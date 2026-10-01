# -*- coding: utf-8 -*-
"""_diag_lowocc.py —— 诊断低阻塞率地形（α=0.35）下「N=1/2/3 都不可行」的真因。

若该不可行是构造性判定器的缺陷（而非物理不可行），相位图会被污染，
因此必须逐条件定位失败点：
  * 失败格 k / 时刻 t / 原因；
  * 该格的需求结构（实例数、可选候选点数）；
  * 若失败原因是"无可行换位"，逐条统计 (T1)到位 / (T2)其余到位 / (T3)并集 / (T4)覆盖 / (T5)能源
    五类拒绝的计数，判断是"候选不足"还是"时序不可能"。
"""
from __future__ import annotations

import os
import sys
import numpy as np

import dcore as D
import terrain as T
import comm as C
import q2 as Q
import q3 as Q3
import q3dpN as DN
import greedy_relay as GR
import terrain_benchmark as TB

ALPHA = float(sys.argv[1]) if len(sys.argv) > 1 else 0.35
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3

_, spec = TB.load_transport_spec()
base = D.DEM()
dem = T.make_dem(alpha=ALPHA, base=base)
D.set_dem(dem)
import q2 as _q2
_q2._COVER[0] = None
inst = Q.Instance()
sorties, assign = TB.rebuild(spec)
link = C.Link(inst, dem=dem, channel_model="observed")
ph = Q3.relay_phases(inst, sorties, assign, None, link=link, verbose=True,
                     min_phase_s=1400.0, max_phase_s=5400.0)
if not ph.get("ok"):
    print("relay_phases 失败：%s" % ph.get("msg"))
    D.set_dem(None)
    raise SystemExit(1)

cells = np.asarray(ph["cells"], dtype=np.float64)
alone = ph["alone"]
groups = ph.get("groups") or []
n = len(cells)
print("\n时间格 %d；相位数 %d；首格 t=%.0f，末格 t=%.0f" % (n, len(ph["intervals"]), cells[0], cells[-1]))
print("需求格长度：前 5 格 %s ... 末 5 格 %s" % (cells[:5], cells[-5:]))
print("每格实例数分布：", {int(v): int(sum(1 for g in groups if len(g) == v))
                          for v in sorted({len(g) for g in groups})})

rtype = inst.d["rtype"]
cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
pb = DN.PB(ph, grid=10.0, topk=400, inst=inst, mode="base")
print("PB 候选点 %d；单次驻留上限 %.0f s" % (pb.P, cap))
print("单点可独保格 %d/%d" % (int(sum(1 for k in range(n) if alone[k].any())), n))

g = GR.greedy(inst, ph, N=N, mode="base", cap_s=cap, topk=400, verbose=False)
print("\n贪心 N=%d -> %s；推进到 %d/%d 格" % (N, "可行" if g["ok"] else "不可行",
                                            g["reached_cell"], g["n_cells"]))
if not g["ok"]:
    k, t, reason = g["fail"]
    print("  失败：k=%d t=%.0f s 原因=%s" % (k, t, reason))
    print("  该格需求实例数 %d；可选候选点数 %d" % (len(groups[k]), int(pb.cand(k, pb.need[k]).size)
                                          if hasattr(pb, "need") else -1))
    # 逐条件统计
    need = pb.need[k]
    cnt = dict(cand_empty=0, rej_pnew_eq=0, rej_old_arrival=0, rej_other_arrival=0,
               rej_union=0, rej_cover=0, rej_age=0, rej_span=0, accepted=0)
    pos, arr, r0 = [GR.IDLE] * N, [0] * N, [0] * N
    for i in range(N):
        others = [pos[j] for j in range(N) if j != i]
        mo = 0
        for o in others:
            if o != GR.IDLE:
                mo |= int(pb.mask[k][o])
        rem = need & ~mo
        targets = list(pb.cand(k, rem))
        if not targets:
            cnt["cand_empty"] += 1
            continue
        for p_new in targets:
            if p_new == pos[i]:
                cnt["rej_pnew_eq"] += 1
                continue
            w = min(pb.w_cells(pos[i], p_new), int(round(1500.0 / 10.0)))
            k0 = max(0, k - w)
            if pos[i] != GR.IDLE and k0 < arr[i]:
                cnt["rej_old_arrival"] += 1
                continue
            if any(pos[j] != GR.IDLE and k0 < arr[j] for j in range(N) if j != i):
                cnt["rej_other_arrival"] += 1
                continue
            if not pb.union_ok(others, k0, k - 1):
                cnt["rej_union"] += 1
                continue
            m2 = 0
            for jj in range(N):
                pj = p_new if jj == i else pos[jj]
                if pj != GR.IDLE:
                    m2 |= int(pb.mask[k][pj])
            if m2 != need:
                cnt["rej_cover"] += 1
                continue
            span = int(pb.run_end[k][p_new]) - k + 1
            if span < 1:
                cnt["rej_span"] += 1
                continue
            cnt["accepted"] += 1
    print("  若从 IDLE 出发，逐条件拒绝计数：", cnt)
    # 该格之后还有多少格
    print("  失败格之后仍有 %d 个需求格（最后一个 t=%.0f s）" % (n - k, cells[-1]))
    j = k
    while j < n and len(groups[j]) == 1 and alone[j].sum() > 0:
        j += 1
    print("  从失败格起连续单实例格数 = %d" % (j - k))
D.set_dem(None)
