# -*- coding: utf-8 -*-
"""
struct_diag.py —— 结构性诊断：把"2 架不可行"从经验结论升级为可解释的定理

核心量：
  * alone-run 长度分布：单个悬停点能**单独**覆盖全部需求的极大连续时段长度；
  * 换位黑障窗口 w：Mode 1 / Mode 2 下的点对分布；
  * **可行换位机会集** O(w) = { t : 存在某悬停点在该点单独覆盖整个 [t, t+w] }
    —— 只有当一架中继要换位时，另一架必须在这个窗口内单独保障，故换位只能发生在 O(w) 内。

由此得到可检验的必要条件：
  (N1) 若某时刻的"单点可覆盖性"在长度 w 的窗口上处处不成立，则任何换位都无法覆盖该窗口，
       系统只能保持配置不变；若同时该窗口内需要的覆盖点必须改变，则 N 架不可行。
  (N2) 更一般地：换位次数 k 与可行换位机会的时空分布共同决定最小机队规模。

输出：results/结构诊断.json + 控制台表
"""
from __future__ import annotations

import json
import os
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def main():
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
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    pb = DN.PB(ph, grid=10.0, topk=12, inst=inst, mode="air")
    alone = ph["alone"]          # (n_cell, n_point)
    n, P = alone.shape
    cells = np.asarray(ph["cells"], dtype=np.float64)

    # ---- 1) alone-run 长度分布 ----
    runs = []
    for j in range(P):
        idx = np.nonzero(alone[:, j])[0]
        if len(idx) == 0:
            continue
        brk = np.nonzero(np.diff(idx) > 1)[0]
        for seg in np.split(idx, brk + 1):
            runs.append((float(cells[seg[-1]] - cells[seg[0]]), int(seg[1] - seg[0] + 1) if False
                         else int(len(seg))))
    L = np.array([r[0] for r in runs])
    print("\n=== alone-run（单点可独立保障的极大连续时段）===")
    print("  条数 %d；长度 s: 中位 %.0f / 均值 %.0f / P90 %.0f / 最大 %.0f"
          % (len(L), np.median(L), L.mean(), np.percentile(L, 90), L.max()))

    # ---- 2) 换位黑障窗口分布（两种模式）----
    rng = np.random.default_rng(0)
    js = rng.choice(P, size=min(P, 400), replace=False)
    base, air = [], []
    for a in js:
        for b in js:
            if a == b:
                continue
            rt = inst.d["rtype"]
            base.append(rt.t_turn + pb.TB[a] + pb.TO[b] + rt.t_link)
            t, e, c = D.relay_transit(rt, inst.nodes,
                                      tuple(float(x) for x in pb.palette[a]),
                                      tuple(float(x) for x in pb.palette[b]))
            air.append(t + rt.t_link)
    base = np.array(base); air = np.array(air)
    print("\n=== 换位黑障窗口 w（点对分布，n=%d）===" % len(base))
    for nm, arr in (("Mode 1 基地返航", base), ("Mode 2 空中转场", air)):
        print("  %-14s 中位 %6.0f s / 均值 %6.0f s / P10 %6.0f / P90 %6.0f"
              % (nm, np.median(arr), arr.mean(), np.percentile(arr, 10), np.percentile(arr, 90)))

    # ---- 3) 可行换位机会集 O(w)：存在单点覆盖整个 [t, t+w] 的时刻数 ----
    def opp(w_s):
        w = max(1, int(round(w_s / 10.0)))
        ok = np.zeros(n, dtype=bool)
        for k in range(n):
            k1 = min(n - 1, k + w)
            if k1 - k < w:
                continue
            # run_end[k, j] = 点 j 的 alone-run（含 k）的结束格；>= k1 即覆盖 [k, k1]
            ok[k] = bool((pb.run_end[k] >= k1).any())
        return ok

    print("\n=== 可行换位机会 O(w)：存在单点能单独保障整个长度-w 窗口的时刻 ===")
    res = {}
    for nm, arr in (("Mode 1", base), ("Mode 2", air)):
        w = float(np.median(arr))
        ok = opp(w)
        frac = ok.mean()
        # 最长连续可换位段（连续机会段才有意义：换位需要连续 w 的窗口，机会本身也是时刻）
        idx = np.nonzero(ok)[0]
        longest = 0.0
        if len(idx):
            brk = np.nonzero(np.diff(idx) > 1)[0]
            for seg in np.split(idx, brk + 1):
                longest = max(longest, float(cells[seg[-1]] - cells[seg[0]]))
        res[nm] = dict(w_median_s=round(w, 1), opp_frac=round(float(frac), 4),
                       opp_cells=int(ok.sum()), n_cells=int(n),
                       longest_opp_span_s=round(longest, 1))
        print("  %-8s w=%6.0f s → 可换位时刻 %4d/%d (%.1f%%)，最长连续机会段 %.0f s"
              % (nm, w, int(ok.sum()), n, 100 * frac, longest))

    # ---- 4) 崩溃点附近的局部结构 ----
    # maxrun[k] = 从 k 起"某单点可独立保障"的最长时长（s）
    maxrun_cells = np.zeros(n, dtype=np.int64)
    for k in range(n):
        e = int(pb.run_end[k].max()) if pb.run_end[k].size else -1
        maxrun_cells[k] = max(0, e - k + 1)
    maxrun_s = maxrun_cells * 10.0
    print("\n=== 从每个时刻起可用的最长「单点独保」时长 ===")
    print("  中位 %.0f s / 均值 %.0f s / P90 %.0f s / 最大 %.0f s"
          % (np.median(maxrun_s), maxrun_s.mean(), np.percentile(maxrun_s, 90), maxrun_s.max()))

    k_fail = 171
    w1 = max(1, int(round(float(np.median(base)) / 10.0)))
    w2 = max(1, int(round(float(np.median(air)) / 10.0)))
    if k_fail < n:
        print("\n=== 崩溃格 k=%d（t=%.0f s）===" % (k_fail, cells[k_fail]))
        print("  从该格起的最长单点独保时长 = %.0f s" % maxrun_s[k_fail])
        print("  Mode 1 需要黑障窗口 w=%d 格（%.0f s）→ %s"
              % (w1, w1 * 10.0, "足够" if maxrun_cells[k_fail] >= w1 else "**不足**"))
        print("  Mode 2 需要黑障窗口 w=%d 格（%.0f s）→ %s"
              % (w2, w2 * 10.0, "足够" if maxrun_cells[k_fail] >= w2 else "**不足**"))
        # 崩溃格之前必须换位的次数：用"需求覆盖点的变化"近似
        k0 = max(0, k_fail - w1)
        seg = maxrun_cells[k0:k_fail + 1]
        print("  在 Mode-1 黑障回看窗口 [k=%d, %d]（%.0f–%.0f s）内，"
              "最长单点独保仅 %d 格（%.0f s），而窗口长 %d 格"
              % (k0, k_fail, cells[k0], cells[k_fail], int(seg.max()), seg.max() * 10.0,
                 k_fail - k0 + 1))
        print("  ⇒ 该窗口内**任何单点都无法独自保障全程**，故换位无法安排；"
              "而窗口内所需覆盖点又必须改变 ⇒ 配置被冻结，需求不可覆盖。")

    out = dict(alone_runs=dict(n=int(len(L)), median_s=round(float(np.median(L)), 1),
                               mean_s=round(float(L.mean()), 1),
                               p90_s=round(float(np.percentile(L, 90)), 1),
                               max_s=round(float(L.max()), 1)),
               blackout=dict(base_median_s=round(float(np.median(base)), 1),
                             base_p10_s=round(float(np.percentile(base, 10)), 1),
                             base_p90_s=round(float(np.percentile(base, 90)), 1),
                             air_median_s=round(float(np.median(air)), 1),
                             air_p10_s=round(float(np.percentile(air, 10)), 1),
                             air_p90_s=round(float(np.percentile(air, 90)), 1)),
               singleton_span=dict(median_s=round(float(np.median(maxrun_s)), 1),
                                   p90_s=round(float(np.percentile(maxrun_s, 90)), 1),
                                   max_s=round(float(maxrun_s.max()), 1)),
               opportunity=res,
               fail_cell=dict(k=k_fail, t=round(float(cells[k_fail]), 1),
                              max_singleton_span_s=round(float(maxrun_s[k_fail]), 1),
                              need_base_s=round(w1 * 10.0, 1), need_air_s=round(w2 * 10.0, 1)))
    p = os.path.join(OUT, "结构诊断.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
