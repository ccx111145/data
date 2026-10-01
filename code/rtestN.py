# -*- coding: utf-8 -*-
"""rtestN.py —— 对照实验：N = 2 / 3 架中继能否实现全程连续通信。"""
from __future__ import annotations
import sys, time
import numpy as np
import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
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
    Ns = [int(x) for x in (sys.argv[1:] or ["2", "3"])]
    t0 = time.time()
    inst = Q.Instance()
    sol, sorties, assign = load_transport()
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    print("相位覆盖完成 %.0f s" % (time.time() - t0))
    for N in Ns:
        t1 = time.time()
        seq, cost, pb = DN.solve(ph, N=N, topk=12, keep_slack=3, inst=inst)
        if seq is None:
            print("N=%d：DP 不可行 —— %s（用时 %.0f s）" % (N, cost, time.time() - t1))
            continue
        ss = DN.to_sorties(inst, seq, pb, N=N)
        bad = DN.check_timing(inst, ss)
        v = Q3.verify(inst, ph, ss)
        over = [s for s in ss if s["soc"] < inst.d["rtype"].rho]
        print("N=%d：中继架次 %d 个 | 时序冲突 %d | 未覆盖实例 %d/%d | 返航电量不足 %d | 最大悬停 %.0f s"
              % (N, len(ss), len(bad), v["miss"], v["n"], len(over),
                 max(s["hover"] for s in ss)))
        for s in ss:
            print("    #%02d %s %s (%.5f,%.5f) 离地%.0f 出动%.0f 建链%.0f 结束%.0f 悬停%5.0f E=%.3f SOC=%.1f%%"
                  % (s["rid"], s["drone"], s["comp"], s["lon"], s["lat"], s["agl"],
                     s["t_depart"], s["t_link_done"], s["t_end"], s["hover"], s["e_total"],
                     100 * s["soc"]))
        print("    用时 %.0f s" % (time.time() - t1))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
