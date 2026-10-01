# -*- coding: utf-8 -*-
"""
q3plan.py —— 中继覆盖规划器（逐需求实例覆盖模型）

输入：运输方案（架次集合 + 排程）
输出：中继架次表（悬停位置、海拔、服务时段、能源组件、能耗），使全程连续通信成立

模型
----
1. 精细航迹扫描（10 s 步长）得到每个运输架次"直连不可用"的时段。
2. 在统一时间栅格 Δ=10 s 上，把"时刻 t 存在失联运输机 k 且其位置为 p"定义为
   一个**需求实例** (t, k, p)。同一时刻可以有多个实例（多机同时失联）。
3. 候选悬停点：DEM 覆盖范围内网格 × 悬停离地高度（<= 300 m），预筛回传链路可用的点。
4. coverage[实例][候选点] = 接入链路可用(运输机↔中继) 且 回传链路可用(中继↔G01)。
5. 对每个候选点 c，"可用时段"= c 至少能覆盖该时刻一个实例的极大连续时段；
   一个中继架次只能停在一个点上，对应一个这样的时段。
6. CP-SAT：选择最少的 (候选点, 时段) 组合，使**每个需求实例**至少被一个选中的
   (候选点, 覆盖它的时段) 覆盖，且同一时刻占用的中继架次数 <= 中继无人机台数
   （占用区间含 O01 往返飞行与架次周转）。
7. 生成中继架次并核算飞行/悬停通信能耗、返航 SOC、充电周转。
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Sequence, Tuple

import numpy as np

import dcore as D
import comm as C
import relay as R

GRID = 10.0


# ---------------------------------------------------------------------------
def build_instances(inst, sol, assign, link=None, grid=GRID):
    """统一栅格上的需求实例：(times, pts, kid)。同一时刻可能多条。"""
    link = link or C.Link(inst)
    per = {}
    for k, s in enumerate(sol):
        tr = C.sortie_track(inst, s, assign[k]["start"], grid)
        if len(tr["t"]) == 0:
            continue
        ok, lp, bl = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        cells = np.floor(tr["t"] / grid).astype(int)
        agg = {}
        for c, o, lo, la, al in zip(cells, ~ok, tr["lon"], tr["lat"], tr["alt"]):
            if not o:
                continue
            agg[int(c)] = (float(lo), float(la), float(al))
        per[k] = agg
    T, P, K = [], [], []
    if not per:
        return np.zeros(0), np.zeros((0, 3)), np.zeros(0, dtype=int), 0.0
    allc = sorted({c for a in per.values() for c in a})
    for c in allc:
        for k in sorted(per):
            if c in per[k]:
                lo, la, al = per[k][c]
                T.append(c * grid)
                P.append((lo, la, al))
                K.append(k)
    o = np.argsort(T, kind="stable")
    return np.array(T)[o], np.array(P)[o], np.array(K)[o], (max(allc) * grid if allc else 0.0)


# ---------------------------------------------------------------------------
def candidate_pool(T, cov, slot=300.0, per_slot=8):
    """槽位贪心集合覆盖，收集候选点池（保证有备选）。"""
    pool = set()
    sl = np.floor(T / slot).astype(int)
    for s in np.unique(sl):
        idx = np.nonzero(sl == s)[0]
        sub = cov[idx]
        gains = sub.sum(axis=0)
        for c in np.argsort(-gains)[:per_slot]:
            pool.add(int(c))
        rem = np.ones(len(sub), dtype=bool)
        for _ in range(3):
            if not rem.any():
                break
            gains = sub[np.nonzero(rem)[0]].sum(axis=0)
            c = int(np.argmax(gains))
            if gains[c] == 0:
                break
            pool.add(c)
            hit = sub[:, c]
            rem = rem & (~hit)
    return sorted(pool)


def runs_for(inst, T, K, cov, pool, meta, min_len=60.0):
    """对候选池内每个点求"可用时段"：至少覆盖该时刻一个实例的极大连续时段。"""
    times = np.unique(T)
    n_t = len(times)
    tidx = np.searchsorted(times, T)
    runs = []
    for c in pool:
        usable = np.zeros(n_t, dtype=bool)
        np.logical_or.at(usable, tidx, cov[:, c])
        i = 0
        while i < n_t:
            if not usable[i]:
                i += 1
                continue
            j = i
            while j + 1 < n_t and usable[j + 1]:
                j += 1
            t0, t1 = float(times[i]), float(times[j])
            if t1 - t0 >= min_len or (j - i + 1) >= 2:
                runs.append(dict(t0=t0, t1=t1, c=int(c), i0=int(i), i1=int(j),
                                 lon=meta[c][0], lat=meta[c][1], g=meta[c][2], agl=meta[c][3]))
            i = j + 1
    return runs, times


def select_runs(inst, runs, T, K, times, cov, pool, n_relay, tlimit=90.0, verbose=True):
    """CP-SAT：最少中继架次 + 逐实例覆盖 + 并发 <= n_relay。"""
    from ortools.sat.python import cp_model
    occ = []
    for r in runs:
        rf = D.relay_flight(inst.d["rtype"], inst.nodes, r["lon"], r["lat"], r["agl"])
        dep = max(0.0, r["t0"] - inst.d["rtype"].t_link - rf["t_out"])
        back = r["t1"] + rf["t_back"] + inst.d["rtype"].t_turn
        occ.append((dep, back, rf["e_fly"]))
    m = cp_model.CpModel()
    y = [m.NewBoolVar("y%d" % i) for i in range(len(runs))]
    ivs = []
    for i in range(len(runs)):
        s0 = int(math.floor(occ[i][0])); e0 = int(math.ceil(occ[i][1]))
        ivs.append(m.NewOptionalIntervalVar(s0, max(1, e0 - s0), e0, y[i], "iv%d" % i))
    m.AddCumulative(ivs, [1] * len(ivs), n_relay)

    tidx = np.searchsorted(times, T)
    by_time = {}
    for i in range(len(T)):
        by_time.setdefault(int(tidx[i]), []).append(i)
    runs_at = {}
    for j, r in enumerate(runs):
        for e in range(r["i0"], r["i1"] + 1):
            runs_at.setdefault(e, []).append(j)
    for e, idxs in by_time.items():
        cands = runs_at.get(e, [])
        if not cands:
            return None, "时刻 e=%d 无任何可用时段" % e
        for i in idxs:
            js = [j for j in cands if cov[i, runs[j]["c"]]]
            if not js:
                return None, "实例 i=%d (t=%.0f) 无候选点覆盖" % (i, T[i])
            m.Add(sum(y[j] for j in js) >= 1)
    m.Minimize(sum(y) * 1000 + sum(int(occ[i][2] * 1000) * y[i] for i in range(len(runs))))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tlimit
    solver.parameters.num_search_workers = 8
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, "CP-SAT %s" % solver.StatusName(st)
    return [i for i in range(len(runs)) if solver.Value(y[i]) > 0.5], solver.StatusName(st)


def make_sorties(inst, chosen, T=None, times=None):
    rtype = inst.d["rtype"]
    order = sorted(chosen, key=lambda r: r["t0"])
    rd = {d: 0.0 for d in inst.d["rfleet"]}
    comp = {k: 0.0 for k in range(1, inst.d["rbatt"][0] + 1)}
    out = []
    for i, r in enumerate(order):
        rf = D.relay_flight(rtype, inst.nodes, r["lon"], r["lat"], r["agl"])
        t_ready = r["t0"]
        t_start = max(0.0, t_ready - rtype.t_link - rf["t_out"])
        t_end = r["t1"]
        t_back = t_end + rf["t_back"]
        hover = max(0.0, t_end - t_ready)
        e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
        e_tot = rf["e_fly"] + e_hover
        soc = 1.0 - e_tot / rtype.e_use
        chg = float(D.charge_time(soc, inst.d["rbatt"][1]))
        dr = min(rd, key=lambda k: (rd[k], k))
        cp = min(comp, key=lambda k: (comp[k], k))
        late = max(0.0, max(rd[dr], comp[cp]) - t_start)
        rd[dr] = t_back + rtype.t_turn + late
        comp[cp] = t_back + chg + late
        nreq = 0
        if T is not None and times is not None:
            ti = np.searchsorted(times, T)
            nreq = int(((ti >= r["i0"]) & (ti <= r["i1"])).sum())
        out.append(dict(rid=i + 1, drone=dr, comp="R-E%d" % cp, lon=r["lon"], lat=r["lat"],
                        ground=r["g"], hover_alt=r["g"] + r["agl"], agl=r["agl"],
                        t_depart=t_start + late, t_link_done=t_ready + late,
                        t_end=t_end + late, t_back=t_back + late, late=late,
                        e_fly=rf["e_fly"], e_hover=e_hover, e_total=e_tot, soc=soc, chg=chg,
                        n_req=nreq, dur=r["t1"] - r["t0"],
                        cov_start=r["i0"], cov_end=r["i1"]))
    return out


# ---------------------------------------------------------------------------
def plan_relay(inst, sol, assign, verbose=True, spacing=0.0050, agl=(100.0, 300.0),
               pad=0.020, min_len=60.0, tlimit=90.0, link=None):
    link = link or C.Link(inst)
    T, P, K, tmax = build_instances(inst, sol, assign, link)
    if len(T) == 0:
        return dict(ok=True, T=T, P=P, K=K, sorties=[], msg="无通信缺口")
    cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=spacing, pad=pad, agl=agl)
    cov_all, bh_ok, acc = R.coverage_matrix(link, P, cand)
    un = cov_all.sum(axis=1)
    if verbose:
        print("  需求实例 %d 个（%d 个不同时刻），候选点 %d（回传可用 %d），每实例平均可选 %.0f，最少 %d"
              % (len(T), len(np.unique(T)), len(cand), int(bh_ok.sum()), un.mean(), un.min()))
    if un.min() == 0:
        return dict(ok=False, msg="存在无候选点可覆盖的需求实例", T=T, P=P, K=K, cand=cand, meta=meta)
    pool = candidate_pool(T, cov_all)
    if verbose:
        print("  候选池 %d 个点" % len(pool))
    runs, times = runs_for(inst, T, K, cov_all, pool, meta, min_len=min_len)
    if verbose:
        print("  可用时段 %d 个" % len(runs))
    sel, st = select_runs(inst, runs, T, K, times, cov_all, pool,
                          len(inst.d["rfleet"]), tlimit=tlimit, verbose=verbose)
    if sel is None:
        return dict(ok=False, msg=st, T=T, P=P, K=K, cand=cand, meta=meta, runs=runs)
    chosen = [runs[i] for i in sel]
    sorties = make_sorties(inst, chosen, T, times)
    if verbose:
        print("  选中中继架次 %d 个（%s）" % (len(chosen), st))
    return dict(ok=True, T=T, P=P, K=K, cand=cand, meta=meta, cov=cov_all, runs=runs,
                times=times, chosen=chosen, sorties=sorties, msg=st, pool=pool)


def verify(inst, T, P, K, sorties, link=None):
    """逐实例校验覆盖（考虑中继实际可用时段与链路几何）。"""
    link = link or C.Link(inst)
    iv = [(s["t_link_done"], s["t_end"], (s["lon"], s["lat"], s["hover_alt"])) for s in sorties]
    miss = []
    for i in range(len(T)):
        t = T[i]
        act = [x for x in iv if x[0] - 1e-9 <= t <= x[1] + 1e-9]
        good = False
        for (a, b, pt) in act:
            a_ok, _, _ = link.access_ok(P[i:i + 1], pt)
            b_ok, _, _ = link.backhaul_ok(np.array([pt]))
            if a_ok[0] and b_ok[0]:
                good = True
                break
        if not good:
            miss.append((float(t), int(K[i]), bool(act)))
    return dict(n=len(T), miss=len(miss), sample=miss[:20], ok=(len(miss) == 0))
