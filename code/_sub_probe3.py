# -*- coding: utf-8 -*-
"""临时探针 3：在 D题/code 下运行，量测中继换位的黑障窗口（换位点对几何逐对精确计算）。"""
import os, sys, json, math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

inst = Q.Instance()
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

ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=False,
                     min_phase_s=1400.0, max_phase_s=5400.0)
pb = DN.PB(ph, grid=10.0, topk=12, inst=inst)
rtype = inst.d["rtype"]
print("候选悬停点 %d，时间格 %d，需求实例 %d" % (pb.P, pb.n, len(ph["T"])))
print("t_turn=%.0f  t_link=%.0f" % (rtype.t_turn, rtype.t_link))

# 相位结构
for i, (k0, k1, js) in enumerate(ph["intervals"]):
    print("  相%02d  %6.0f–%-6.0f 时长 %5.0f s  点位 %s"
          % (i + 1, ph["cells"][k0], ph["cells"][k1],
             ph["cells"][k1] - ph["cells"][k0] + 10, tuple(int(x) for x in js)))

# 逐点对黑障窗口
print("\n== 黑障窗口（换位：返航+架次周转+再出动+建链），按点对几何精确计算 ==")
ws = []
for a in range(0, pb.P):
    for b in range(0, pb.P):
        if a == b:
            continue
        w = pb.w_cells(a, b)
        sec = pb.TB[a] + pb.t_turn + pb.TO[b] + pb.t_link
        ws.append((sec, a, b))
ws.sort()
n = len(ws)
print("点对数 %d" % n)
print("最小 %.0f s（点 %d→%d）" % (ws[0][0], ws[0][1], ws[0][2]))
print("1%% 分位 %.0f s" % ws[int(0.01 * n)][0])
print("中位   %.0f s" % ws[n // 2][0])
print("99%% 分位 %.0f s" % ws[int(0.99 * n)][0])
print("最大 %.0f s" % ws[-1][0])
print("平均 %.0f s" % (sum(x[0] for x in ws) / n))
print("≥1100 s 的点对占比 %.1f%%" % (100.0 * sum(1 for x in ws if x[0] >= 1100) / n))
print("≥1300 s 的点对占比 %.1f%%" % (100.0 * sum(1 for x in ws if x[0] >= 1300) / n))
print("Wmax 截断(=1300 s) 的点对数 %d（%.1f%%）"
      % (sum(1 for x in ws if x[0] > 1300), 100.0 * sum(1 for x in ws if x[0] > 1300) / n))

# 每个相位的首格、需求实例数
print("\n== 时间格与需求实例 ==")
print("时间格 %d，需求实例 %d，单点可覆盖格 %d"
      % (pb.n, len(ph["T"]), int((pb.alone.any(axis=1)).sum())))
cnt = [int((ph["K"] == k).sum()) for k in range(len(sorties))]
print("逐架次失联实例数：", cnt)
