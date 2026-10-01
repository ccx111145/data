# -*- coding: utf-8 -*-
"""
vq1.py —— 问题一独立交叉验证
用 CP-SAT 求解"集合划分"整数规划（与 q1.py 的分组状态 DP 完全不同的算法），
对比 (a) 最少架次数 (b) 最少架次数下的最小总能耗，并对最终方案逐项复算物理约束。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

import dcore as D
import q1

from ortools.sat.python import cp_model

OUT = D.RESULTS


def feasible_columns(bx, nodes, types, rho):
    """枚举所有可行单架次列：mask -> (最优机型, E, T)。"""
    n = len(bx)
    cols = {}
    for mask in range(1, 1 << n):
        mass = sum(bx[i].mass for i in range(n) if mask >> i & 1)
        vol = sum(bx[i].vol for i in range(n) if mask >> i & 1)
        best = None
        for g in ("A", "B", "C"):
            dt = types[g]
            if mass > dt.q_max + 1e-9 or vol > dt.v_cap + 1e-9:
                continue
            e, t, _ = q1.sortie_single(nodes, dt, bx[0].sid, mass)
            if e > (1 - rho) * dt.e_use + 1e-12:
                continue
            if best is None or (e, t) < (best[1], best[2]):
                best = (g, e, t)
        if best:
            cols[mask] = best
    return cols


def ip_area(bx, nodes, types, rho, n_fix=None, obj="E"):
    n = len(bx)
    cols = feasible_columns(bx, nodes, types, rho)
    if not cols:
        return None
    m = cp_model.CpModel()
    xs = {mask: m.NewBoolVar("x%d" % mask) for mask in cols}
    for i in range(n):
        m.Add(sum(xs[mask] for mask in cols if mask >> i & 1) == 1)
    if n_fix is not None:
        m.Add(sum(xs.values()) == n_fix)
    scale = 10000
    if obj == "count":
        m.Minimize(sum(xs.values()))
    elif obj == "E":
        m.Minimize(sum(int(round(cols[mask][1] * scale)) * xs[mask] for mask in cols))
    else:
        m.Minimize(sum(int(round(cols[mask][2] * 100)) * xs[mask] for mask in cols))
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = 120.0
    s.parameters.num_search_workers = 8
    st = s.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    parts = [mask for mask in cols if s.Value(xs[mask]) > 0.5]
    return dict(count=len(parts), E=sum(cols[k][1] for k in parts), T=sum(cols[k][2] for k in parts),
                parts=parts, status=s.StatusName(st), cols=cols)


def main():
    d = D.load_all()
    nodes, types, boxes, SIDS = d["nodes"], d["ttypes"], d["boxes"], d["SIDS"]
    rho = types["A"].rho

    recs = []
    dp_par = {}
    for sid in SIDS:
        bx = [b for b in boxes if b.sid == sid]
        lst = q1.area_pareto(bx, nodes, types, rho)
        dp_par[sid] = lst
        dp_min_count = min(o["count"] for o in lst)
        dp_minE_at_minc = min((o["E"] for o in lst if o["count"] == dp_min_count))
        dp_minE_any = min(o["E"] for o in lst)

        r1 = ip_area(bx, nodes, types, rho, obj="count")
        r2 = ip_area(bx, nodes, types, rho, n_fix=r1["count"], obj="E") if r1 else None
        r3 = ip_area(bx, nodes, types, rho, obj="E")

        recs.append(dict(
            服务区=sid, 箱数=len(bx),
            DP最少架次=dp_min_count, IP最少架次=r1["count"] if r1 else None,
            一致1=(r1 is not None and dp_min_count == r1["count"]),
            DP最少架次下最优能耗=round(dp_minE_at_minc, 4),
            IP最少架次下最优能耗=round(r2["E"], 4) if r2 else None,
            一致2=(r2 is not None and abs(dp_minE_at_minc - r2["E"]) < 1e-3),
            DP全局最小能耗=round(dp_minE_any, 4),
            IP全局最小能耗=round(r3["E"], 4) if r3 else None,
            一致3=(r3 is not None and abs(dp_minE_any - r3["E"]) < 1e-3),
            求解状态=r1["status"] if r1 else "INFEASIBLE",
        ))
    df = pd.DataFrame(recs)
    df.to_excel(os.path.join(OUT, "Q1_IP交叉验证.xlsx"), index=False)
    print(df.to_string(index=False))
    print("\n汇总：最少架次数一致 %d/%d，能耗一致 %d/%d，全局最小能耗一致 %d/%d"
          % (df["一致1"].sum(), len(df), df["一致2"].sum(), len(df), df["一致3"].sum(), len(df)))

    # ---- 物理约束复算（对 q1.py 产出的 S1 方案）----
    res = q1.solve(verbose=False)
    tot, recs_s1 = res["schemes"]["S1-最少架次"]
    bxidx = D.box_index(boxes)
    bad = []
    for r in recs_s1:
        g = r["机型编号"]
        dt = types[g]
        bids = r["货箱编号列表"].split(";")
        mass = sum(bxidx[b].mass for b in bids)
        vol = sum(bxidx[b].vol for b in bids)
        if mass > dt.q_max + 1e-9:
            bad.append((r["架次编号"], "质量超限", mass, dt.q_max))
        if vol > dt.v_cap + 1e-9:
            bad.append((r["架次编号"], "体积超限", vol, dt.v_cap))
        E, T, _ = q1.sortie_single(nodes, dt, r["服务区编号"], mass)
        if E > (1 - dt.rho) * dt.e_use + 1e-9:
            bad.append((r["架次编号"], "能量超限", E, (1 - dt.rho) * dt.e_use))
        if abs(E - r["架次能耗_kWh"]) > 1e-3 or abs(T - r["往返时间_s"]) > 0.15:
            bad.append((r["架次编号"], "复算不符", (E, T), (r["架次能耗_kWh"], r["往返时间_s"])))
    # 货箱覆盖检查
    delivered = [b for r in recs_s1 for b in r["货箱编号列表"].split(";")]
    if sorted(delivered) != sorted(bxidx.keys()):
        bad.append(("全局", "货箱重复或遗漏", len(delivered), len(bxidx)))
    print("\n=== S1 方案物理约束复算 ===")
    print("架次数 %d, 覆盖货箱 %d/%d, 违反项 %d" % (len(recs_s1), len(delivered), len(bxidx), len(bad)))
    for b in bad:
        print("   !", b)
    with open(os.path.join(OUT, "Q1_复算报告.txt"), "w", encoding="utf-8") as f:
        f.write("架次数=%d 覆盖货箱=%d/%d 违反项=%d\n" % (len(recs_s1), len(delivered), len(bxidx), len(bad)))
        for b in bad:
            f.write("  ! %s\n" % (b,))
    return df


if __name__ == "__main__":
    main()
