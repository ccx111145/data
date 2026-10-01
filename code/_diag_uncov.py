# -*- coding: utf-8 -*-
"""_diag_uncov.py —— 定位「几何不可覆盖」到底卡在哪一条链路。

对地形平移族（shift=(40,40)）下被 `relay_phases` 判为"无任何悬停点可见"的失联实例，
分别计算：
  * 忽略回传、只看接入链路时的最优（最小）接入损耗与对应候选点；
  * 只看回传链路时的最优候选点；
  * 该运输位置的高度、其正下方地面高程与离地高度；
从而判定是「接入几何不可能」还是「回传几何不可能」，并给出裕量。
"""
from __future__ import annotations

import numpy as np

import comm as C
import dcore as D
import q2 as Q
import relay as R
import terrain as T
import terrain_benchmark as TB

_, spec = TB.load_transport_spec()
base = D.DEM()
dem = T.make_dem(alpha=1.0, cut=0.0, base=base, shift=(40, 40))
D.set_dem(dem)
import q2 as _q2
_q2._COVER[0] = None
inst = Q.Instance()
sorties, assign = TB.rebuild(spec)
link = C.Link(inst, dem=dem, channel_model="observed")

# 复现 relay_phases 前段的失联实例构造
grid = 10.0
T_, P_, K_ = [], [], []
for k, s in enumerate(sorties):
    tr = C.sortie_track(inst, s, assign[k]["start"], grid)
    if len(tr["t"]) == 0:
        continue
    ok, _, _ = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
    cells = np.floor(tr["t"] / grid).astype(int)
    agg = {}
    for c, o, lo, la, al in zip(cells, ~ok, tr["lon"], tr["lat"], tr["alt"]):
        if o:
            agg[int(c)] = (float(lo), float(la), float(al))
    for c, v in agg.items():
        T_.append(c * grid); P_.append(v); K_.append(k)
T_ = np.array(T_); P_ = np.array(P_); K_ = np.array(K_)
print("失联实例 %d 个" % len(T_))

cand, meta = R.candidate_grid(inst, P_[:, 0], P_[:, 1], spacing=0.0035, pad=0.024,
                              agl=(80.0, 160.0, 300.0))
print("候选点 %d" % len(cand))
bh_ok, bh_lp, _ = link.backhaul_ok(cand)
print("回传可用候选点 %d (%.1f%%)" % (int(bh_ok.sum()), 100 * bh_ok.mean()))

# 关键：可用的悬停点必须**同时**满足回传可用 + 接入可用。
# relay_phases 正是先在候选集里筛掉回传不可用的点，再判接入覆盖。
bad = []
for i in range(len(T_)):
    lp, blk, d3 = link._loss(tuple(P_[i]), cand, True)
    ok = (lp <= link.l_acc + 1e-9) & bh_ok
    if not ok.any():
        bad.append(i)
print("无任何候选点可见的实例 %d 个" % len(bad))
if not bad:
    D.set_dem(None)
    raise SystemExit(0)

print("\n%-6s %-8s %-8s %-9s %-9s %-9s %-9s" %
      ("idx", "t(s)", "高度m", "地面m", "离地m", "最优接入", "回传可用中\n最优接入"))
for i in bad[:8]:
    lp_all, _, d3 = link._loss(tuple(P_[i]), cand, True)
    j_best = int(np.argmin(lp_all))
    best_acc = float(lp_all[j_best])
    acc_bh = float(lp_all[bh_ok].min()) if bh_ok.any() else float("nan")
    g = float(dem.at(P_[i][0], P_[i][1]))
    print("%-6d %-8.0f %-8.0f %-9.0f %-9.0f %-9.2f %-9.2f"
          % (i, T_[i], P_[i][2], g, P_[i][2] - g, best_acc, acc_bh))
print("\n接入门限 l_acc = %.1f dB（越大越差；最优接入 > 门限 ⇒ 接入几何不可行）" % link.l_acc)
bh_min = float(bh_lp[bh_ok].min()) if bh_ok.any() else float("nan")
print("回传门限 l_bh = %.1f dB；回传可用点的最优回传损耗 = %.1f dB" % (link.l_bh, bh_min))
# 只放宽接入门限，看需要多大才能覆盖
need = []
for i in bad:
    lp_all, _, _ = link._loss(tuple(P_[i]), cand, True)
    need.append(float(lp_all.min()))
print("要让全部实例可覆盖，接入门限至少需放宽到 %.1f dB（当前 %.1f dB，差 %.1f dB）"
      % (max(need), link.l_acc, max(need) - link.l_acc))
D.set_dem(None)
