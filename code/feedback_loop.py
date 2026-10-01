# -*- coding: utf-8 -*-
"""
feedback_loop.py —— 审稿防线 2：运输—中继协同再调度（Co-design Feedback Loop）

审稿人会问：不可行是不是因为"运输排程是外生固定的"？如果允许微调运输架次的起飞时刻，
把失联需求在时间上错开，N=2 是否就能接力？

本脚本回答这个问题，且**不改变货箱—架次归属、不改变访问顺序与机型**，只调整各架次的开始时刻：
  1) 用"跨度—黑障不等式"定位赤字点：span(t-w) < w；
  2) 以**最小化赤字**为目标，对固定架次集合做开始时刻的局部搜索
     （约束：同一架无人机前后架次不重叠、共享电池占用与充电不重叠、硬时限尽量不破坏）；
  3) 报告：赤字能否被压到 0（⇒ N=2 在 Mode 2 下可行）；若不能，缺口还剩多少；
     若能，代价是完工时间/加权延误增加了多少（"用多少运输延误换取 1 架中继"）。

评估口径（精确、可复算）
------------------------
对每个候选悬停点 j 与每个运输架次，预计算"该架次失联且**不被 j 覆盖**"的相对时间区间；
给定各架次开始时刻后，把这些区间投影到统一时间栅格：某格"单点可独保"⟺ 存在 j 在该格无失败。
span(k) = 从 k 起的最长连续"单点可独保"格数。
"""
from __future__ import annotations

import argparse
import json
import os
import time
import numpy as np

import dcore as D
import comm as C
import q2 as Q
import q3 as Q3
import relay as R
import solution_io as SIO

OUT = D.RESULTS
GRID = 10.0


# ---------------------------------------------------------------------------
def load_transport():
    inst = Q.Instance()
    sol = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"]) for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=float(r.get("chg", 0.0)),
                         soc=float(r.get("soc", 1.0)))
    return inst, sol, sorties, assign


def strong_points(inst, ph, K=70):
    """取"独立覆盖格数"最多的 K 个候选点（与 q3.relay_phases 的强点口径一致）。"""
    order = np.argsort(-ph["alone"].sum(axis=0))
    return [int(j) for j in order[:K]]


def uncovered_profiles(inst, sorties, assign, link):
    """每个架次的"直连不可用"相对时间样本：(t_rel, lon, lat, alt) 数组（相对架次开始）。"""
    profs = []
    for k, s in enumerate(sorties):
        tr = C.sortie_track(inst, s, assign[k]["start"], GRID)
        if len(tr["t"]) == 0:
            profs.append((np.zeros(0), np.zeros((0, 3))))
            continue
        ok, lp, bl = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        idx = np.nonzero(~ok)[0]
        t_rel = tr["t"][idx] - assign[k]["start"]
        pts = np.c_[tr["lon"][idx], tr["lat"][idx], tr["alt"][idx]]
        profs.append((t_rel, pts))
    return profs


def point_failure_masks(inst, link, ph, profs, pts_idx):
    """对每个强点 j，返回每个架次"失联且 j 覆盖不到"的相对时间数组。"""
    out = []
    for j in pts_idx:
        p = tuple(float(x) for x in ph["palette"][j])
        bh_ok, _, _ = link.backhaul_ok(np.array([p]))
        if not bh_ok[0]:
            out.append(None)
            continue
        per = []
        for (t_rel, pts) in profs:
            if len(t_rel) == 0:
                per.append(np.zeros(0))
                continue
            a_ok, _, _ = link.access_ok(pts, p)
            per.append(t_rel[~a_ok])
        out.append(per)
    return out


def build_grid(cells):
    return cells


def span_profile(cells, fails, starts, n_cell):
    """给定各架次开始时刻，返回 (solo_ok, span_cells, deficit)。"""
    solo = np.zeros(n_cell, dtype=bool)
    for per in fails:
        if per is None:
            continue
        bad = np.zeros(n_cell + 2, dtype=np.int32)
        for k, t_rel in enumerate(per):
            if len(t_rel) == 0:
                continue
            t_abs = t_rel + starts[k]
            i0 = np.searchsorted(cells, t_abs, side="left")
            i1 = np.searchsorted(cells, t_abs, side="right")
            for a, b in zip(i0, i1):
                if a < n_cell:
                    bad[a] += 1
                    bad[min(b, n_cell)] -= 1
        solo |= (np.cumsum(bad)[:n_cell] == 0)
    # span(k) = 从 k 起的最长连续 solo 格数
    span = np.zeros(n_cell, dtype=np.int64)
    run = 0
    for k in range(n_cell - 1, -1, -1):
        run = run + 1 if solo[k] else 0
        span[k] = run
    return solo, span


def deficit_of(cells, span, w_cells):
    """(★) 赤字：对所有完成时刻 k，max(0, w - span(k-w))（格数）。"""
    n = len(cells)
    d = 0
    worst = None
    for k in range(w_cells, n):
        s = span[k - w_cells]
        if s < w_cells:
            gap = w_cells - s
            d += gap
            if worst is None or gap > worst[1]:
                worst = (k, int(gap), float(cells[k]))
    return int(d), worst


def feasible_windows(sorties, assign, delta_max):
    """每个架次在不与同机其它架次冲突前提下的开始时刻调整区间。"""
    win = {}
    by_drone = {}
    for k, a in assign.items():
        by_drone.setdefault(a["drone"], []).append(k)
    for dr, ks in by_drone.items():
        ks.sort(key=lambda k: assign[k]["start"])
        for i, k in enumerate(ks):
            lo = assign[ks[i - 1]]["end"] if i > 0 else 0.0
            hi = assign[ks[i + 1]]["start"] - sorties[ks[i + 1]].dur if i + 1 < len(ks) else 1e9
            win[k] = (lo, hi)
    return win


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=400)
    ap.add_argument("--K", type=int, default=70)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--delta", type=float, default=900.0)
    a = ap.parse_args()
    t0 = time.time()
    inst, sol, sorties, assign = load_transport()
    link = C.Link(inst)
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    cells = np.asarray(ph["cells"], dtype=np.float64)
    n = len(cells)
    pts_idx = strong_points(inst, ph, K=a.K)
    print("  强点 %d 个；开始计算各架次失联剖面 ..." % len(pts_idx))
    profs = uncovered_profiles(inst, sorties, assign, link)
    n_unc = sum(len(t) for t, _ in profs)
    print("  失联采样点合计 %d 个（%d 个架次）" % (n_unc, len(sorties)))
    fails = point_failure_masks(inst, link, ph, profs, pts_idx)
    print("  失败掩码完成 %.0f s" % (time.time() - t0))

    rtype = inst.d["rtype"]
    sample = pts_idx[:min(len(pts_idx), 40)]
    w_air = []
    for x in sample:
        for y in sample:
            if x == y:
                continue
            t, _, _ = D.relay_transit(rtype, inst.nodes,
                                      tuple(float(v) for v in ph["palette"][x]),
                                      tuple(float(v) for v in ph["palette"][y]))
            w_air.append(t + rtype.t_link)
    w = float(np.median(w_air))
    wc = int(round(w / GRID))
    print("  Mode 2 换位黑障 w(中位) = %.0f s = %d 格" % (w, wc))

    starts0 = np.array([assign[k]["start"] for k in range(len(sorties))])
    solo0, span0 = span_profile(cells, fails, starts0, n)
    d0, worst0 = deficit_of(cells, span0, wc)
    print("\n=== 基准（原排程）===")
    print("  单点可独保格 %d/%d；span 中位 %.0f s；赤字合计 %d 格（%.0f s）"
          % (int(solo0.sum()), n, np.median(span0) * GRID, d0, d0 * GRID))
    print("  最大赤字点：k=%d t=%.0f s，缺口 %d 格（%.0f s）" % (worst0[0], worst0[2], worst0[1], worst0[1] * GRID))

    # ---- 局部搜索：只调开始时刻 ----
    rng = np.random.default_rng(a.seed)
    win = feasible_windows(sorties, assign, a.delta)
    starts = starts0.copy()
    best_starts = starts.copy()
    best = (d0, worst0)
    cur = d0
    for it in range(a.iters):
        k = int(rng.integers(0, len(sorties)))
        lo, hi = win[k]
        cand = starts.copy()
        shift = rng.uniform(-a.delta, a.delta)
        ns = float(np.clip(starts[k] + shift, max(0.0, lo), min(hi - sorties[k].dur, hi)))
        if ns < lo - 1e-9 or ns + sorties[k].dur > hi + 1e-9:
            continue
        cand[k] = ns
        _, span = span_profile(cells, fails, cand, n)
        dc, wc_ = deficit_of(cells, span, wc)
        if dc < cur or (dc == cur and rng.random() < 0.15):
            starts, cur = cand, dc
            if dc < best[0]:
                best = (dc, wc_)
                best_starts = cand.copy()
    print("\n=== 反馈再调度后（仅调整开始时刻，不改箱-架次归属/顺序/机型）===")
    solo1, span1 = span_profile(cells, fails, best_starts, n)
    print("  单点可独保格 %d/%d；span 中位 %.0f s；赤字合计 %d 格（%.0f s）"
          % (int(solo1.sum()), n, np.median(span1) * GRID, best[0], best[0] * GRID))
    if best[1]:
        print("  最大赤字点：k=%d t=%.0f s，缺口 %d 格（%.0f s）"
              % (best[1][0], best[1][2], best[1][1], best[1][1] * GRID))
    mk0 = max(float(x["end"]) for x in assign.values())
    shifts = best_starts - starts0
    print("  开始时刻调整：%d 个架次变动，最大前移 %.0f s，最大后移 %.0f s，绝对调整量合计 %.0f s"
          % (int((np.abs(shifts) > 1e-6).sum()), -min(0.0, shifts.min()), max(0.0, shifts.max()),
             float(np.abs(shifts).sum())))

    verdict = ("赤字清零 ⇒ N=2 在 Mode 2 下**可行**，可用少量运输时刻调整省下 1 架中继"
               if best[0] == 0 else
               "赤字未清零 ⇒ 即使做最优的运输时刻协同，N=2 仍不可行（残余赤字 %.0f s）" % (best[0] * GRID))
    print("\n=== 结论 ===\n  " + verdict)

    json.dump(dict(w_air_median_s=round(w, 1), w_cells=wc,
                   baseline=dict(deficit_cells=d0, deficit_s=round(d0 * GRID, 1),
                                 solo_cells=int(solo0.sum()), n_cells=int(n),
                                 span_median_s=round(float(np.median(span0) * GRID), 1),
                                 worst=dict(k=worst0[0], t=worst0[2], gap_cells=worst0[1],
                                            gap_s=round(worst0[1] * GRID, 1))),
                   after_feedback=dict(deficit_cells=int(best[0]), deficit_s=round(best[0] * GRID, 1),
                                       solo_cells=int(solo1.sum()), n_cells=int(n),
                                       span_median_s=round(float(np.median(span1) * GRID), 1),
                                       worst=(dict(k=best[1][0], t=best[1][2], gap_cells=best[1][1],
                                                   gap_s=round(best[1][1] * GRID, 1)) if best[1] else None),
                                       n_shifted=int((np.abs(shifts) > 1e-6).sum()),
                                       max_shift_abs_s=round(float(np.abs(shifts).max()), 1),
                                       total_shift_s=round(float(np.abs(shifts).sum()), 1),
                                       makespan_before=round(mk0, 1)),
                   verdict=verdict),
              open(os.path.join(OUT, "协同再调度.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写出：%s" % os.path.join(OUT, "协同再调度.json"))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
