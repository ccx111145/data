# -*- coding: utf-8 -*-
"""_vrelay8.py —— 全局贪心中继规划：每次迭代在所有 (候选点, 种子时刻) 中选"覆盖最多"的可行架次。

与 _vrelay7 的区别：不再"选定种子时刻后在少量候选里挑"，而是对**全部回传可用候选点 ×
全部仍未覆盖的时刻**做一次全局评估，选净收益最大者。代价是一次全枚举较慢，但覆盖率显著更高。

用法：python _vrelay8.py [spacing] [pad] [max_win_s] [topk_per_cand]
"""
from __future__ import annotations
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import dcore as D
import comm as C
import relay as R
import q2 as Q
import q3plan as PL
import solution_io as SIO

SPACING = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0030
PAD = float(sys.argv[2]) if len(sys.argv) > 2 else 0.030
MAXWIN = float(sys.argv[3]) if len(sys.argv) > 3 else 4600.0
TOPK = int(sys.argv[4]) if len(sys.argv) > 4 else 6
AGL = (150.0, 300.0)
GRID = 10.0

inst = Q.Instance()
sol = SIO.load(SIO.SOL_JSON)
tr = sol["transport"]
link = C.Link(inst)
rtype = inst.d["rtype"]
rtb = inst.d["rbatt"][1]
ncomp = inst.d["rbatt"][0]
EMAX = (1 - rtype.rho) * rtype.e_use
p_hov = rtype.p_hover + rtype.p_comm
print("运输架次 %d；spacing=%.4f pad=%.3f max_win=%.0f topk=%d；能耗上限 %.3f kWh"
      % (len(tr), SPACING, PAD, MAXWIN, TOPK, EMAX))


class S:
    pass


sorties, assign = [], {}
for i, r in enumerate(tr):
    s = S()
    s.g, s.areas = r["type"], list(r["route"][1:-1])
    s.load = {k: list(v) for k, v in (r.get("boxes") or {}).items()}
    s.E, s.dur, s.offs = float(r["energy"]), float(r["end"]) - float(r["start"]), {}
    sorties.append(s)
    assign[i] = dict(start=float(r["start"]))

t0 = time.time()
T, P, K, tmax = PL.build_instances(inst, sorties, assign, link, grid=GRID)
times = np.unique(T)
tidx = np.searchsorted(times, T)
nt = len(times)
cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=SPACING, pad=PAD, agl=AGL)
cov_all, bh_ok, acc = R.coverage_matrix(link, P, cand)
keep = np.nonzero(bh_ok)[0]
cov = np.ascontiguousarray(cov_all[:, keep])
metak = [meta[i] for i in keep]
cand_idx = [np.nonzero(cov[:, c])[0] for c in range(len(keep))]
# 预计算每个候选点的往返飞行参数
RF = [D.relay_flight(rtype, inst.nodes, metak[c][0], metak[c][1], metak[c][3])
      for c in range(len(keep))]
print("需求实例 %d（%d 时刻），候选 %d（回传可用 %d），矩阵 %.0f s"
      % (len(T), nt, len(cand), len(keep), time.time() - t0))

N = len(T)
covered = np.zeros(N, dtype=bool)
reserved = {d: 0.0 for d in inst.d["rfleet"]}
comp_free = {"R-E%d" % (k + 1): 0.0 for k in range(ncomp)}
out = []
t_greedy = time.time()
it = 0
while True:
    it += 1
    best = None
    for c in range(len(keep)):
        js = [int(j) for j in cand_idx[c] if not covered[j]]
        if not js:
            continue
        rf = RF[c]
        # 所有可用的"提前到场时刻"下界：机动无人机 → 越早越难满足；直接按无人机可用时刻评估
        drones = sorted(inst.d["rfleet"], key=lambda d: reserved[d])
        dr = drones[0]
        d_free = reserved[dr]
        # 候选窗口生成：对每个"起点实例"，向前贪心扩展连续时刻
        jt = sorted(js, key=lambda j: float(T[j]))
        tl = np.array([float(T[j]) for j in jt])
        ec = np.array([int(tidx[j]) for j in jt])
        i0 = 0
        while i0 < len(jt):
            # 起点的"最早可服务时刻" <= 当前窗口起点；不满足则跳过（该实例留给以后或由别的点覆盖）
            t_lo = tl[i0] if i0 > 0 else tl[0]
            t_need = max(0.0, t_lo - rtype.t_link - rf["t_out"])
            if max(t_need, 0.0) < d_free - 1e-9:
                i0 += 1
                continue
            i2 = i0
            while (i2 + 1 < len(jt) and ec[i2 + 1] == ec[i2] + 1
                   and tl[i2 + 1] - tl[i0] <= MAXWIN):
                i2 += 1
            t_hi = tl[i2]
            if t_hi - t_lo < 60.0:
                i0 += 1
                continue
            e_tot = rf["e_fly"] + p_hov * (t_hi - t_lo) / 3600.0
            if e_tot > EMAX:
                cap = t_lo + (EMAX - rf["e_fly"]) / p_hov * 3600.0
                m = tl[:i2 + 1] <= cap + 1e-9
                i2 = int(np.nonzero(m)[0][-1])
                t_hi = tl[i2]
                if t_hi - t_lo < 60.0:
                    i0 += 1
                    continue
                e_tot = rf["e_fly"] + p_hov * (t_hi - t_lo) / 3600.0
            gain = i2 - i0 + 1
            if best is None or gain > best[0]:
                cc = [k for k, v in comp_free.items() if v <= t_need + 1e-9]
                if not cc:
                    i0 = i2 + 1
                    continue
                cp = min(cc, key=lambda k: (comp_free[k], k))
                best = (gain, c, t_lo, t_hi, jt[i0:i2 + 1], rf, dr, cp, e_tot)
            # 也尝试"跳过若干实例后重新开窗"，用 step 加速
            i0 = i0 + max(1, (i2 - i0 + 1) // 60)
    if best is None:
        print("无更多可行架次（剩余未覆盖 %d 实例）" % int((~covered).sum()))
        break
    gain, c, t_lo, t_hi, win, rf, dr, cp, e_tot = best
    t_need = max(0.0, t_lo - rtype.t_link - rf["t_out"])
    lo, la, g, agl = metak[c]
    link_done, t_end = t_lo, t_hi
    back = t_end + rf["t_back"]
    hover = t_end - link_done
    e_hover = p_hov * hover / 3600.0
    e_tot = rf["e_fly"] + e_hover
    soc = 1.0 - e_tot / rtype.e_use
    chg = float(D.charge_time(soc, rtb))
    reserved[dr] = back + rtype.t_turn
    comp_free[cp] = back + chg
    out.append(dict(rid=len(out) + 1, drone=dr, comp=cp, lon=lo, lat=la, ground=g, agl=agl,
                    hover_alt=g + agl, t_depart=t_need, t_link_done=link_done, t_end=t_end,
                    t_back=back, e_fly=rf["e_fly"], e_hover=e_hover, e_total=e_tot,
                    soc=soc, chg=chg))
    for j in win:
        covered[j] = True
    print("  架次 %2d：覆盖 %4d 实例（累计 %4d/%d），悬停 %.0f~%.0f s E=%.3f SOC=%.1f%% [%s/%s] %.0f s"
          % (len(out), gain, int(covered.sum()), N, link_done, t_end, e_tot, 100 * soc, dr, cp,
             time.time() - t_greedy))

ok = np.zeros(N, dtype=bool)
for r in out:
    pt = (r["lon"], r["lat"], r["hover_alt"])
    a_ok, _, _ = link.access_ok(np.c_[P[:, 0], P[:, 1], P[:, 2]], pt)
    sel = np.nonzero(a_ok)[0]
    sel = sel[(T[sel] >= r["t_link_done"] - 1e-9) & (T[sel] <= r["t_end"] + 1e-9)]
    ok[sel] = True
n_un = int((~ok).sum())
print("中继架次 %d；真实未覆盖 %d/%d（覆盖率 %.2f%%），未覆盖时长约 %.0f s；悬停总时长 %.0f s"
      % (len(out), n_un, N, 100.0 * (1 - n_un / max(1, N)), GRID * n_un,
         sum(r["t_end"] - r["t_link_done"] for r in out)))
if not out:
    sys.exit(1)
recs = SIO.relay_to_records(out, code_prefix="Q3-R")
sol["relay"] = recs
sol["meta"] = dict(sol.get("meta") or {})
sol["meta"]["n_relay"] = len(recs)
sol["meta"]["relay_plan"] = dict(method="global_greedy(_vrelay8.py)", spacing=SPACING, pad=PAD,
                                 agl=list(AGL), n_req=int(N), n_uncovered_true=n_un,
                                 cover_rate_true=round(1.0 - n_un / max(1, N), 4))
# 记录该中继方案所依据的运输方案指纹，供 export_results.py 判断是否过期
import hashlib
_items = []
for _r in tr:
    _b = ";".join("%s:%s" % (k, ",".join(sorted(v))) for k, v in sorted((_r.get("boxes") or {}).items()))
    _items.append("%s|%s|%.3f|%.3f|%s|%s" % (_r.get("sid"), _r.get("type"), float(_r["start"]),
                                             float(_r["end"]), "->".join(_r["route"]), _b))
sol["meta"]["relay_plan"]["transport_fp"] = hashlib.md5(
    "\n".join(_items).encode("utf-8")).hexdigest()[:12]
SIO.save(sol, SIO.SOL_JSON)
print("已写回 %s" % SIO.SOL_JSON)
