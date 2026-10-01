# -*- coding: utf-8 -*-
"""
q3dp2.py —— 双中继部署动态规划（全候选池 + 位掩码配置生成）

状态：cell k 上两架中继的悬停位置 (a, b)（可为 IDLE = 停在 O01）
可行性：a 与 b 的覆盖位掩码并集 = 该 cell 全部通信需求实例
转移：只允许 0 或 1 台换位（两台同时换位则无人保障）；换位时另一台必须在
      换位窗口 [k-W, k+W] 内独立覆盖全部需求（W = 往返飞行 + 建链 + 架次周转）
代价：换位 = 新开一个中继架次 ⇒ 目标为最少中继架次
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

import dcore as D

IDLE = -1
INF = float("inf")


def build_masks(dat):
    """每个 cell 上候选点的覆盖位掩码（实例数 <= 30 时用 int 位运算）。"""
    cells = len(dat["cells"])
    masks = []
    for k, g in enumerate(dat["groups"]):
        sub = dat["cov_pool"][g]                  # (n_inst, n_pool)
        n = sub.shape[0]
        m = np.zeros(sub.shape[1], dtype=np.int64)
        for i in range(n):
            m |= (sub[i].astype(np.int64) << i)
        masks.append(m)
    return masks


def prepare_pref(dat):
    """alone 前缀和（用于换位窗口校验）。"""
    alone = dat["alone"]
    n, m = alone.shape
    pref = np.zeros((m, n + 1), dtype=np.int32)
    for j in range(m):
        pref[j, 1:] = np.cumsum(~alone[:, j])
    return pref


def alone_covers(pref, j, k0, k1, ncell):
    k0 = max(0, k0); k1 = min(ncell - 1, k1)
    if k1 < k0:
        return True
    return pref[j, k1 + 1] - pref[j, k0] == 0


def cell_configs(masks, k, score, single_top=400, pair_top=120, max_multi=3):
    """cell k 的可行配置列表 [(a, b)]，b 可为 IDLE。"""
    m = masks[k]
    n_inst = int(m.max()).bit_length()
    full = (1 << n_inst) - 1
    idx = np.nonzero(m)[0]
    if len(idx) == 0:
        return []
    singles = idx[m[idx] == full]
    out = []
    if len(singles):
        order = singles[np.argsort(-score[singles])]
        out.extend((int(a), IDLE) for a in order[:single_top])
        return out
    # 双点：按覆盖掩码分组
    groups = {}
    for a in idx:
        groups.setdefault(int(m[a]), []).append(int(a))
    keys = list(groups.keys())
    pairs = []
    for ma in keys:
        need = full & ~ma
        for mb in keys:
            if (mb & need) == need:
                for a in groups[ma][:6]:
                    for b in groups[mb][:6]:
                        if b != a:
                            pairs.append((a, b))
                break
    if not pairs:                        # 三点兜底
        for ma in keys:
            for mb in keys:
                need3 = full & ~(ma | mb)
                if need3 == 0:
                    continue
                for mc in keys:
                    if (mc & need3) == need3:
                        for a in groups[ma][:3]:
                            for b in groups[mb][:3]:
                                if b != a:
                                    pairs.append((a, b))
                        break
    pairs.sort(key=lambda ab: -(score[ab[0]] + score[ab[1]]))
    uniq = []
    seen = set()
    for (a, b) in pairs:
        if (a, b) in seen:
            continue
        seen.add((a, b))
        uniq.append((a, b))
        uniq.append((b, a))
        if len(uniq) >= pair_top:
            break
    return uniq


def solve(inst, dat, W_move=950.0, W_launch=420.0, grid=10.0, keep_slack=3,
          single_top=400, pair_top=120, verbose=True):
    """
    W_move   ：中继从旧悬停点回 O01 再飞到新悬停点所需时间（换位黑障窗口）
    W_launch ：中继从 O01 直接起飞到新悬停点所需时间（首次出动/休整后再出动）
    """
    cells = len(dat["cells"])
    ncell = cells
    Wm = max(1, int(round(W_move / grid)))
    Wl = max(1, int(round(W_launch / grid)))
    pool = dat["pool"]
    npool = len(pool)
    score = dat["alone"].sum(axis=0).astype(np.float64)
    masks = build_masks(dat)
    pref = prepare_pref(dat)

    cfgs = []
    for k in range(cells):
        c = cell_configs(masks, k, score, single_top=single_top, pair_top=pair_top)
        if not c:
            return None, "cell %d（t=%.0f s）在候选池内无可行配置" % (k, dat["cells"][k])
        cfgs.append(c)
    if verbose:
        npair = sum(1 for c in cfgs if c[0][1] != IDLE)
        print("  cell 数 %d；单点可覆盖 %d，需双点 %d；候选池 %d；W_move=%.0f s W_launch=%.0f s"
              % (cells, cells - npair, npair, npool, W_move, W_launch))

    def base_cost(st):
        return (1 if st[0] >= 0 else 0) + (1 if st[1] >= 0 else 0)

    dp = {st: base_cost(st) for st in cfgs[0]}
    parents = [dict()]
    for k in range(1, cells):
        r_idle, r_act = {}, {}          # key=b, value=(cost, argmin_state)
        c_idle, c_act = {}, {}
        for (a, b), v in dp.items():
            d = r_idle if a < 0 else r_act
            if b not in d or v < d[b][0]:
                d[b] = (v, (a, b))
            d2 = c_idle if b < 0 else c_act
            if a not in d2 or v < d2[a][0]:
                d2[a] = (v, (a, b))
        cur, par = {}, {}
        for (a2, b2) in cfgs[k]:
            best, bp = dp.get((a2, b2), INF), (a2, b2)
            addA = (1 if a2 >= 0 else 0)
            # 第一台（slot0）换位/出动：第二台 b2 必须在黑障窗口内独立保障
            if b2 == IDLE:
                for d in (r_idle, r_act):
                    if b2 in d and d[b2][0] + addA < best:
                        best, bp = d[b2][0] + addA, d[b2][1]
            else:
                if b2 in r_idle and alone_covers(pref, b2, k - Wl, k, ncell):
                    if r_idle[b2][0] + addA < best:
                        best, bp = r_idle[b2][0] + addA, r_idle[b2][1]
                if b2 in r_act and alone_covers(pref, b2, k - Wm, k, ncell):
                    if r_act[b2][0] + addA < best:
                        best, bp = r_act[b2][0] + addA, r_act[b2][1]
            addB = (1 if b2 >= 0 else 0)
            if a2 == IDLE:
                for d in (c_idle, c_act):
                    if a2 in d and d[a2][0] + addB < best:
                        best, bp = d[a2][0] + addB, d[a2][1]
            else:
                if a2 in c_idle and alone_covers(pref, a2, k - Wl, k, ncell):
                    if c_idle[a2][0] + addB < best:
                        best, bp = c_idle[a2][0] + addB, c_idle[a2][1]
                if a2 in c_act and alone_covers(pref, a2, k - Wm, k, ncell):
                    if c_act[a2][0] + addB < best:
                        best, bp = c_act[a2][0] + addB, c_act[a2][1]
            if best < INF:
                cur[(a2, b2)] = best
                par[(a2, b2)] = bp
        if cur:
            mn = min(cur.values())
            keep = {s: v for s, v in cur.items() if v <= mn + keep_slack}
            cur = keep
            par = {s: v for s, v in par.items() if s in keep}
        dp = cur
        parents.append(par)
        if not dp:
            return None, "第 %d 格（t=%.0f s）无可行状态：换位窗口约束过紧" % (k, dat["cells"][k])
    end = min(dp, key=lambda s: dp[s])
    seq = [None] * cells
    st = end
    for k in range(cells - 1, -1, -1):
        seq[k] = st
        if k == 0:
            break
        st = parents[k][st]
        if st is None:
            return None, "回溯失败 k=%d" % k
    return dict(seq=seq, cost=dp[end], cfgs=cfgs, pool=pool)


def to_sorties(inst, dat, seq, grid=10.0):
    """逐格位置序列 → 中继架次表（同一中继的同点连续段合并为一个架次）。"""
    rtype = inst.d["rtype"]
    cells = dat["cells"]
    meta = dat["meta"]
    pool = dat["pool"]
    segs = {0: [], 1: []}
    for slot in (0, 1):
        cur = None
        for k, st in enumerate(seq):
            j = st[slot]
            if cur is not None and cur["j"] == j:
                cur["k1"] = k
                continue
            if cur is not None:
                segs[slot].append(cur)
            cur = dict(j=j, k0=k, k1=k)
        if cur is not None:
            segs[slot].append(cur)
    out = []
    for slot in (0, 1):
        for sg in segs[slot]:
            if sg["j"] == IDLE:
                continue
            c = pool[sg["j"]]
            lo, la, g, agl = meta[c]
            rf = D.relay_flight(rtype, inst.nodes, lo, la, agl)
            t0, t1 = float(cells[sg["k0"]]), float(cells[sg["k1"]])
            hover = max(0.0, t1 - t0)
            e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
            e_tot = rf["e_fly"] + e_hover
            out.append(dict(slot=slot, lon=lo, lat=la, ground=g, agl=agl, hover_alt=g + agl,
                            t_link_done=t0, t_end=t1, hover=hover,
                            t_depart=max(0.0, t0 - rtype.t_link - rf["t_out"]),
                            t_back=t1 + rf["t_back"], e_fly=rf["e_fly"], e_hover=e_hover,
                            e_total=e_tot, soc=1.0 - e_tot / rtype.e_use,
                            chg=float(D.charge_time(1.0 - e_tot / rtype.e_use, inst.d["rbatt"][1]))))
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    # 同一中继相邻同点段合并
    merged = []
    for s in out:
        if merged and merged[-1]["slot"] == s["slot"] and \
                abs(merged[-1]["lon"] - s["lon"]) < 1e-9 and abs(merged[-1]["lat"] - s["lat"]) < 1e-9 and \
                abs(merged[-1]["agl"] - s["agl"]) < 1e-9 and s["t_link_done"] <= merged[-1]["t_end"] + grid + 1e-6:
            m = merged[-1]
            m["t_end"] = s["t_end"]
            m["hover"] = m["t_end"] - m["t_link_done"]
            m["e_hover"] = (rtype.p_hover + rtype.p_comm) * m["hover"] / 3600.0
            m["e_total"] = m["e_fly"] + m["e_hover"]
            m["soc"] = 1.0 - m["e_total"] / rtype.e_use
            m["chg"] = float(D.charge_time(m["soc"], inst.d["rbatt"][1]))
            m["t_back"] = m["t_end"] + D.relay_flight(rtype, inst.nodes, m["lon"], m["lat"], m["agl"])["t_back"]
        else:
            merged.append(dict(s))
    merged.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(merged, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]]
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return merged
