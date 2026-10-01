# -*- coding: utf-8 -*-
"""
solution_io.py —— 各问题之间的标准数据接口（Q2 → Q3 → Q4 / 论文 / 校验共用）

规范文件：results/solution.json
{
  "meta":    {"rho":0.2, "makespan":float, "energy":float, ...},
  "transport": [
     {"sid":"Q2-P1-01", "drone":"U07", "type":"C", "battery":"C-B1",
      "start":0.0, "end":1234.5, "energy":3.21, "soc":0.85, "chg":900.0,
      "route":["O01","S001","S005","O01"],
      "boxes":{"S001":["S001-MED-01",...], "S005":[...]},
      "deliver":{"S001-MED-01":900.0, ...}}
  ],
  "relay": [
     {"sid":"Q3-R-01", "drone":"R01", "comp":"R-E1",
      "lon":109.2, "lat":23.05, "hover_alt":520.0, "agl":300.0, "ground":220.0,
      "depart":100.0, "link_done":500.0, "end":3000.0, "back":3400.0,
      "e_fly":0.25, "e_hover":0.60, "e_total":0.85, "soc":0.73, "chg":800.0}
  ],
  "coverage": [ {"sid":"Q2-P1-01", "phase":"cruise", "t0":..., "t1":..., "mode":"direct|relay|none",
                 "relay":"Q3-R-01"} ]
}
"""
from __future__ import annotations

import json
import os
import numpy as np
import pandas as pd

import dcore as D

OUT = D.RESULTS
SOL_JSON = os.path.join(OUT, "solution.json")
SOL_XLSX = os.path.join(OUT, "结果提交.xlsx")


def save(sol, path=SOL_JSON):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sol, f, ensure_ascii=False, indent=1, default=float)
    return path


def load(path=SOL_JSON):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def transport_from_sorties(inst, sol, assign, code_prefix="Q2"):
    """把 q2.Sortie 列表 + 排程转成标准 transport 记录。"""
    order = sorted(range(len(sol)), key=lambda k: (assign[k]["start"], k))
    code = {k: "%s-%02d" % (code_prefix, i + 1) for i, k in enumerate(order)}
    recs = []
    for k in order:
        s = sol[k]
        a = assign[k]
        boxes = {ar: list(s.load[ar]) for ar in s.areas}
        deliver = {}
        for ar in s.areas:
            for b in s.load[ar]:
                deliver[b] = a["start"] + s.offs[ar]
        recs.append(dict(sid=code[k], drone=a.get("drone", ""), type=s.g,
                         battery=a.get("battery", ""), start=float(a["start"]),
                         end=float(a["end"]), energy=float(s.E),
                         soc=float(1 - s.E / inst.euse[s.g]),
                         chg=float(a.get("chg", 0.0)),
                         route=["O01"] + list(s.areas) + ["O01"],
                         boxes=boxes, deliver=deliver))
    return recs


def relay_to_records(sorties, code_prefix="Q3-R"):
    out = []
    for i, s in enumerate(sorties, 1):
        out.append(dict(sid="%s-%02d" % (code_prefix, i), drone=s["drone"], comp=s.get("comp", ""),
                        lon=float(s["lon"]), lat=float(s["lat"]),
                        hover_alt=float(s["hover_alt"]), agl=float(s["agl"]),
                        ground=float(s.get("ground", s["hover_alt"] - s["agl"])),
                        depart=float(s.get("t_depart", 0.0)),
                        link_done=float(s["t_link_done"]), end=float(s["t_end"]),
                        back=float(s.get("t_back", s["t_end"])),
                        e_fly=float(s["e_fly"]), e_hover=float(s["e_hover"]),
                        e_total=float(s["e_total"]), soc=float(s["soc"]),
                        chg=float(s.get("chg", 0.0))))
    return out


# ---------------------------------------------------------------------------
# 资源核算（Q4 与检查说明共用）
# ---------------------------------------------------------------------------
def resource_peak(records, key_type, key_time=("start", "end"), dtype="type"):
    """按机型统计峰值并发数（用于"所需实体无人机/电池组数"核算）。"""
    ev = []
    for r in records:
        g = r[dtype]
        ev.append((r[key_time[0]], g, +1))
        ev.append((r[key_time[1]], g, -1))
    ev.sort(key=lambda x: (x[0], x[2]))
    cur = {}
    peak = {}
    for _, g, d in ev:
        cur[g] = cur.get(g, 0) + d
        peak[g] = max(peak.get(g, 0), cur[g])
    return peak
