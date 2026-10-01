# -*- coding: utf-8 -*-
"""
q3.py —— 问题三：通信约束下的运输与中继联合调度

两阶段联合优化
--------------
阶段一（运输—通信兼容化）：在问题二的 ALNS 目标中加入"通信兼容性"项
    Σ_架次 (该架次直连不可用时长中，**连最好的单个悬停点也无法覆盖**的部分)
该项由 cover_model.CoverModel 通过航段级缓存快速求值。把它压到 0，
意味着**每个架次的失联时段都能被一个固定悬停点覆盖**，从而整个任务期可以被切成
少数几个"相"，每相只用一个悬停点即可保障。

阶段二（中继接力调度）：在调色板候选点上做
    a) 每个点"独立可用时段"（能单独覆盖该时刻全部失联运输机的极大连续时段）；
    b) 一维区间覆盖贪心 ⇒ 最少相数（对固定候选集精确最优）；
    c) 两架中继交替接力：第 i 相与第 i+2 相由同一架承担，
       中间用"返回 O01 + 架次周转 + 再出动"的时间换取换位，
       因此要求第 i+1 相时长 >= t_back(p_i) + 周转 + t_out(p_{i+2}) + 建链时间；
    d) 生成中继架次并核算能耗、返航 SOC、能源组件周转。
"""
from __future__ import annotations

import os
import random
import time
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

import dcore as D
import comm as C
import relay as R
import q2 as Q
import solution_io as SIO

OUT = D.RESULTS
GRID = 10.0


# ---------------------------------------------------------------------------
# 阶段一：通信兼容化运输方案
# ---------------------------------------------------------------------------
def build_transport_all(inst, budget=150.0, cover_w=30.0, air_w=60.0, uncov_cap=2, seed=5,
                        verbose=True):
    """运行全部权重方案，返回候选列表 [(tag, sol, pol, met)]（供中继相位择优）。"""
    weights = [
        dict(name="C1-兼容优先", count=1.2, energy=1.5, makespan=1.5, tardy=2.0,
             cover=cover_w, air=air_w, uncov_cap=uncov_cap),
        dict(name="C2-兼顾", count=1.5, energy=2.0, makespan=1.5, tardy=4.0,
             cover=cover_w * 0.7, air=air_w, uncov_cap=uncov_cap),
        dict(name="C3-及时优先", count=1.0, energy=1.5, makespan=1.0, tardy=8.0,
             cover=cover_w * 0.8, air=air_w * 0.8, uncov_cap=uncov_cap),
        dict(name="C4-能耗优先", count=1.2, energy=4.0, makespan=1.5, tardy=2.0,
             cover=cover_w * 0.8, air=air_w, uncov_cap=uncov_cap),
        dict(name="C5-强兼容", count=1.0, energy=1.2, makespan=1.2, tardy=3.0,
             cover=cover_w * 1.6, air=air_w * 2.0, uncov_cap=uncov_cap),
    ]
    cm = Q._cover(inst)
    cands = []
    t0 = time.time()
    for k, w in enumerate(weights):
        sol, obj, met, it = Q.alns(inst, w, seed=seed + 13 * k, iters=30000,
                                   tlimit=max(20.0, budget / len(weights) - 6))
        pol = Q.polish(inst, sol, cpsat_limit=15.0, ls_iters=1800)
        m = dict(pol["met"])
        prof = cm.solution_profile(sol)
        m["uncov_time"] = sum(p["uncovered"] for p in prof)
        m["cover_left"] = sum(p["best_left"] for p in prof)
        m["cover_rate"] = 1.0 - m["cover_left"] / max(1.0, m["uncov_time"])
        ex, peak, tot = cm.uncovered_concurrency(sol, pol["assign"], cap=uncov_cap)
        m["uncov_excess"], m["uncov_peak"], m["uncov_total"] = ex, peak, tot
        key = (round(m["hard_violation"], 3), round(m["cover_left"], 1),
               round(m["uncov_excess"], 1), m["tardiness"], m["makespan"])
        if verbose:
            print("  %-12s 架次=%2d 能耗=%6.2f 完工=%6.0f 延误=%8.0f 硬违反=%6.0f "
                  "失联峰值=%d 并发超限=%6.0f s 失联=%7.0f s 单点可覆盖=%5.1f%%"
                  % (w["name"], m["count"], m["energy"], m["makespan"], m["tardiness"],
                     m["hard_violation"], m.get("uncov_peak", 0), m.get("uncov_excess", 0.0),
                     m["uncov_time"], 100 * m["cover_rate"]))
        cands.append((w["name"], sol, pol, m, key))
    if verbose:
        print("  候选运输方案 %d 个（用时 %.0f s）" % (len(cands), time.time() - t0))
    return cands


def build_transport(inst, budget=150.0, cover_w=30.0, air_w=60.0, uncov_cap=2, seed=5,
                    verbose=True):
    cands = build_transport_all(inst, budget, cover_w, air_w, uncov_cap, seed, verbose)
    cands.sort(key=lambda c: c[4])
    tag, sol, pol, m, _ = cands[0]
    if verbose:
        print("  按运输侧准则选中：%s  %s" % (tag, cands[0][4]))
    return sol, pol, tag, m


# ---------------------------------------------------------------------------
# 阶段二：中继接力调度
# ---------------------------------------------------------------------------
def relay_phases(inst, sol, assign, palette=None, link=None, grid=GRID, verbose=True,
                 spacing=0.0035, pad=0.024, agl=(80.0, 160.0, 300.0), min_phase_s=1400.0,
                 max_phase_s=5400.0, top_pair=70):
    """求覆盖全部失联时刻的悬停点—时段集合。

    候选悬停点采用**面向实际需求点的密集网格**（而非 CoverModel 的稀疏调色板），
    以保证每个失联实例都有可选点；随后做"独立可用时段 + 最少区间覆盖"。
    """
    link = link or C.Link(inst)
    T, P, K = [], [], []
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
        for c, v in agg.items():
            T.append(c * grid); P.append(v); K.append(k)
    if not T:
        return dict(ok=True, empty=True)
    o = np.argsort(T, kind="stable")
    T = np.array(T)[o]; P = np.array(P)[o]; K = np.array(K)[o]
    cells = np.unique((np.floor(T / grid) * grid).astype(np.int64))
    cid = np.searchsorted(cells, (np.floor(T / grid) * grid).astype(np.int64))
    groups = [np.nonzero(cid == k)[0] for k in range(len(cells))]
    # 候选悬停点：密集网格 + 回传链路可用
    cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=spacing, pad=pad, agl=agl)
    bh, blp, _ = link.backhaul_ok(cand)
    cand = cand[bh]
    if palette is not None and len(palette):
        cand = np.vstack([cand, np.asarray(palette, dtype=np.float64)])
    if verbose:
        print("  候选悬停点 %d 个（密集网格 %.4f° × %d 档离地高度 + 调色板）"
              % (len(cand), spacing, len(agl)))
    Pn = len(cand)
    cov = np.zeros((len(T), Pn), dtype=bool)
    for i in range(len(T)):
        lp, blk, d3 = link._loss(tuple(P[i]), cand, True)
        cov[i] = lp <= link.l_acc + 1e-9
    un = cov.sum(axis=1)
    if un.min() == 0:
        miss = np.nonzero(un == 0)[0]
        return dict(ok=False, kind="uncoverable",
                    msg="有 %d 个失联实例在密集候选集内仍无任何悬停点可见（首个 t=%.0f s）"
                        % (len(miss), T[miss[0]]),
                    T=T, P=P, K=K, cells=cells, cov=cov,
                    bad_t=[float(T[i]) for i in miss[:20]])
    alone = np.zeros((len(cells), Pn), dtype=bool)
    for k, g in enumerate(groups):
        alone[k] = cov[g].all(axis=0)
    bad = [k for k in range(len(cells)) if not alone[k].any()]
    if verbose:
        print("  需求实例 %d，时间格 %d（最多 %d 架同时失联），"
              "单点可覆盖格 %d，需双点格 %d，每实例平均可选 %.0f 点"
              % (len(T), len(cells), max(len(g) for g in groups),
                 len(cells) - len(bad), len(bad), un.mean()))
    # 独立可用极大时段（单点 + 双点配置）
    runs = []
    for j in range(Pn):
        idx = np.nonzero(alone[:, j])[0]
        if len(idx) == 0:
            continue
        brk = np.nonzero(np.diff(idx) > 1)[0]
        for s in np.split(idx, brk + 1):
            runs.append((int(s[0]), int(s[-1]), (int(j),)))
    # 双点配置：在"单点覆盖能力最强"的若干候选点之间枚举点对
    top = np.argsort(-alone.sum(axis=0))[:top_pair]
    top = [int(x) for x in top if alone[:, x].any()]
    pair_runs = 0
    for ai in range(len(top)):
        for bi in range(ai + 1, len(top)):
            a, b = top[ai], top[bi]
            u = alone[:, a] | alone[:, b]
            idx = np.nonzero(u)[0]
            if len(idx) == 0:
                continue
            brk = np.nonzero(np.diff(idx) > 1)[0]
            for s in np.split(idx, brk + 1):
                runs.append((int(s[0]), int(s[-1]), (a, b)))
                pair_runs += 1
    if verbose:
        print("  独立可用时段 %d 个（其中双点配置 %d 个，参与枚举的强点 %d 个）"
              % (len(runs), pair_runs, len(top)))
    # 区间覆盖贪心：优先选择"从当前格起可独立覆盖 >= Tmin"的时段（保证双机接力来得及），
    # 若无此时段则退化为最长延长。
    Tmin_cells = max(1, int(round(min_phase_s / grid)))
    max_phase_cells = max(Tmin_cells, int(round(max_phase_s / grid)))
    n = len(cells)
    import heapq
    heap_long, heap_all = [], []
    ptr = 0
    runs_sorted = sorted(runs, key=lambda r: (r[0], -(r[1] - r[0])))
    intervals = []
    k = 0
    multi = 0
    while k < n:
        while ptr < len(runs_sorted) and runs_sorted[ptr][0] <= k:
            i0, i1, js = runs_sorted[ptr]
            heapq.heappush(heap_all, (-i1, js))
            if i1 - k + 1 >= Tmin_cells:
                heapq.heappush(heap_long, (-i1, js))
            ptr += 1
        while heap_all and -heap_all[0][0] < k:
            heapq.heappop(heap_all)
        while heap_long and -heap_long[0][0] < k:
            heapq.heappop(heap_long)
        use = heap_long if heap_long else heap_all
        if use and -use[0][0] >= k:
            e, js = -use[0][0], use[0][1]
            # 相位时长上限：中继单次悬停受能源组件容量限制，过长必须回 O01 换组件
            emax = k + max_phase_cells - 1
            if e > emax:
                e = emax
            intervals.append((k, e, tuple(js)))
            if len(js) > 1:
                multi += 1
            k = e + 1
            continue
        # 需要多点：从实例覆盖集里做小规模集合覆盖
        sub = cov[groups[k]]
        rem = np.ones(sub.shape[0], dtype=bool)
        js = []
        while rem.any() and len(js) < 3:
            gains = sub[np.nonzero(rem)[0]].sum(axis=0)
            c = int(np.argmax(gains))
            if gains[c] == 0:
                break
            js.append(c)
            rem = rem & (~sub[:, c])
        if rem.any():
            return dict(ok=False, kind="uncoverable",
                        msg="cell %d（t=%.0f s）有运输机在任何候选悬停点上均不可见" % (k, cells[k]),
                        T=T, P=P, K=K, cells=cells, cov=cov,
                        bad_inst=[int(i) for i in np.nonzero(rem)[0]])
        i0 = i1 = k
        while i1 + 1 < n and cov[groups[i1 + 1]][:, js].any(axis=1).all():
            i1 += 1
        intervals.append((i0, i1, tuple(js)))
        multi += 1
        k = i1 + 1
    # 合并相邻同点区间
    merged = []
    for iv in intervals:
        if merged and merged[-1][2] == iv[2] and iv[0] <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], iv[1], iv[2])
        else:
            merged.append((iv[0], iv[1], iv[2]))
    # 清理过短相位：短相会使"下一相"来不及换位（中继回 O01 + 周转 + 再出动约 20 min），
    #   (a) 若上一相的**任一点位**能单独覆盖本相，则并入上一相（同机续驻，无需换位）；
    #   (b) 若存在**单点**覆盖两相并集，则合并为单点相（保留后续可合并性）；
    #   (c) 否则合并两点集（并集 <= 2 个悬停点即可行）。
    pref = np.zeros((Pn, len(cells) + 1), dtype=np.int32)
    for j in range(Pn):
        pref[j, 1:] = np.cumsum(~alone[:, j])

    def single_cover(k0, k1):
        hit = np.nonzero(pref[:, k1 + 1] - pref[:, k0] == 0)[0]
        return int(hit[0]) if len(hit) else None

    changed = True
    guard = 0
    while changed and len(merged) > 1 and guard < 400:
        changed = False
        guard += 1
        for i in range(len(merged)):
            dur = merged[i][1] - merged[i][0] + 1
            if dur >= Tmin_cells:
                continue
            # (a) 并入上一相（尝试上一相的全部点位）
            if i > 0:
                done = False
                for c in merged[i - 1][2]:
                    if all(alone[kk, c] for kk in range(merged[i][0], merged[i][1] + 1)):
                        merged[i - 1:i + 1] = [(merged[i - 1][0], merged[i][1], merged[i - 1][2])]
                        changed = True
                        done = True
                        break
                if done:
                    break
            # (a') 并入下一相（下一相的任一点位单独覆盖本相）
            if i + 1 < len(merged):
                done = False
                for c in merged[i + 1][2]:
                    if all(alone[kk, c] for kk in range(merged[i][0], merged[i][1] + 1)):
                        merged[i:i + 2] = [(merged[i][0], merged[i + 1][1], merged[i + 1][2])]
                        changed = True
                        done = True
                        break
                if done:
                    break
            # (b)/(c) 与相邻相合并
            for j in ([i + 1] if i + 1 < len(merged) else []) + ([i - 1] if i > 0 else []):
                k0, k1 = min(merged[i][0], merged[j][0]), max(merged[i][1], merged[j][1])
                sc = single_cover(k0, k1)
                uni = tuple(sorted(set(merged[i][2]) | set(merged[j][2])))
                if sc is not None:
                    newpts = (sc,)
                elif len(uni) <= 2:
                    newpts = uni
                else:
                    continue
                lo, hi = min(i, j), max(i, j)
                merged[lo:hi + 1] = [(merged[lo][0], merged[hi][1], newpts)]
                changed = True
                break
            if changed:
                break
    if verbose:
        durs = [(r[1] - r[0] + 1) * grid for r in merged]
        print("  相数 = %d（多点相 %d），最短相 %.0f s，最长相 %.0f s，"
              "短于 %.0f s 的相 %d 个"
              % (len(merged), sum(1 for r in merged if len(r[2]) > 1),
                 min(durs), max(durs), min_phase_s, sum(1 for d in durs if d < min_phase_s)))
    return dict(ok=True, T=T, P=P, K=K, cells=cells, cov=cov, alone=alone,
                intervals=merged, palette=cand, groups=groups, link=link)


def schedule_relay(inst, ph, verbose=True, strict=False):
    """两架中继接力排程；核算时序、能耗、SOC、能源组件周转。

    接力规则：某相的中继必须能在该相开始前到达并完成建链，否则：
      (a) 若上一相的中继所在悬停点仍能**单独覆盖**本相全部需求，则让它延展驻留
          （物理上可行的"接力保障"）；
      (b) strict=True 时本相不派中继，如实记为通信中断；否则按最早可用强行安排并告警。
    """
    rtype = inst.d["rtype"]
    cells = ph["cells"]; palette = ph["palette"]; intervals = ph["intervals"]
    alone = ph["alone"]
    dem = D.get_dem()
    ivs = sorted(intervals, key=lambda r: r[0])
    out, warn, outage = [], [], []
    free = {0: 0.0, 1: 0.0}
    last = {0: None, 1: None}          # 各中继最近一个架次记录

    def geom(j):
        lo, la, alt = palette[j]
        agl = float(alt) - float(dem.at(lo, la))
        rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
        return lo, la, float(alt), agl, rf

    def covers_phase(j, k0, k1):
        return bool(alone[k0:k1 + 1, j].all())

    def emit(slot, j, t0, t1):
        lo, la, alt, agl, rf = geom(j)
        hover = max(0.0, t1 - t0)
        e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
        e_tot = rf["e_fly"] + e_hover
        soc = 1.0 - e_tot / rtype.e_use
        rec = dict(slot=slot, j=j, lon=lo, lat=la, ground=float(dem.at(lo, la)), agl=agl,
                   hover_alt=alt, t_link_done=t0, t_end=t1, hover=hover, t_out=rf["t_out"],
                   t_back=rf["t_back"], e_fly=rf["e_fly"], e_hover=e_hover, e_total=e_tot,
                   soc=soc, chg=float(D.charge_time(soc, inst.d["rbatt"][1])))
        out.append(rec)
        free[slot] = t1 + rf["t_back"] + rtype.t_turn
        last[slot] = rec
        return rec

    def extend(rec, t1):
        ext = t1 - rec["t_end"]
        if ext <= 0:
            return
        rec["t_end"] = t1
        rec["hover"] += ext
        rec["e_hover"] = (rtype.p_hover + rtype.p_comm) * rec["hover"] / 3600.0
        rec["e_total"] = rec["e_fly"] + rec["e_hover"]
        rec["soc"] = 1.0 - rec["e_total"] / rtype.e_use
        rec["chg"] = float(D.charge_time(rec["soc"], inst.d["rbatt"][1]))
        free[rec["slot"]] = rec["t_end"] + rec["t_back"] + rtype.t_turn

    for i, iv in enumerate(ivs):
        t0 = float(cells[iv[0]]); t1 = float(cells[iv[1]])
        js = list(iv[2])
        need = {}
        for j in js:
            lo, la, alt, agl, rf = geom(j)
            need[j] = rf["t_out"] + rtype.t_link
        ready = [s for s in (0, 1) if all(free[s] + need[j] <= t0 + 1e-6 for j in js)]
        if len(js) == 1 and ready:
            slots = [min(ready, key=lambda s: free[s])]
        elif len(js) == 2 and len(ready) == 2:
            slots = [0, 1]
        else:
            slots = []
        if len(slots) < len(js):
            # (a) 延展接力：上一相的中继点位若能单独覆盖本相，则继续驻留
            rescued = False
            for s in (0, 1):
                rec = last[s]
                if rec is None or rec["t_end"] >= t1 - 1e-6:
                    continue
                if covers_phase(rec["j"], iv[0], iv[1]):
                    extend(rec, t1)
                    warn.append(dict(idx=i, t0=t0, reason="由上一相中继延展保障",
                                     slot=s, extended=round(t1 - t0, 1)))
                    rescued = True
                    break
            if len(js) == 1 and (ready or rescued):
                slots = [min((0, 1), key=lambda s: free[s])]
            elif len(js) == 2 and rescued:
                slots = [0, 1]
            elif strict:
                # 严格模式：无法按时到位则本相不派中继，如实记为通信中断
                outage.append(dict(idx=i, t0=t0, t1=t1,
                                   reason="无中继可按时到位（相位 %.0f s）" % (t1 - t0)))
                continue
            else:
                slots = sorted((0, 1), key=lambda s: free[s])[:len(js)]
                warn.append(dict(idx=i, t0=t0, reason="中继未就绪（相位过短或换位不及）",
                                 free={k: round(v, 1) for k, v in free.items()}))
        for slot, j in zip(slots, js):
            emit(slot, j, t0, t1)
    # 合并同一中继上时间相邻且同点位的架次
    merged_out = []
    for s in sorted(out, key=lambda r: (r["slot"], r["t_link_done"])):
        if merged_out and merged_out[-1]["slot"] == s["slot"] and merged_out[-1]["j"] == s["j"] \
                and s["t_link_done"] <= merged_out[-1]["t_end"] + 2 * GRID:
            m = merged_out[-1]
            m["t_end"] = max(m["t_end"], s["t_end"])
            m["hover"] = m["t_end"] - m["t_link_done"]
            m["e_hover"] = (rtype.p_hover + rtype.p_comm) * m["hover"] / 3600.0
            m["e_total"] = m["e_fly"] + m["e_hover"]
            m["soc"] = 1.0 - m["e_total"] / rtype.e_use
            m["chg"] = float(D.charge_time(m["soc"], inst.d["rbatt"][1]))
            m["t_back"] = m["t_end"] + geom(m["j"])[4]["t_back"]
        else:
            merged_out.append(dict(s))
    out = merged_out
    # 时序检查：同一中继的架次占用 [depart, back] + 周转
    for slot in (0, 1):
        seq = sorted([s for s in out if s["slot"] == slot], key=lambda s: s["t_link_done"])
        fr = 0.0
        for s in seq:
            depart = max(0.0, s["t_link_done"] - s["t_out"] - inst.d["rtype"].t_link)
            if depart < fr - 1e-6:
                warn.append(dict(slot=slot, t=s["t_link_done"], need=round(depart, 1),
                                 free=round(fr, 1), gap=round(fr - depart, 1)))
            fr = max(fr, s["t_end"] + s["t_back"] + inst.d["rtype"].t_turn)
    # 能耗检查
    for s in out:
        cap = (1 - rtype.rho) * rtype.e_use
        if s["e_total"] > cap + 1e-9:
            warn.append(dict(slot=s["slot"], t=s["t_link_done"], reason="返航电量不足",
                             e=s["e_total"], cap=cap))
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for r, s in enumerate(out, 1):
        s["rid"] = r
        s["drone"] = inst.d["rfleet"][s["slot"]]
        s["comp"] = "R-E%d" % (((r - 1) % inst.d["rbatt"][0]) + 1)
    if verbose:
        print("  中继架次 %d 个，时序/能量告警 %d 条，未派中继的相 %d 个（合计 %.0f s）"
              % (len(out), len(warn), len(outage), sum(o["t1"] - o["t0"] for o in outage)))
        for w in warn[:8]:
            print("    !", w)
    return out, warn, outage


def verify(inst, ph, sorties, link=None):
    link = link or C.Link(inst)
    iv = [(s["t_link_done"], s["t_end"], (s["lon"], s["lat"], s["hover_alt"])) for s in sorties]
    miss = []
    for i in range(len(ph["T"])):
        t = ph["T"][i]
        act = [x for x in iv if x[0] - 1e-9 <= t <= x[1] + 1e-9]
        good = False
        for (a, b, pt) in act:
            a_ok, _, _ = link.access_ok(ph["P"][i:i + 1], pt)
            b_ok, _, _ = link.backhaul_ok(np.array([pt]))
            if a_ok[0] and b_ok[0]:
                good = True
                break
        if not good:
            miss.append((float(t), int(ph["K"][i]), bool(act)))
    return dict(n=len(ph["T"]), miss=len(miss), sample=miss[:10], ok=(len(miss) == 0))


# ---------------------------------------------------------------------------
def n_blocks(sol):
    """运输方案的"不可分割块"数（同一架次服务的服务区互相耦合）。"""
    par = {}

    def find(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    for s in sol:
        ars = list(s.areas)
        for a in ars:
            find(a)
        for a in ars[1:]:
            uni(ars[0], a)
    return len({find(k) for k in par})


def solve(inst=None, budget=150.0, cover_w=30.0, air_w=60.0, uncov_cap=2, verbose=True,
          save=True, min_phase_s=1400.0, max_phase_s=5400.0, min_blocks=3):
    """在全部候选运输方案上分别做中继相位评估，选"相位结构最健康"的方案作为最终解。
    min_blocks：要求运输方案的不可分割块数不少于该值（问题四需划分 2 组与 3 组）。"""
    inst = inst or Q.Instance()
    cands = build_transport_all(inst, budget=budget, cover_w=cover_w, air_w=air_w,
                                uncov_cap=uncov_cap, verbose=verbose)
    best = None
    for tag, sol, pol, m, tkey in cands:
        if m["hard_violation"] > 1e-6:
            continue
        nb = n_blocks(sol)
        if nb < min_blocks:
            if verbose:
                print("  %-12s 不可分割块数 %d < %d，跳过（问题四需 2/3 分区）" % (tag, nb, min_blocks))
            continue
        try:
            ph = relay_phases(inst, sol, pol["assign"], Q._cover(inst).palette, link=None,
                              verbose=False, min_phase_s=min_phase_s, max_phase_s=max_phase_s)
        except Exception as e:
            if verbose:
                print("  %-12s 中继相位求解异常：%s" % (tag, e))
            continue
        if not ph.get("ok"):
            if verbose:
                print("  %-12s 中继相位不可行：%s" % (tag, ph.get("msg")))
            continue
        ss, warn, outage = schedule_relay(inst, ph, verbose=False, strict=True)
        v = verify(inst, ph, ss)
        viol = len([w for w in warn if "gap" in w or "未就绪" in w])
        durs = [(r[1] - r[0] + 1) * GRID for r in ph["intervals"]]
        short = sum(1 for d in durs if d < min_phase_s)
        score = (len(outage), 0 if v["ok"] else 1, -nb, viol, short, len(ss),
                 m["tardiness"], m["makespan"])
        if verbose:
            print("  %-12s 块数=%d 相数=%2d 短相=%2d 中继架次=%2d 未覆盖=%d 未派中继相=%d(%.0f s)"
                  % (tag, nb, len(ph["intervals"]), short, len(ss), v["miss"], len(outage),
                     sum(o["t1"] - o["t0"] for o in outage)))
        if best is None or score < best[0]:
            best = (score, tag, sol, pol, m, ph, ss, warn, v, outage)
    if best is None:
        return dict(ok=False, msg="所有候选运输方案均无法完成中继相位规划")
    _, tag, sol, pol, m, ph, ss, warn, v, outage = best
    pol = dict(pol); pol["met"] = m
    if verbose:
        print("  最终选择：%s  评分 %s" % (tag, best[0]))
        print("  逐实例覆盖校验：未覆盖 %d / %d  %s" % (v["miss"], v["n"],
                                                        "OK" if v["ok"] else "不通过"))
    res = dict(ok=v["ok"], sol=sol, pol=pol, ph=ph, sorties=ss, warn=warn, verify=v,
               outage=outage, scheme=tag, cover_w=cover_w)
    if save and ss:
        save_solution(inst, res)
    return res


def save_solution(inst, res):
    sol, pol, ss = res["sol"], res["pol"], res["sorties"]
    solj = SIO.load() if os.path.exists(SIO.SOL_JSON) else {}
    tr = SIO.transport_from_sorties(inst, sol, pol["assign"], code_prefix="Q2")
    rtype = inst.d["rtype"]
    relay = []
    for i, s in enumerate(ss, 1):
        relay.append(dict(
            sid="Q3-R-%02d" % i, drone=s["drone"], comp=s["comp"],
            lon=float(s["lon"]), lat=float(s["lat"]),
            hover_alt=float(s["hover_alt"]), agl=float(s["agl"]), ground=float(s["ground"]),
            depart=float(max(0.0, s["t_link_done"] - s["t_out"] - rtype.t_link)),
            link_done=float(s["t_link_done"]), end=float(s["t_end"]),
            back=float(s["t_end"] + s["t_back"]),
            e_fly=float(s["e_fly"]), e_hover=float(s["e_hover"]),
            e_total=float(s["e_total"]), soc=float(s["soc"]), chg=float(s["chg"]),
            hover=float(s["hover"]), phase=int(s.get("iv_idx", i - 1))))
    solj.update(dict(
        meta=dict(rho=inst.rho, makespan=pol["makespan"], energy=sum(x.E for x in sol),
                  n_transport=len(sol), polish=pol["tag"], scheme=res["scheme"],
                  tardiness=pol["met"]["tardiness"],
                  ontime_rate=pol["met"]["ontime_rate"],
                  hard_violation=pol["met"]["hard_violation"],
                  nbox=len(inst.boxes),
                  relay_energy=sum(s["e_total"] for s in ss), n_relay=len(ss),
                  relay_hover=sum(s["hover"] for s in ss),
                  joint_makespan=max([pol["makespan"]] + [s["t_back"] + s["t_end"] for s in ss]),
                  uncov_time=pol["met"].get("uncov_time"),
                  cover_rate=pol["met"].get("cover_rate"),
                  uncov_peak=pol["met"].get("uncov_peak"),
                  uncov_excess=pol["met"].get("uncov_excess"),
                  comm_ok=bool(res["verify"]["ok"]),
                  comm_miss=int(res["verify"]["miss"]),
                  relay_outage_s=float(sum(o["t1"] - o["t0"] for o in res.get("outage", []))),
                  relay_outage_n=int(len(res.get("outage", [])))),
        transport=tr, relay=relay, coverage=[]))
    SIO.save(solj)
    return SIO.SOL_JSON


if __name__ == "__main__":
    t0 = time.time()
    r = solve(budget=150.0, cover_w=30.0)
    print("ok=%s msg=%s 用时 %.0f s" % (r["ok"], r.get("msg"), time.time() - t0))
    if r["ok"]:
        for s in r["sorties"]:
            print("  #%02d %s %s (%.5f,%.5f) 海拔%.0f 离地%.0f 建链%.0f 结束%.0f 返回%.0f "
                  "悬停%5.0f E=%.3f SOC=%.1f%%"
                  % (s["rid"], s["drone"], s["comp"], s["lon"], s["lat"], s["hover_alt"],
                     s["agl"], s["t_link_done"], s["t_end"], s["t_end"] + s["t_back"],
                     s["hover"], s["e_total"], 100 * s["soc"]))
