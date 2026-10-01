# -*- coding: utf-8 -*-
"""
q3sched.py —— 中继保障调度（最少区间覆盖 + 双机接力）

思路
----
1. 候选悬停点 c 的"独立可用时段" = 该点能**单独**覆盖全部通信需求的极大连续时段。
2. 一维区间覆盖贪心 ⇒ 用最少的独立可用时段覆盖全部需求时刻（对固定候选集是精确最优）。
3. 少数时刻需要多点同时保障（多机同时失联且无单点可同时看见），用"多点配置"覆盖。
4. 相邻区间的接力：第 i 个区间由 R01/R02 交替承担；某架换位期间由另一架独立保障。
5. 每个区间 ⇒ 一个中继架次；核算往返飞行能耗、悬停-通信能耗、返航 SOC 与充电周转。
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

import dcore as D
import comm as C
import relay as R


def single_runs(alone):
    """对全部候选点求独立可用极大时段。alone: (n_cell, n_cand) bool。"""
    n, m = alone.shape
    runs = []
    for j in range(m):
        col = alone[:, j]
        idx = np.nonzero(col)[0]
        if len(idx) == 0:
            continue
        brk = np.nonzero(np.diff(idx) > 1)[0]
        segs = np.split(idx, brk + 1)
        for s in segs:
            runs.append((int(s[0]), int(s[-1]), int(j)))
    return runs


def greedy_cover(alone, runs):
    """最少区间覆盖（贪心，对固定区间集精确最优）。返回 (选中区间列表, 首个无法覆盖的 cell)。"""
    n = alone.shape[0]
    start_at = {}
    for (i0, i1, j) in runs:
        start_at.setdefault(i0, []).append((i1, j))
    best_end = np.full(n, -1, dtype=np.int64)
    best_j = np.full(n, -1, dtype=np.int64)
    cur_end, cur_j = -1, -1
    for k in range(n):
        for (i1, j) in start_at.get(k, []):
            if i1 > cur_end:
                cur_end, cur_j = i1, j
        best_end[k], best_j[k] = cur_end, cur_j
    chosen = []
    k = 0
    while k < n:
        e, j = int(best_end[k]), int(best_j[k])
        if e < k or j < 0:
            return chosen, k
        chosen.append((k, e, j))
        k = e + 1
    return chosen, None


def cover_cell(dat, k, max_k=3, pool_limit=40):
    """对 cell k 求覆盖其全部需求实例的最小候选点集合（<= max_k）。"""
    g = dat["groups"][k]
    sub = dat["cov_pool"][g].copy()
    gains = sub.sum(axis=0)
    order = list(np.argsort(-gains)[:pool_limit])
    # 尝试 1、2、3 点
    for size in range(1, max_k + 1):
        sol = _search(sub, order, size)
        if sol is not None:
            return sol
    return None


def _search(sub, order, size):
    import itertools
    for combo in itertools.combinations(order, size):
        m = np.ones(sub.shape[0], dtype=bool)
        for j in combo:
            m &= (~sub[:, j])
        if not m.any():
            return [int(j) for j in combo]
    return None


def max_run_with(dat, k, js):
    """候选点集合 js 能覆盖 cell k 起（并向前）的最长连续段。"""
    n = dat["alone"].shape[0]
    cov = dat["cov_pool"]
    def ok_at(cell):
        g = dat["groups"][cell]
        sub = cov[g]
        m = np.zeros(sub.shape[0], dtype=bool)
        for j in js:
            m |= sub[:, j]
        return bool(m.all())
    i0 = i1 = k
    c = k
    while c + 1 < n and ok_at(c + 1):
        c += 1
        i1 = c
    c = k
    while c - 1 >= 0 and ok_at(c - 1):
        c -= 1
        i0 = c
    return (i0, i1, tuple(js))


def schedule(inst, dat, intervals, verbose=True):
    """交替分配中继无人机，检查接力可行性，生成中继架次。"""
    rtype = inst.d["rtype"]
    cells = dat["cells"]
    meta = dat["meta"]
    pool = dat["pool"]
    relay_free = {d: 0.0 for d in inst.d["rfleet"]}
    out, bad = [], []
    for idx, iv in enumerate(intervals):
        t0 = float(cells[iv[0]])
        t1 = float(cells[iv[1]])
        js = list(iv[2])
        ds = sorted(relay_free, key=lambda d: relay_free[d])
        used = ds[:len(js)]
        ready = max(relay_free[d] for d in used)
        if ready > t0 + 1e-6:
            bad.append(dict(idx=idx, t0=t0, ready=ready, reason="中继无人机未就绪（需 %.0f s）" % (ready - t0)))
        for j, dr in zip(js, used):
            c = pool[j]
            lo, la, g, agl = meta[c]
            rf = D.relay_flight(rtype, inst.nodes, lo, la, agl)
            t_start = max(0.0, t0 - rtype.t_link - rf["t_out"])
            hover = max(0.0, t1 - t0)
            e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
            e_tot = rf["e_fly"] + e_hover
            soc = 1.0 - e_tot / rtype.e_use
            chg = float(D.charge_time(soc, inst.d["rbatt"][1]))
            relay_free[dr] = t1 + rf["t_back"] + rtype.t_turn
            out.append(dict(rid=0, drone=dr, lon=lo, lat=la, ground=g, agl=agl,
                            hover_alt=g + agl, t_depart=t_start, t_link_done=t0, t_end=t1,
                            t_back=t1 + rf["t_back"], e_fly=rf["e_fly"], e_hover=e_hover,
                            e_total=e_tot, soc=soc, chg=chg, iv_idx=idx))
    out.sort(key=lambda s: (s["t_link_done"], s["drone"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out, bad


def check_relay_energy(inst, sorties):
    rtype = inst.d["rtype"]
    bad = []
    for s in sorties:
        if s["soc"] < rtype.rho - 1e-9:
            bad.append(dict(rid=s["rid"], reason="返航电量不足", soc=round(s["soc"], 4)))
        hover = s["t_end"] - s["t_link_done"]
        cap = (1 - rtype.rho) * rtype.e_use - s["e_fly"]
        need = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
        if need > cap + 1e-9:
            bad.append(dict(rid=s["rid"], reason="悬停通信能耗超限",
                            hover=round(hover, 1), need=round(need, 4), cap=round(cap, 4)))
    return bad


def relay_energy_summary(inst, sorties):
    return dict(n=len(sorties),
                e_fly=sum(s["e_fly"] for s in sorties),
                e_hover=sum(s["e_hover"] for s in sorties),
                e_total=sum(s["e_total"] for s in sorties),
                hover_total=sum(s["t_end"] - s["t_link_done"] for s in sorties),
                drones=sorted({s["drone"] for s in sorties}),
                comps=sorted({s["comp"] for s in sorties}))
