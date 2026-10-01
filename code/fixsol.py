# -*- coding: utf-8 -*-
"""fixsol.py —— 修正 solution.json 中继记录的 depart/back 为绝对时刻并补齐派生字段。"""
from __future__ import annotations
import os
import dcore as D
import q2 as Q
import solution_io as SIO


def main():
    inst = Q.Instance()
    rtype = inst.d["rtype"]
    sol = SIO.load()
    for r in sol.get("relay", []):
        rf = D.relay_flight(rtype, inst.nodes, r["lon"], r["lat"], max(0.0, r["agl"]))
        r["depart"] = float(max(0.0, r["link_done"] - rf["t_out"] - rtype.t_link))
        r["end"] = float(r["end"])
        r["back"] = float(r["end"] + rf["t_back"])
        r["hover"] = float(r["end"] - r["link_done"])
        r["t_out"] = float(rf["t_out"])
        r["t_back"] = float(rf["t_back"])
    m = sol.setdefault("meta", {})
    if sol.get("relay"):
        m["n_relay"] = len(sol["relay"])
        m["relay_energy"] = float(sum(r["e_total"] for r in sol["relay"]))
        m["relay_hover"] = float(sum(r["hover"] for r in sol["relay"]))
        m["joint_makespan"] = float(max([m.get("makespan", 0.0)] + [r["back"] for r in sol["relay"]]))
    SIO.save(sol)
    print("relay rows=%d  n_relay=%s  relay_energy=%.3f kWh  relay_hover=%.0f s  joint_makespan=%.0f s"
          % (len(sol.get("relay", [])), m.get("n_relay"), m.get("relay_energy", 0.0),
             m.get("relay_hover", 0.0), m.get("joint_makespan", 0.0)))
    for r in sol.get("relay", []):
        print("  %s %s %s dep=%.0f link=%.0f end=%.0f back=%.0f hover=%.0f SOC=%.1f%%"
              % (r["sid"], r["drone"], r["comp"], r["depart"], r["link_done"], r["end"],
                 r["back"], r["hover"], 100 * r["soc"]))


if __name__ == "__main__":
    main()
