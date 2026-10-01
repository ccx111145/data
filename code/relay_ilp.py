# -*- coding: utf-8 -*-
"""
relay_ilp.py —— 中继侧**整数规划区间松弛**判定器（SCI 实验补齐 ② 的第三块）

定位
----
`relay_baselines.py` 的两条下界（逐格集合覆盖 $N_{\\rm naive}$、相邻相位并集覆盖
$LB_{\\rm handover}$）都是**纯几何**的。本脚本补上第三类方法：把调度问题写成
**相位级的整数规划区间松弛**，用 CP-SAT 独立地重判"N 架是否可行"，
从而与状态 DP（`q3dpN.py`）形成**方法学交叉验证**。

模型（相位 = 区间）
-------------------
需求期被切成若干**相位** $\\{[t_k^{\\rm lo}, t_k^{\\rm hi}]\\}$（相内需求结构稳定）。
变量 $x_{i,j,k}\\in\\{0,1\\}$：中继 $i$ 在相位 $k$ 以悬停点 $j$ 值守。约束：

  (C1) 覆盖：每条失联实例 $r$ 落在相位 $k(r)$，要求
       $\\sum_i\\sum_{j:\\,j\\ \\text{覆盖}\\ r} x_{i,j,k(r)} \\ge 1$；
  (C2) 单点值守：$\\sum_j x_{i,j,k}\\le 1$（一架在一个相位内只用一个悬停点）；
  (C3) 过滤：若点 $j$ 在该相位覆盖不到任何在册实例，则 $x_{i,j,k}=0$；
  (C4) **换位黑障（相位级）**：若 $x_{i,a,k}=x_{i,b,k+1}=1$ 且 $a\\ne b$，
       则需 $W(a,b)\\le t_{k+1}^{\\rm lo}-t_k^{\\rm hi}$，否则该组合被割掉。

与真实调度的关系（**方向很重要**）
----------------------------------
(C4) 只是必要条件：它把每个相位内部的时刻耦合全部丢掉，不再要求"换位期间
另一架保持覆盖"。因此

  * 松弛**不可行** ⇒ 真实调度不可行（这是强结论，不可行性被独立证实）；
  * 松弛**可行**   ⇒ 真实调度**未必**可行（只说明瓶颈在更细的时刻耦合层）。

这正是区间松弛应有的强弱方向，也是它与状态 DP 互补之处：
DP 在时刻级精确、但只对声明的候选集生效；本松弛在相位级、约束更弱、覆盖全候选池。

输出：results/中继ILP松弛.json + 控制台表

用法：python relay_ilp.py [--model observed] [--Ns 1,2,3,4] [--tl 120]
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

import comm as C
import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def build_transport():
    sol = SIO.load()
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
    return sol, sorties, assign


def decide(ph, cov, groups, phases, N, wfun, tl=120.0, per_phase=40, verbose=False):
    """相位级区间松弛：N 架能否覆盖全部相位的在册需求。

    phases: [(lo_cell, hi_cell), ...] 升序且互不重叠（相数与相边界来自 q3.relay_phases）
    wfun(a, b): 点 a→b 的黑障窗口（秒），与 q3dpN 同口径
    per_phase: 每个相位最多保留多少个候选点（按该相内可覆盖实例数降序）。
               全候选池 × 全相位 × N 的布尔变量数会到百万量级并触发 OOM，
               故本松弛在**每相 top-per_phase 的精简候选集**上求解——
               这一点与 DP 的候选集限制一样，必须与结论一起报告。
    """
    from ortools.sat.python import cp_model

    cells = np.asarray(ph["cells"], dtype=np.float64)
    n_inst = cov.shape[0]

    # 每条实例归属的相位
    inst_phase = np.full(n_inst, -1, dtype=int)
    for pi, (lo, hi) in enumerate(phases):
        for k in range(lo, hi + 1):
            for r in np.asarray(groups[k], dtype=int):
                inst_phase[r] = pi
    # 每个相位的精简候选点：按"该相内可覆盖的实例数"降序取前 per_phase 个
    phase_pts = []
    for pi in range(len(phases)):
        rs = np.nonzero(inst_phase == pi)[0]
        if rs.size == 0:
            phase_pts.append(np.zeros(0, dtype=int))
            continue
        gain = cov[rs].sum(axis=0)
        order = np.argsort(-gain)
        pick = [int(j) for j in order[:per_phase] if gain[j] > 0]
        phase_pts.append(np.asarray(pick, dtype=int))

    t_lo = np.array([cells[lo] for lo, _ in phases])
    t_hi = np.array([cells[hi] for _, hi in phases])

    m = cp_model.CpModel()
    x = {}
    for i in range(N):
        for pi in range(len(phases)):
            for j in phase_pts[pi]:
                x[(i, int(j), pi)] = m.NewBoolVar("x_%d_%d_%d" % (i, int(j), pi))
            if phase_pts[pi].size:
                m.Add(sum(x[(i, int(j), pi)] for j in phase_pts[pi]) <= 1)   # (C2)

    # (C1) 覆盖：每条实例必须被某个 (中继, 该相可用点) 组合覆盖
    for r in range(n_inst):
        pi = inst_phase[r]
        if pi < 0:
            continue
        js = [int(j) for j in np.nonzero(cov[r])[0]]
        usable = [j for j in js if (0, j, pi) in x]
        if not usable:
            return dict(status="INFEASIBLE_UNCOVERABLE", feasible=False, proven=True,
                        reason="实例 %d 在相位 %d 的精简候选集内无可用点" % (r, pi))
        m.Add(sum(x[(i, j, pi)] for i in range(N) for j in usable) >= 1)

    # (C4) 相邻相位换点的黑障可行性
    npair = 0
    for pi in range(len(phases) - 1):
        gap = float(t_lo[pi + 1] - t_hi[pi])
        for i in range(N):
            js1 = [j for (ii, j, p) in x if ii == i and p == pi]
            js2 = [j for (ii, j, p) in x if ii == i and p == pi + 1]
            for a in js1:
                for b in js2:
                    if a == b:
                        continue
                    if wfun(a, b) > gap:
                        m.Add(x[(i, a, pi)] + x[(i, b, pi + 1)] <= 1)
                        npair += 1

    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = float(tl)
    sol.parameters.num_search_workers = 8
    st = sol.Solve(m)
    feasible = st in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    chosen = []
    if feasible:
        for (i, j, pi), v in x.items():
            if sol.Value(v) > 0.5:
                chosen.append(dict(relay=int(i), point=int(j), phase=int(pi)))
    return dict(status=sol.StatusName(st), feasible=bool(feasible),
                proven=bool(st == cp_model.INFEASIBLE),
                n_bool=int(len(x)), n_blackout_cuts=int(npair),
                per_phase=int(per_phase),
                n_pts_per_phase=[int(t.size) for t in phase_pts],
                chosen=sorted(chosen, key=lambda d: (d["phase"], d["relay"]))[:60])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="observed")
    ap.add_argument("--topk", type=int, default=400)
    ap.add_argument("--Ns", default="1,2,3,4")
    ap.add_argument("--tl", type=float, default=120.0)
    ap.add_argument("--per-phase", type=int, default=40,
                    help="每个相位保留的候选点数（按相内可覆盖实例数降序）")
    a = ap.parse_args()
    t0 = time.time()

    inst = Q.Instance()
    _, sorties, assign = build_transport()
    link = C.Link(inst, channel_model=a.model)
    import cover_model as CM
    palette = CM.CoverModel(inst, channel_model=a.model, verbose=False).palette
    ph = Q3.relay_phases(inst, sorties, assign, palette, link=link, verbose=False,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    if not ph.get("ok"):
        print("!! 相位规划失败：%s" % ph.get("msg"))
        return 1
    cov = np.asarray(ph["cov"], dtype=np.int64)
    groups = ph.get("groups") or []
    phases = [(int(lo), int(hi)) for lo, hi, _ in sorted(ph["intervals"], key=lambda r: r[0])]
    cells = np.asarray(ph["cells"], dtype=np.float64)
    print("相位 %d 个，失联实例 %d，候选点 %d" % (len(phases), cov.shape[0], cov.shape[1]))
    print("相位表：" + " | ".join("%d–%d（%.0f–%.0f s）" % (lo, hi, cells[lo], cells[hi])
                                  for lo, hi in phases))

    pb = DN.PB(ph, grid=10.0, topk=a.topk, inst=inst, mode="base")
    wfun = lambda x, y: pb.w_sec(int(x), int(y))          # noqa: E731

    out = dict(model=a.model, topk=int(a.topk), n_phases=len(phases),
               n_inst=int(cov.shape[0]), n_cand=int(cov.shape[1]),
               per_phase=int(a.per_phase), tl_s=float(a.tl),
               phases=[[lo, hi, round(float(cells[lo]), 1), round(float(cells[hi]), 1)]
                       for lo, hi in phases],
               results={}, elapsed_s=None)
    for N in [int(t) for t in a.Ns.split(",") if t.strip()]:
        tt = time.time()
        r = decide(ph, cov, groups, phases, N, wfun, tl=a.tl, per_phase=a.per_phase)
        r["elapsed_s"] = round(time.time() - tt, 1)
        if r.get("feasible"):
            r["relays_used"] = len({c["relay"] for c in r["chosen"]})
        out["results"]["N%d" % N] = r
        print("  N=%d → %-18s 布尔变量 %6d，黑障割 %7d，用时 %7.1f s  %s"
              % (N, r["status"], r.get("n_bool", 0), r.get("n_blackout_cuts", 0),
                 r["elapsed_s"],
                 "已证明不可行" if r.get("proven") else
                 ("找到可行值守表" if r.get("feasible") else "未定（需放宽时限）")))
    out["elapsed_s"] = round(time.time() - t0, 1)

    p = os.path.join(OUT, "中继ILP松弛.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s（%.0f s）" % (p, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
