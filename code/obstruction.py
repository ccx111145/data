# -*- coding: utf-8 -*-
"""
obstruction.py —— **N=2 的精确判定**、alibi 窗口证书与机队规模下界

论文 Theorem（handover obstruction）只给出 N=2 的**必要**条件（span–黑障不等式）。
本脚本把它升级为**充要**，并给出可计算的结构量：

  (E) N=2 精确判定（Theorem: exact two-relay decision）
      在"至多一架同时换位"(A2) 下，两架中继的换位必然**交替**：
      若 u=(a,b) 是当前配置、a 在 τ 完成换位到 a'，则
        · 窗口 [τ-W(a,a'), τ] 内只有 b 在保障 ⇒ b 的悬停点在过去 w 格内恒定；
        · a 的下一次换位必须等到 b 的换位窗口结束。
      故 N=2 可行 ⟺ 存在交替的点序列与换位时刻，使每个 alibi 窗口都被
      "另一架的固定点"完整覆盖、且每架的在空时长不超过 T^cap。这是一个
      在配置空间上的可达性问题；把状态剪枝全部关闭即为**精确判定**。

  (A) alibi 窗口证书
      span(k) = 从格 k 起、某单点能**单独**连续保障的最长时长（论文 span 函数）。
      换位只能发生在 span(k) ≥ w 的格上；统计该条件的放行率与赤字。

  (B) 机队规模下界（两条独立来源）
      · 能量维：每架一次在空最多 T^cap 秒，需求期长 T ⇒ N ≥ ceil(T / T^cap)；
      · 结构维：μ = max_j max_k span_{¬j}(k)（撤掉任一架后系统能独撑的最长时长），
        每架至少换位一次 ⇒ μ ≤ T-(N-1)·w_min ⇒ N ≥ 1 + floor(μ / w_min)。

输出：results/局部阻塞证书.json + 控制台表
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dp3 as DP3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def hover_cap_s(inst):
    """单架次在空（悬停）上限 T^cap —— 与 q3refresh.py / mode_compare.py **同口径**：
    ((1-rho)*e_use - e_fly_assumed) / (p_hover + p_comm) * 3600，e_fly_assumed = 0.35 kWh。
    """
    rt = inst.d["rtype"]
    return float(((1 - rt.rho) * rt.e_use - 0.35) / (rt.p_hover + rt.p_comm) * 3600.0)


# --------------------------------------------------------------------------
def build_phase(inst, sol):
    """与 struct_diag.py 完全一致的 phase 构造，保证结果可比。"""
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"])
                for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]),
                         drone=r["drone"], battery=r["battery"],
                         chg=float(r.get("chg", 0.0)), soc=float(r.get("soc", 1.0)))
    return Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette,
                           verbose=False, min_phase_s=1400.0, max_phase_s=5400.0)


def cover_matrix(pb):
    """A[k, j] = 1 ⟺ 候选点 j 在格 k 完整覆盖该格在册需求（口径与 pb.need 一致）。"""
    A = np.zeros((pb.n, pb.P), dtype=np.int64)
    for k in range(pb.n):
        m = pb.mask[k]
        A[k] = ((m & pb.need[k]) == pb.need[k]).astype(np.int64)
    return A


def span_series(pb, step):
    """论文 span 函数：span(k) = 从格 k 起某单点能单独连续保障的最长时长（秒）。"""
    RE = np.asarray(pb.run_end)
    n = pb.n
    if not RE.size:
        return np.zeros(n)
    best = RE.max(axis=1)
    return np.where(best >= 0, best - np.arange(n) + 1, 0) * step


def mu_bound(pb, reloc_pts, step):
    """μ = max_j max_k span_{¬j}(k)。"""
    RE = np.asarray(pb.run_end)
    n, P = pb.n, pb.P
    if not RE.size or P < 2:
        return 0.0, np.zeros(P)
    rs = np.sort(RE, axis=1)
    best, second = rs[:, -1], rs[:, -2]
    span_all = np.where(best >= 0, best - np.arange(n) + 1, 0) * step
    span_second = np.where(second >= 0, second - np.arange(n) + 1, 0) * step
    n_arg = (RE == best[:, None]).sum(axis=1)
    mu = np.zeros(P, dtype=np.float64)
    for j in range(P):
        span = np.where(RE[:, j] == best,
                        np.where(n_arg == 1, span_second, span_all), span_all)
        vals = span[reloc_pts]
        mu[j] = float(vals.max()) if vals.size else 0.0
    return float(mu.max()), mu


def w_distribution(pb, js, cap=300):
    """换位黑障窗口 w 的分布（Mode 依赖 pb.mode），用于给出放行率阈值。"""
    a = js[:cap]
    w = [pb.w_sec(x, y) for x in a for y in a if x != y]
    return np.asarray(w, dtype=np.float64)


# --------------------------------------------------------------------------
def exact_two_relay(ph, mode, topk, verbose=True, max_states=200000):
    """(E) N=2 精确判定：关闭全部状态剪枝，仅加状态数内存护栏。

    返回 dict(feasible, reason, n_state_max, k, t, hit_cap)。
    hit_cap=True 表示在给定候选集上**未能**跑完精确判定（状态空间超出预算），
    此时不得声称"在该候选集上不可行"，只能报告搜索边界。
    """
    try:
        seq, cost, pbx, diag = DN.solve(ph, N=2, grid=10.0, topk=topk, inst=None,
                                        verbose=verbose, mode=mode, exact=True,
                                        max_states=max_states)
    except DN.StateSpaceOverflow as e:
        return dict(feasible=None, mode=mode, topk=int(topk), exact=True,
                    max_states=int(max_states), hit_cap=True,
                    reason="状态空间超出护栏：%s" % str(e)[:160])
    ok = seq is not None
    d = diag or {}
    return dict(feasible=bool(ok), mode=mode, topk=int(topk), exact=True,
                max_states=int(max_states), hit_cap=False,
                n_state_max=d.get("n_state"),
                fail_k=(None if ok else d.get("k")),
                fail_t=(None if ok else d.get("t")),
                reason=(None if ok else "第 %s 格（t=%s s）无可行状态"
                        % (d.get("k"), d.get("t"))))


# --------------------------------------------------------------------------
def main():
    inst = Q.Instance()
    sol = SIO.load()
    ph = build_phase(inst, sol)
    cells = np.asarray(ph["cells"], dtype=np.float64)
    step = float(np.median(np.diff(cells)))
    T = float(cells[-1] - cells[0])
    cap = hover_cap_s(inst)
    print("需求格 %d 个，时长 %.0f s，候选点 %d 个；单架次在空上限 T^cap=%.1f s"
          % (len(cells), T, ph["alone"].shape[1], cap))

    out = dict(n_cells=int(len(cells)), T_s=round(T, 1), step_s=round(step, 2),
               T_cap_s=round(cap, 1),
               bound_energy=int(math.ceil(T / cap)), results={})

    for mode, label in (("air", "Mode 2 空中转场"), ("base", "Mode 1 基地返航")):
        pb = DN.PB(ph, grid=10.0, topk=12, inst=inst, mode=mode)
        A = cover_matrix(pb)
        ncov = A.sum(axis=1)
        sp = span_series(pb, step)
        multi = (ncov >= 2)
        mu_max, mu = mu_bound(pb, multi, step)
        js = [int(j) for j in pb.useful]
        w = w_distribution(pb, js)
        w_min, w_med = float(w.min()), float(np.median(w))

        def release(th):
            return float((sp >= th).mean())

        st = dict(
            mode=label, n_cells=int(pb.n), n_cand=int(len(js)),
            cells_uncoverable=int((ncov == 0).sum()),
            cells_single_provider=int((ncov == 1).sum()),
            cells_multi_provider=int(multi.sum()),
            span_median_s=round(float(np.median(sp)), 1),
            span_p90_s=round(float(np.percentile(sp, 90)), 1),
            span_max_s=round(float(sp.max()), 1),
            w_min_s=round(w_min, 1), w_median_s=round(w_med, 1),
            release_at_wmin=round(release(w_min), 4),
            release_at_wmed=round(release(w_med), 4),
            mu_max_s=round(mu_max, 1),
            bound_by_w=(int(1 + math.floor(mu_max / w_min)) if w_min > 0 else None),
            bound_energy=int(math.ceil(T / cap)),
            bound_combined=max(int(math.ceil(T / cap)),
                               int(1 + math.floor(mu_max / w_min)) if w_min > 0 else 1),
            # 候选集外延（论文 Proposition: distinguishing candidate set 需写明搜索空间）：
            #   C_1 = 候选点池；C_0 = PB.useful = 至少能在某一格上单独覆盖该格全部需求的点。
            n_cand_pool=int(pb.P),
            n_cand_c0=int(len(js)),
            c0_ratio=round(float(len(js) / max(1, pb.P)), 4),
        )
        out["results"][mode] = st

        print("\n=== %s ===" % label)
        print("  覆盖层：无点可保格 %d，单点独保格 %d，多点可保格 %d"
              % (st["cells_uncoverable"], st["cells_single_provider"],
                 st["cells_multi_provider"]))
        print("  span（单点独保最长时长）：中位 %.0f s / P90 %.0f s / 最大 %.0f s"
              % (st["span_median_s"], st["span_p90_s"], st["span_max_s"]))
        print("  黑障窗口 w：最小 %.0f s / 中位 %.0f s（n=%d）"
              % (w_min, w_med, len(w)))
        print("  换位放行率：span≥w_min 时 %.1f%%；span≥w_median 时 %.1f%%"
              % (100 * st["release_at_wmin"], 100 * st["release_at_wmed"]))
        print("  候选集：点池 %d → C_0 %d（%.1f%%）"
              % (st["n_cand_pool"], st["n_cand_c0"], 100 * st["c0_ratio"]))
        print("  μ_max=%.0f s → 结构下界 N ≥ %d；能量下界 N ≥ %d；计数上界 N ≤ %d"
              % (mu_max, st["bound_by_w"], st["bound_energy"],
                 1 + int(T // w_min) if w_min > 0 else -1))

    # ---- (E) N=2 精确判定（关闭剪枝，仅内存护栏）----
    if "--no-exact" not in sys.argv:
        print("\n=== N=2 精确判定（exact=True，关闭状态剪枝）===")
        for mode, label in (("air", "Mode 2"), ("base", "Mode 1")):
            try:
                r = exact_two_relay(ph, mode, topk=12, verbose=False, max_states=400000)
            except Exception as e:                               # 其它异常
                r = dict(feasible=None, mode=mode, exact=True, error=repr(e)[:200])
            out.setdefault("exact_N2", {})[mode] = r
            print("  %s: %s" % (label, json.dumps(r, ensure_ascii=False)))
    else:
        print("\n（--no-exact：跳过 N=2 精确判定）")

    p = os.path.join(OUT, "局部阻塞证书.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
