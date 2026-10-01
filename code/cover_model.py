# -*- coding: utf-8 -*-
"""
cover_model.py —— 通信兼容性快速评估模型（Q3 联合优化的核心）

关键困难
--------
中继一次架次只能停在一个悬停点上，换位必须回 O01 再出发（约 15–20 min 黑障），
因此**运输方案必须与少数几个固定中继位置"通信兼容"**：把任务期切成若干相，
每一相内所有"直连不可用"的运输机都能被同一个悬停点覆盖。

快速评估
--------
把一个架次的直连不可用时长拆成"航段级"量：
  * 水平航段 (机型 g, 起点 a, 终点 b)：巡航海拔只由端点与 DEM 决定，
    因此该航段的轨迹是固定的 ⇒ 对任意候选悬停点 p，"被 p 覆盖的时长占比"可一次性算好并缓存；
  * 节点垂直段 (节点 a, 海拔区间)：同理按 (节点, 海拔, p) 缓存。
这样"某架次的不可用时长中有多少无法被 p 覆盖"可在 O(航段数) 内查表得到，
从而把通信兼容性目标放进 ALNS 的目标函数。
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

import dcore as D
import comm as C
import relay as R


class CoverModel:
    def __init__(self, inst, palette=None, dem=None, step=120.0, spacing=0.0045,
                 pad=0.022, agl=(80.0, 160.0, 300.0), n_palette=140, verbose=False,
                 channel_model=None):
        self.inst = inst
        self.link = C.Link(inst, dem, channel_model=channel_model)
        self.step = step
        self._leg = {}
        self._vert = {}
        self._sortie = {}
        self._dl = {}
        self._ui = {}
        if palette is None:
            palette = self._default_palette(spacing, pad, agl, n_palette, verbose)
        self.palette = np.asarray(palette, dtype=np.float64)     # (P, 3)
        self._bh = None

    # -- 调色板：覆盖 DEM 范围内的高点网格，只保留回传链路可用的点 -------------
    def _default_palette(self, spacing, pad, agl, n_palette, verbose):
        inst = self.inst
        lo = [n.lon for n in inst.nodes.values()]
        la = [n.lat for n in inst.nodes.values()]
        cand, meta = R.candidate_grid(inst, np.array(lo), np.array(la), spacing=spacing,
                                      pad=pad, agl=agl)
        ok, lp, bl = self.link.backhaul_ok(cand)
        cand = cand[ok]
        if verbose:
            print("  调色板：回传可用候选 %d" % len(cand))
        # 用贪心最大化"对全部需求点的覆盖数"来挑点（这里用节点+航段采样点近似）
        pts = self._probe_points()
        cov = np.zeros(len(cand), dtype=np.int64)
        grid = np.linspace(0, len(cand) - 1, min(len(cand), 400)).astype(int)
        sub = cand[grid]
        for i in range(0, len(pts), 40):
            blk = pts[i:i + 40]
            for j, p in enumerate(sub):
                pass
        # 向量化：access_ok 以固定运输机点为批
        cover = np.zeros((len(sub),), dtype=np.int64)
        for i in range(len(sub)):
            lp2, blk2, d3 = self.link._loss(tuple(sub[i]), pts, True)
            cover[i] = int((lp2 <= self.link.l_acc + 1e-9).sum())
        order = np.argsort(-cover)
        pick = sub[order[:n_palette]]
        if verbose:
            print("  调色板：选中 %d 个点（覆盖探测点 %.0f–%.0f）"
                  % (len(pick), cover[order[-1]], cover[order[0]]))
        return pick

    def _probe_points(self):
        """用于挑选调色板的探测点：各节点上空若干海拔 + 节点间航段中点。"""
        inst = self.inst
        pts = []
        ids = ["O01"] + inst.SIDS
        for a in ids:
            na = inst.nodes[a]
            for h in (120.0, 260.0, 420.0, 600.0):
                pts.append((na.lon, na.lat, h))
        for a in ids:
            for b in ids:
                if a >= b:
                    continue
                na, nb = inst.nodes[a], inst.nodes[b]
                L = D.leg(inst.nodes, inst.types["C"], a, b, 0.0)
                for f in (0.25, 0.5, 0.75):
                    pts.append((na.lon + (nb.lon - na.lon) * f,
                                na.lat + (nb.lat - na.lat) * f, L.cruise_alt))
        return np.array(pts, dtype=np.float64)

    # -- 航段 / 节点缓存 ----------------------------------------------------
    def leg_cover(self, g, a, b):
        """返回 (被调色板各点覆盖的时长占比数组 (P,), 航段飞行时间, 是否遮挡无关量)"""
        key = (g, a, b)
        hit = self._leg.get(key)
        if hit is not None:
            return hit
        inst = self.inst
        dt = inst.types[g]
        L = D.leg(inst.nodes, dt, a, b, 0.0)
        n = max(4, int(math.ceil(L.dist / self.step)) + 1)
        f = np.linspace(0.0, 1.0, n)
        na, nb = inst.nodes[a], inst.nodes[b]
        pts = np.c_[na.lon + (nb.lon - na.lon) * f,
                    na.lat + (nb.lat - na.lat) * f,
                    np.full(n, L.cruise_alt)]
        P = len(self.palette)
        cov = np.zeros(P)
        for j in range(P):
            lp, blk, d3 = self.link._loss(tuple(self.palette[j]), pts, True)
            cov[j] = float((lp <= self.link.l_acc + 1e-9).mean())
        # 直连可用占比同样可算（用于"不可用时长"）
        okd, lpd, blkd = self.link.direct_ok(pts)
        unc = float((~okd).mean())
        res = (cov, float(unc * L.t_flight), float(L.t_flight))
        self._leg[key] = res
        return res

    def vert_cover(self, node, alt):
        key = (node, round(float(alt), 0))
        hit = self._vert.get(key)
        if hit is not None:
            return hit
        nd = self.inst.nodes[node]
        p = np.array([[nd.lon, nd.lat, float(alt)]])
        okd, _, _ = self.link.direct_ok(p)
        P = len(self.palette)
        cov = np.zeros(P, dtype=bool)
        for j in range(P):
            lp, blk, d3 = self.link._loss(tuple(self.palette[j]), p, True)
            cov[j] = bool(lp[0] <= self.link.l_acc + 1e-9)
        res = (not bool(okd[0]), cov)
        self._vert[key] = res
        return res

    # -- 架次级：不可用时长中"无法被任一单点覆盖"的最小量 --------------------
    def sortie_profile(self, s):
        """
        返回 dict(uncovered=总直连不可用时长, best_p=最适合的调色板下标,
                  best_left=在该点下仍无法覆盖的时长, per_p=(P,) 各点剩余时长)
        """
        key = (s.g, tuple(s.areas), tuple(len(s.load[a]) for a in s.areas),
               tuple(sorted(b for a in s.areas for b in s.load[a])))
        hit = self._sortie.get(key)
        if hit is not None:
            return hit
        inst = self.inst
        dt = inst.types[s.g]
        stops = ["O01"] + list(s.areas) + ["O01"]
        P = len(self.palette)
        left = np.zeros(P)
        total = 0.0
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            L = D.leg(inst.nodes, dt, a, b, 0.0)
            # 爬升
            tc = L.h_up / dt.v_up
            na, nb = inst.nodes[a], inst.nodes[b]
            nseg = max(2, int(math.ceil(tc / 30.0)))
            for al in np.linspace(na.op_alt, L.cruise_alt, nseg):
                unc, cov = self.vert_cover(a, al)
                if unc:
                    total += tc / nseg
                    left += (tc / nseg) * (~cov)
            # 巡航
            cov, unc_t, t_all = self.leg_cover(s.g, a, b)
            total += unc_t
            left += cov * 0.0 + (unc_t * (1.0 - cov))
            # 下降
            td = L.h_dn / dt.v_dn
            nseg = max(2, int(math.ceil(td / 30.0)))
            for al in np.linspace(L.cruise_alt, nb.op_alt, nseg):
                unc, covv = self.vert_cover(b, al)
                if unc:
                    total += td / nseg
                    left += (td / nseg) * (~covv)
            # 投送悬停
            if b != "O01":
                hold = dt.t_hand_base + dt.t_hand_box * len(s.load[b])
                unc, covv = self.vert_cover(b, nb.op_alt)
                if unc:
                    total += hold
                    left += hold * (~covv)
        j = int(np.argmin(left))
        res = dict(uncovered=float(total), best_p=j, best_left=float(left[j]),
                   per_p=left, pos=tuple(self.palette[j]))
        if len(self._sortie) < 400000:
            self._sortie[key] = res
        return res

    def solution_profile(self, sorties):
        return [self.sortie_profile(s) for s in sorties]

    # ------------------------------------------------------------------
    # 直连不可用"模式"缓存（用于估计**同时失联**的架次数）
    # ------------------------------------------------------------------
    def _dleg(self, g, a, b):
        key = (g, a, b)
        hit = self._dl.get(key)
        if hit is not None:
            return hit
        inst = self.inst
        dt = inst.types[g]
        L = D.leg(inst.nodes, dt, a, b, 0.0)
        n = max(4, int(math.ceil(L.dist / self.step)) + 1)
        f = np.linspace(0.0, 1.0, n)
        na, nb = inst.nodes[a], inst.nodes[b]
        pts = np.c_[na.lon + (nb.lon - na.lon) * f,
                    na.lat + (nb.lat - na.lat) * f,
                    np.full(n, L.cruise_alt)]
        ok, lp, bl = self.link.direct_ok(pts)
        res = (~ok, L, na, nb)
        self._dl[key] = res
        return res

    def uncovered_intervals(self, s):
        """
        返回该架次"直连不可用"的相对时间区间列表 [(tau0, tau1)]（相对于架次开始时刻）。
        爬升/下降段按中点海拔判定（保守取整段），巡航段按沿线采样点的连续段给出。
        """
        key = ("U", s.g, tuple(s.areas), tuple(len(s.load[a]) for a in s.areas))
        hit = self._ui.get(key)
        if hit is not None:
            return hit
        inst = self.inst
        dt = inst.types[s.g]
        t = dt.t_prep + dt.t_load_box * sum(len(s.load[a]) for a in s.areas)
        out = []
        stops = ["O01"] + list(s.areas) + ["O01"]
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            mask, L, na, nb = self._dleg(s.g, a, b)
            # 爬升
            tc = L.h_up / dt.v_up
            if tc > 0:
                mid = 0.5 * (na.op_alt + L.cruise_alt)
                unc, _ = self.vert_cover(a, mid)
                if unc:
                    out.append((t, t + tc))
            t += tc
            # 巡航
            tcr = L.dist / dt.v_cruise
            if mask.any():
                idx = np.nonzero(mask)[0]
                brk = np.nonzero(np.diff(idx) > 1)[0]
                for seg in np.split(idx, brk + 1):
                    f0 = seg[0] / max(1, len(mask) - 1)
                    f1 = seg[-1] / max(1, len(mask) - 1)
                    out.append((t + tcr * f0, t + tcr * f1 + tcr / max(1, len(mask) - 1)))
            t += tcr
            # 下降
            td = L.h_dn / dt.v_dn
            if td > 0:
                mid = 0.5 * (L.cruise_alt + nb.op_alt)
                unc, _ = self.vert_cover(b, mid)
                if unc:
                    out.append((t, t + td))
            t += td
            # 投送悬停
            if b != "O01":
                hold = dt.t_hand_base + dt.t_hand_box * len(s.load[b])
                unc, _ = self.vert_cover(b, nb.op_alt)
                if unc:
                    out.append((t, t + hold))
                t += hold
        # 合并
        merged = []
        for (x, y) in sorted(out):
            if merged and x <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], y))
            else:
                merged.append((x, y))
        if len(self._ui) < 400000:
            self._ui[key] = merged
        return merged

    def uncovered_concurrency(self, sorties, assign, grid=30.0, cap=1):
        """把各架次的失联区间投影到统一时间栅格，返回
        (Σ max(0, 并发-c) * grid, 峰值并发, 总失联时长)。"""
        ivs = []
        for k, s in enumerate(sorties):
            st = assign[k]["start"]
            for (x, y) in self.uncovered_intervals(s):
                if y > x:
                    ivs.append((st + x, st + y))
        if not ivs:
            return 0.0, 0, 0.0
        tmax = max(y for _, y in ivs)
        n = int(math.ceil(tmax / grid)) + 1
        cnt = np.zeros(n + 1, dtype=np.int32)
        for (x, y) in ivs:
            i0 = int(math.floor(x / grid)); i1 = min(n, int(math.ceil(y / grid)))
            if i1 > i0:
                cnt[i0] += 1
                cnt[i1] -= 1
        c = np.cumsum(cnt)[:n]
        excess = float(np.maximum(0, c - cap).sum() * grid)
        return excess, int(c.max()), float(sum(y - x for x, y in ivs))
