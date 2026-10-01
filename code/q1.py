# -*- coding: utf-8 -*-
"""
q1.py —— 问题一：单点往返运输能力与货箱组批方案

(1) 三种机型在 15 个服务区的最大安全载荷（二分精确）
(2) 货箱不可拆分、单服务区组批的可行组批方案
(3) 架次数 / 总运输能耗 / 累计作业时间的精确 Pareto 前沿与权衡
(4) 返航安全余量 rho 的灵敏度分析

精确性说明
----------
同一服务区内同（物资类型, 单箱质量, 单箱体积）的货箱完全可互换，因此状态只需记录
各类货箱的剩余数量，状态空间从 2^n 降为 Π(c_k+1)（最大 3×9×4×3=324），
在该状态空间上做多目标（架次数, 能耗, 作业时间）DP 并逐状态剪枝非支配解，
所得 Pareto 前沿对原问题仍是**精确**的。

"累计作业时间"定义：所有架次作业时长之和（总工时）；同时报告单架次最长时长。
"""
from __future__ import annotations

import itertools
import json
import os
import numpy as np
import pandas as pd

import dcore as D

OUT = D.RESULTS
os.makedirs(OUT, exist_ok=True)
EPS_E = 5e-4      # kWh 剪枝容差
EPS_T = 0.5       # s   剪枝容差


# ---------------------------------------------------------------------------
# 单架次（单服务区往返）物理量
# ---------------------------------------------------------------------------
def sortie_single(nodes, dt, sid, q):
    """O01 -> sid -> O01，去程载荷 q、回程 0。返回 (E[kWh], T[s], legs)。"""
    E, legs = D.sortie_energy(nodes, dt, ["O01", sid, "O01"], [q, 0.0])
    T = dt.t_prep + dt.t_load_box + sum(L.t_flight for L in legs) + dt.t_hand_base + dt.t_hand_box
    return E, T, legs


def max_safe_payload(nodes, dt, sid, rho, tol=1e-3):
    """最大安全载荷 = min(q_max, 返航安全余量所允许的载荷上限)。"""
    lim = (1 - rho) * dt.e_use
    E0, _, _ = sortie_single(nodes, dt, sid, 0.0)
    if E0 > lim:
        return 0.0, E0
    Ehi, _, _ = sortie_single(nodes, dt, sid, dt.q_max)
    if Ehi <= lim:
        return dt.q_max, Ehi
    lo, hi = 0.0, dt.q_max
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if sortie_single(nodes, dt, sid, mid)[0] <= lim:
            lo = mid
        else:
            hi = mid
    E, _, _ = sortie_single(nodes, dt, sid, lo)
    return lo, E


# ---------------------------------------------------------------------------
# 单服务区精确多目标 DP
# ---------------------------------------------------------------------------
def _prune(plist):
    """对 (count, E, T, parts) 列表做非支配剪枝（先粗化再支配判定）。"""
    if len(plist) <= 1:
        return plist
    plist = sorted(plist, key=lambda x: (x[0], x[1], x[2]))
    out = []
    for p in plist:
        dom = False
        for q in out:
            if (q[0] <= p[0] and q[1] <= p[1] + EPS_E and q[2] <= p[2] + EPS_T):
                dom = True
                break
        if not dom:
            out.append(p)
    return out


def area_pareto(bx, nodes, types, rho, max_pareto=400):
    """返回该服务区的 Pareto 列表：[(架次数, 总能耗, 总作业时间, [(机型, {箱编号})...])]。"""
    sid = bx[0].sid
    groups = sorted({(b.kind, b.mass, b.vol) for b in bx})
    ids = {g: sorted(b.bid for b in bx if (b.kind, b.mass, b.vol) == g) for g in groups}
    caps = tuple(len(ids[g]) for g in groups)
    K = len(groups)

    # 所有可行的"单架次装箱构成"及其机型选项
    comps = []
    for combo in itertools.product(*[range(c + 1) for c in caps]):
        if sum(combo) == 0:
            continue
        mass = float(sum(combo[i] * groups[i][1] for i in range(K)))
        vol = float(sum(combo[i] * groups[i][2] for i in range(K)))
        opts = []
        for g in ("A", "B", "C"):
            dt = types[g]
            if mass > dt.q_max + 1e-9 or vol > dt.v_cap + 1e-9:
                continue
            e, t, _ = sortie_single(nodes, dt, sid, mass)
            if e <= (1 - rho) * dt.e_use + 1e-12:
                opts.append((g, e, t, mass, vol))
        if not opts:
            continue
        # 机型之间也做非支配剪枝
        opts = [o for o in opts if not any(
            (p[0] != o[0] or True) and p[1] <= o[1] + EPS_E and p[2] <= o[2] + EPS_T and
            (p[1] < o[1] - EPS_E or p[2] < o[2] - EPS_T) for p in opts)]
        comps.append((combo, mass, vol, opts))

    states = sorted(itertools.product(*[range(c + 1) for c in caps]), key=sum)
    zero = (0,) * K
    par = {zero: [(0, 0.0, 0.0, [])]}
    for s in states:
        if s == zero:
            continue
        cur = []
        for combo, mass, vol, opts in comps:
            if any(combo[i] > s[i] for i in range(K)):
                continue
            prev = tuple(s[i] - combo[i] for i in range(K))
            base = par.get(prev)
            if not base:
                continue
            for (c0, e0, t0, parts) in base:
                for (g, e, t, m, v) in opts:
                    cur.append((c0 + 1, e0 + e, t0 + t, parts + [(g, combo, m, v)]))
        par[s] = _prune(cur)[:max_pareto]
    sol = par[caps]

    out = []
    for (c, e, t, parts) in sol:
        recs = []
        used = [0] * K
        for k, (g, combo, m, v) in enumerate(parts):
            bids = []
            for i in range(K):
                for _ in range(combo[i]):
                    bids.append(ids[groups[i]][used[i]])
                    used[i] += 1
            recs.append(dict(sid=sid, g=g, bids=bids, mass=m, vol=v,
                             E=_type_energy(nodes, types[g], sid, m),
                             T=_type_time(nodes, types[g], sid, m)))
        out.append(dict(count=c, E=e, T=t, sorties=recs))
    # 去重
    seen = set()
    uniq = []
    for o in out:
        key = (o["count"], round(o["E"], 3), round(o["T"], 1))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(o)
    return uniq


def _type_energy(nodes, dt, sid, q):
    return sortie_single(nodes, dt, sid, q)[0]


def _type_time(nodes, dt, sid, q):
    return sortie_single(nodes, dt, sid, q)[1]


# ---------------------------------------------------------------------------
# 全场景组合
# ---------------------------------------------------------------------------
def combine(area_par, weights):
    """给定 (w_count, w_E, w_T)，逐服务区独立取最优（问题一各服务区解耦），返回全局方案。"""
    wc, we, wt = weights
    tot = dict(count=0, E=0.0, T=0.0)
    picked = {}
    for sid, lst in area_par.items():
        if not lst:
            return None, None
        best = min(lst, key=lambda o: wc * o["count"] + we * o["E"] + wt * o["T"])
        picked[sid] = best
        tot["count"] += best["count"]
        tot["E"] += best["E"]
        tot["T"] += best["T"]
    return tot, picked


def pareto_front(area_par, n_grid=26):
    """权重单纯形扫描 → 全局 Pareto 前沿（(架次数, 总能耗, 总作业时间)）。"""
    cands = []
    for i in range(n_grid + 1):
        for j in range(n_grid + 1 - i):
            k = n_grid - i - j
            cands.append((i / n_grid, j / n_grid, k / n_grid))
    triples = {}
    for w in cands:
        tot, picked = combine(area_par, w)
        if tot is None:
            continue
        key = (tot["count"], round(tot["E"], 3), round(tot["T"], 1))
        triples.setdefault(key, (tot, picked))
    arr = sorted(triples.values(), key=lambda x: (x[0]["count"], x[0]["E"], x[0]["T"]))
    front = []
    for tot, picked in arr:
        if any((o["count"] <= tot["count"] and o["E"] <= tot["E"] + 1e-6 and o["T"] <= tot["T"] + 1e-6)
               and (o["count"], o["E"], o["T"]) != (tot["count"], tot["E"], tot["T"]) for o, _ in front):
            continue
        front.append((tot, picked))
    return front


# ---------------------------------------------------------------------------
def solve(rho=None, verbose=True):
    d = D.load_all()
    nodes, types, boxes = d["nodes"], d["ttypes"], d["boxes"]
    rho = types["A"].rho if rho is None else rho
    SIDS = d["SIDS"]

    # ---- (1) 最大安全载荷 ----
    rows = []
    for sid in SIDS:
        for g in ("A", "B", "C"):
            dt = types[g]
            q, e = max_safe_payload(nodes, dt, sid, rho)
            rows.append(dict(服务区编号=sid, 机型编号=g, 最大载货质量_kg=dt.q_max,
                             最大安全载荷_kg=round(q, 3), 是否受能量限制=(q < dt.q_max - 1e-6),
                             该载荷往返能耗_kWh=round(e, 4), 单组电池可用能量_kWh=dt.e_use,
                             返航安全余量比例=rho))
    q1a = pd.DataFrame(rows)

    # ---- (2)(3) 逐服务区 Pareto ----
    area_par = {}
    for sid in SIDS:
        bx = [b for b in boxes if b.sid == sid]
        area_par[sid] = area_pareto(bx, nodes, types, rho)
        if verbose:
            lst = area_par[sid]
            print("%s 箱数=%2d Pareto解=%3d  架次数 %d~%d  能耗 %.2f~%.2f  时间 %.0f~%.0f"
                  % (sid, len(bx), len(lst), min(o["count"] for o in lst), max(o["count"] for o in lst),
                     min(o["E"] for o in lst), max(o["E"] for o in lst),
                     min(o["T"] for o in lst), max(o["T"] for o in lst)))

    front = pareto_front(area_par)

    # 命名方案
    schemes = {}
    named = {
        "S1-最少架次": min(front, key=lambda x: (x[0]["count"], x[0]["E"], x[0]["T"])),
        "S4-最省能耗": min(front, key=lambda x: (x[0]["E"], x[0]["T"], x[0]["count"])),
        "S5-最短总工时": min(front, key=lambda x: (x[0]["T"], x[0]["E"], x[0]["count"])),
    }
    nmin = named["S1-最少架次"][0]["count"]
    sub = [f for f in front if f[0]["count"] == nmin]
    if sub:
        named["S2-最少架次·能耗最优"] = min(sub, key=lambda x: (x[0]["E"], x[0]["T"]))
        named["S3-最少架次·工时最优"] = min(sub, key=lambda x: (x[0]["T"], x[0]["E"]))
    for k, (tot, picked) in named.items():
        recs = []
        for sid in SIDS:
            for s in picked[sid]["sorties"]:
                dt = types[s["g"]]
                recs.append(dict(服务区编号=sid, 机型编号=s["g"],
                                 货箱编号列表=";".join(s["bids"]), 箱数=len(s["bids"]),
                                 总质量_kg=round(s["mass"], 3), 总体积_m3=round(s["vol"], 4),
                                 往返时间_s=round(s["T"], 1), 架次能耗_kWh=round(s["E"], 4),
                                 返航SOC_pct=round(100 * (1 - s["E"] / dt.e_use), 2),
                                 质量占用率=round(s["mass"] / dt.q_max, 4),
                                 体积占用率=round(s["vol"] / dt.v_cap, 4)))
        recs.sort(key=lambda r: (r["服务区编号"], r["机型编号"], r["货箱编号列表"]))
        code = k.split("-")[0]
        for i, r in enumerate(recs, 1):
            r["架次编号"] = "Q1%s-%02d" % (code, i)
        schemes[k] = (tot, recs)

    return dict(d=d, rho=rho, q1a=q1a, area_par=area_par, front=front,
                schemes=schemes, SIDS=SIDS)


def sensitivity():
    recs = []
    for rho in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
        d = D.load_all()
        nodes, types, boxes, SIDS = d["nodes"], d["ttypes"], d["boxes"], d["SIDS"]
        row = dict(返航安全余量比例=rho)
        for g in ("A", "B", "C"):
            qs = [max_safe_payload(nodes, types[g], sid, rho)[0] for sid in SIDS]
            row["%s型最大安全载荷均值_kg" % g] = round(float(np.mean(qs)), 3)
            row["%s型受限服务区数" % g] = int(sum(1 for q in qs if q < types[g].q_max - 1e-6))
            row["%s型最小安全载荷_kg" % g] = round(float(np.min(qs)), 3)
        area_par = {sid: area_pareto([b for b in boxes if b.sid == sid], nodes, types, rho)
                    for sid in SIDS}
        bad = [sid for sid in SIDS if not area_par[sid]]
        row["不可达服务区"] = ",".join(bad) if bad else "-"
        front = pareto_front(area_par, n_grid=8)
        if front:
            best = min(front, key=lambda x: (x[0]["count"], x[0]["E"], x[0]["T"]))[0]
            row["最少架次数"] = best["count"]
            row["最少架次方案总能耗_kWh"] = round(best["E"], 3)
            row["最少架次方案累计工时_s"] = round(best["T"], 1)
            row["Pareto点数"] = len(front)
            row["最小架次数下最优能耗_kWh"] = round(min(f[0]["E"] for f in front), 3)
        else:
            row["最少架次数"] = None
            row["最少架次方案总能耗_kWh"] = None
            row["最少架次方案累计工时_s"] = None
            row["Pareto点数"] = 0
            row["最小架次数下最优能耗_kWh"] = None
        recs.append(row)
    return pd.DataFrame(recs)


if __name__ == "__main__":
    import time
    t0 = time.time()
    res = solve()
    print("\n求解耗时 %.1f s" % (time.time() - t0))

    res["q1a"].to_excel(os.path.join(OUT, "Q1_最大安全载荷.xlsx"), index=False)
    with pd.ExcelWriter(os.path.join(OUT, "Q1_单点组批.xlsx")) as w:
        for name, (tot, recs) in res["schemes"].items():
            pd.DataFrame(recs).to_excel(w, sheet_name=name[:31], index=False)

    print("\n=== 全局 Pareto 前沿（架次数, 总能耗 kWh, 累计工时 s） ===")
    for tot, _ in res["front"]:
        print("  架次=%3d  能耗=%8.2f  工时=%8.0f s (%.2f h)" % (tot["count"], tot["E"], tot["T"], tot["T"] / 3600))
    print("\n=== 具名方案 ===")
    for name, (tot, recs) in res["schemes"].items():
        print("%-24s 架次=%3d  能耗=%8.2f kWh  工时=%8.0f s (%.2f h)" %
              (name, tot["count"], tot["E"], tot["T"], tot["T"] / 3600))

    with open(os.path.join(OUT, "Q1_前沿.json"), "w", encoding="utf-8") as f:
        json.dump([t[0] for t in res["front"]], f, ensure_ascii=False, indent=1)

    sen = sensitivity()
    sen.to_excel(os.path.join(OUT, "Q1_灵敏度.xlsx"), index=False)
    print("\n=== rho 灵敏度 ===")
    print(sen.to_string(index=False))
