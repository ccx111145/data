# -*- coding: utf-8 -*-
"""
mode_compare.py —— 审稿防线 1：中继换位模式对机队最小规模的影响

Mode 1（base）：换位必须返回 O01（返航 + 架次周转 τ_turn + 再出动）
Mode 2（air） ：允许空中点对点直接转场（爬升 + 巡航 + 下降），不回基地

对 N = 1, 2, 3 分别在两种模式下做状态 DP 可行性判定，输出：
  * 是否可行（不可行则给出首个崩溃格/时刻）
  * 中继架次数、在空时长、总能耗、最大连续在空时长
并汇总"空中转场灵活性对机队最小规模的节省效应"。

用法：python mode_compare.py            # 跑 N=1,2 两种模式（快）
      python mode_compare.py --n3       # 追加 N=3（慢，约 30–60 分钟）
"""
from __future__ import annotations

import argparse
import json
import os
import time
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def load_transport():
    """读取 solution.json 的运输方案，重建 q2.Sortie 与排程字典。"""
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
    return sol, sorties, assign


def run_one(inst, ph, N, mode, hover_cap, verbose=False):
    t0 = time.time()
    # DN.solve 现返回 4 元组（多了阻塞诊断 diag）
    seq, cost, pb, _diag = DN.solve(ph, N=N, topk=12, keep_slack=3, inst=inst, verbose=verbose,
                             max_hover_s=hover_cap, mode=mode)
    if seq is None:
        return dict(N=N, mode=mode, feasible=False, reason=str(cost),
                    elapsed=round(time.time() - t0, 1))
    ss = DN.to_sorties(inst, seq, pb, N=N, mode=mode)
    bad = DN.check_timing(inst, ss, mode=mode)
    v = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                  lon=s["lon"], lat=s["lat"], hover_alt=s["hover_alt"])
                             for s in ss], link=ph.get("link"))
    over = [s for s in ss if s["soc"] < inst.d["rtype"].rho - 1e-9]
    # 最大连续在空时长
    max_air = 0.0
    for slot in sorted({s["slot"] for s in ss}):
        run = 0.0
        prev_end = None
        for s in sorted([x for x in ss if x["slot"] == slot], key=lambda x: x["t_link_done"]):
            if prev_end is not None and s["t_depart"] - prev_end <= 60:
                run += s["t_end"] - s["t_depart"]
            else:
                run = s["t_end"] - s["t_depart"]
            prev_end = s["t_end"] + s["t_back"]
            max_air = max(max_air, run + (s["t_back"] if mode == "base" else 0.0))
    return dict(N=N, mode=mode, feasible=True, sorties=len(ss),
                timing_conflicts=len(bad), energy_miss=int(v["miss"]), n_inst=int(v["n"]),
                energy=round(float(sum(s["e_total"] for s in ss)), 3),
                hover=round(float(sum(s["hover"] for s in ss)), 1),
                max_air=round(max_air, 1),
                soc_min=round(100 * min(s["soc"] for s in ss), 1),
                energy_violations=len(over),
                drones=len({s["drone"] for s in ss}),
                elapsed=round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n3", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    inst = Q.Instance()
    rtype = inst.d["rtype"]
    hover_cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
    sol, sorties, assign = load_transport()
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    print("覆盖矩阵完成 %.0f s；单次在空上限 %.0f s" % (time.time() - t0, hover_cap))

    rows = []
    for mode, mname in (("base", "Mode 1 基地返航换电"), ("air", "Mode 2 空中直接转场")):
        for N in ([1, 2, 3] if a.n3 else [1, 2]):
            r = run_one(inst, ph, N, mode, hover_cap)
            r["mode_name"] = mname
            rows.append(r)
            if r["feasible"]:
                print("  %-20s N=%d  可行 | 架次 %2d | 时序冲突 %d | 未覆盖 %d/%d | "
                      "能耗 %7.3f kWh | 悬停合计 %7.0f s | 最大在空 %6.0f s | SOC 最低 %5.1f%% (%.0f s)"
                      % (mname, N, r["sorties"], r["timing_conflicts"], r["energy_miss"],
                         r["n_inst"], r["energy"], r["hover"], r["max_air"], r["soc_min"],
                         r["elapsed"]))
            else:
                print("  %-20s N=%d  不可行 —— %s (%.0f s)" % (mname, N, r["reason"], r["elapsed"]))

    # 汇总
    summary = {}
    for mode in ("base", "air"):
        feas = [r for r in rows if r["mode"] == mode and r["feasible"]]
        summary[mode] = dict(min_N=(min(r["N"] for r in feas) if feas else None),
                             tested=[r["N"] for r in rows if r["mode"] == mode])
    print("\n=== 结论 ===")
    print("Mode 1（基地返航）最小可行中继台数：%s" % summary["base"]["min_N"])
    print("Mode 2（空中转场）最小可行中继台数：%s" % summary["air"]["min_N"])
    if summary["base"]["min_N"] and summary["air"]["min_N"]:
        save = summary["base"]["min_N"] - summary["air"]["min_N"]
        if save > 0:
            print("⇒ 空中点对点转场的灵活性可节省 **%d 架** 中继无人机（%d → %d）"
                  % (save, summary["base"]["min_N"], summary["air"]["min_N"]))
        elif save == 0:
            print("⇒ 空中转场**不能**降低机队最小规模：两种模式下 N=%d 才可行，"
                  "结论对换位模式稳健" % summary["air"]["min_N"])
        else:
            print("⇒ 异常：空中转场反而需要更多中继")

    path = os.path.join(OUT, "换位模式对比.json")
    json.dump(dict(hover_cap_s=round(hover_cap, 1), rows=rows, summary=summary),
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % path)
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
