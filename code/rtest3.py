# -*- coding: utf-8 -*-
"""rtest3.py —— 用状态 DP 求双中继悬停位置序列并校验连续通信。"""
from __future__ import annotations
import time
import numpy as np
import dcore as D
import q2 as Q
import q3 as Q3
import q3dp3 as DP3
import solution_io as SIO


def load_transport():
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


def main():
    t0 = time.time()
    inst = Q.Instance()
    sol, sorties, assign = load_transport()
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    print("相位覆盖计算完成 %.0f s" % (time.time() - t0))
    t1 = time.time()
    seq, cost, pb = DP3.solve(ph, T_move=1300.0, topk=14, keep_slack=3, inst=inst)
    if seq is None:
        print("DP 失败：%s" % cost)
        return
    print("DP 完成：中继架次（换位/出动次数）= %d，用时 %.0f s" % (cost, time.time() - t1))
    ss = DP3.to_sorties(inst, seq, pb, T_move=1300.0)
    print("中继架次明细 %d 个：" % len(ss))
    for s in ss:
        print("  #%02d %s %s (%.5f,%.5f) 离地%.0f 出动%.0f 建链%.0f 结束%.0f 返回%.0f 悬停%5.0f E=%.3f SOC=%.1f%%"
              % (s["rid"], s["drone"], s["comp"], s["lon"], s["lat"], s["agl"], s["t_depart"],
                 s["t_link_done"], s["t_end"], s["t_end"] + s["t_back"], s["hover"],
                 s["e_total"], 100 * s["soc"]))
    bad0 = DP3.check_timing(inst, ss)
    print("拆分前时序冲突 %d 条" % len(bad0))
    ss = DP3.split_long_sorties(inst, seq, pb, ss, T_move=1300.0)
    print("拆分后中继架次 %d 个；最大悬停 %.0f s（容量 %.0f s）"
          % (len(ss), max(s["hover"] for s in ss), DP3.max_hover(inst)))
    bad = DP3.check_timing(inst, ss)
    print("时序冲突 %d 条" % len(bad))
    for b in bad[:6]:
        print("   !", b)
    v = Q3.verify(inst, ph, ss)
    print("逐实例覆盖校验：未覆盖 %d / %d  ok=%s" % (v["miss"], v["n"], v["ok"]))
    em = [s for s in ss if s["soc"] < inst.d["rtype"].rho]
    print("返航电量不足的架次 %d 个" % len(em))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
