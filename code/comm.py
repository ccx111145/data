# -*- coding: utf-8 -*-
"""
comm.py —— 通信层：运输航迹抽样 + 直连/中继链路判定 + 通信缺口扫描

规则依据题目附录 3：
  * 端点三维位置：运输无人机按附录 2 的飞行海拔；G01 为 O01 地面海拔 + 天线离地 20 m；
    中继为悬停海拔。
  * 地形遮挡：由两端点三维连线与 30 m DEM 判定，遮挡附加损耗 L_obs。
  * 链路门限：双向取两方向较小者；P_th = P_sens + M。
  * 状态判定：直连可用 → 直连；否则接入链路与回传链路同时可用 → 中继；否则中断。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

import dcore as D

DT_SAMPLE = 10.0     # 航迹抽样步长 (s)


# ---------------------------------------------------------------------------
# 航迹抽样
# ---------------------------------------------------------------------------
def sortie_track(inst, s, start, dt_sample=DT_SAMPLE):
    """
    生成一个运输架次的通信端点采样序列。
    返回 dict(t=, lon=, lat=, alt=, phase=, area=)
    phase ∈ {'climb','cruise','descend','handover'}
    """
    stops = ["O01"] + list(s.areas) + ["O01"]
    ts, los_, las, als, phs, ars = [], [], [], [], [], []
    t = start + inst.types[s.g].t_prep + inst.types[s.g].t_load_box * sum(
        len(s.load[a]) for a in s.areas)
    # 飞行阶段（准备/装载在工位完成，不属于"爬升/巡航/下降/投送"通信阶段）
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        L = D.leg(inst.nodes, inst.types[s.g], a, b, 0.0)
        na, nb = inst.nodes[a], inst.nodes[b]
        # 爬升：在 a 点垂直爬升
        for x in _seq(L.h_up / inst.types[s.g].v_up, dt_sample, include_zero=(i > 0)):
            ts.append(t + x)
            los_.append(na.lon); las.append(na.lat)
            als.append(na.op_alt + (L.cruise_alt - na.op_alt) * (x / max(1e-9, L.h_up / inst.types[s.g].v_up)))
            phs.append("climb"); ars.append(a)
        t += L.h_up / inst.types[s.g].v_up
        # 巡航
        for x in _seq(L.dist / inst.types[s.g].v_cruise, dt_sample):
            f = x / max(1e-9, L.dist / inst.types[s.g].v_cruise)
            ts.append(t + x)
            los_.append(na.lon + (nb.lon - na.lon) * f)
            las.append(na.lat + (nb.lat - na.lat) * f)
            als.append(L.cruise_alt)
            phs.append("cruise"); ars.append("%s->%s" % (a, b))
        t += L.dist / inst.types[s.g].v_cruise
        # 下降
        for x in _seq(L.h_dn / inst.types[s.g].v_dn, dt_sample):
            f = x / max(1e-9, L.h_dn / inst.types[s.g].v_dn)
            ts.append(t + x)
            los_.append(nb.lon); las.append(nb.lat)
            als.append(L.cruise_alt + (nb.op_alt - L.cruise_alt) * f)
            phs.append("descend"); ars.append(b)
        t += L.h_dn / inst.types[s.g].v_dn
        # 服务区交接（悬停投送）
        if b != "O01":
            hold = inst.types[s.g].t_hand_base + inst.types[s.g].t_hand_box * len(s.load[b])
            for x in _seq(hold, dt_sample):
                ts.append(t + x)
                los_.append(nb.lon); las.append(nb.lat); als.append(nb.op_alt)
                phs.append("handover"); ars.append(b)
            t += hold
    return dict(t=np.array(ts), lon=np.array(los_), lat=np.array(las), alt=np.array(als),
                phase=np.array(phs), area=np.array(ars))


def _seq(dur, dt_sample, include_zero=True):
    if dur <= 1e-9:
        return []
    n = max(1, int(math.ceil(dur / dt_sample)))
    xs = np.linspace(0.0, dur, n + 1)[:-1] if include_zero else np.linspace(dt_sample, dur, n)
    return xs


# ---------------------------------------------------------------------------
# 链路判定（向量化）
# ---------------------------------------------------------------------------
class Link:
    def __init__(self, inst, dem=None, channel_model=None):
        self.inst = inst
        self.cp = inst.d["comm"]
        self.dem = dem or D.get_dem()
        #: 信道模型：'observed'（附件口径，FSPL + 固定遮挡损耗）
        #: 或 'p526' / 'p526ub'（ITU-R P.526 单刃峰 / 多刃峰上界）
        self.channel_model = channel_model or getattr(self.cp, "channel_model", "observed")
        self._diff = None
        if self.channel_model.startswith("p526"):
            import diffraction as _DF
            self._diff = _DF
        o = inst.nodes["O01"]
        self.gw = (o.lon, o.lat, o.elev + self.cp.gw_ant_h)
        self.l_dir = D.lmax_bidir(self.cp.transport, self.cp.gateway, self.cp)
        self.l_acc = D.lmax_bidir(self.cp.transport, self.cp.relay_access, self.cp)
        self.l_bh = D.lmax_bidir(self.cp.relay_backhaul, self.cp.gateway, self.cp)

    # -- 通用 -------------------------------------------------------------
    def _loss(self, p_fixed, pts, l_obs_on):
        pts = np.atleast_2d(pts)
        dh = _hav(p_fixed[0], p_fixed[1], pts[:, 0], pts[:, 1])
        d3 = np.sqrt(dh ** 2 + (p_fixed[2] - pts[:, 2]) ** 2)
        if self._diff is None:
            # 附件口径：二值遮挡 + 固定附加损耗
            blocked = D.los_blocked_batch(p_fixed, pts, self.dem)
            lp = np.asarray(D.fspl(self.cp.f_mhz, d3)) + (self.cp.l_obs if l_obs_on else 0.0) * blocked
            return lp, blocked, d3
        # ITU-R P.526：由地形剖面解析计算绕射损耗
        js, ju, nu, ne, ho, d1, d2 = self._diff.knife_edge_batch(
            p_fixed, pts, self.cp.f_mhz, self.dem,
            step=float(getattr(self.cp, "prof_step", 25.0)),
            k=float(getattr(self.cp, "k_earth", 4.0 / 3.0)))
        j = ju if self.channel_model.endswith("ub") else js
        lp = np.asarray(D.fspl(self.cp.f_mhz, d3)) + (j if l_obs_on else 0.0)
        blocked = j > 0.5                      # 供既有接口沿用：是否产生实质绕射损耗
        return lp, blocked, d3

    def direct_ok(self, draw_pts):
        """运输无人机各采样点与 G01 的直连可用性 (bool 数组)。"""
        lp, blocked, d3 = self._loss(self.gw, draw_pts, True)
        return lp <= self.l_dir + 1e-9, lp, blocked

    def access_ok(self, transport_pts, relay_pt):
        """运输无人机 -> 中继接入链路（对固定中继位置）。"""
        lp, blocked, d3 = self._loss(relay_pt, transport_pts, True)
        return lp <= self.l_acc + 1e-9, lp, blocked

    def backhaul_ok(self, relay_pts):
        """中继 -> G01 回传链路（对一批中继候选位置）。"""
        lp, blocked, d3 = self._loss(self.gw, relay_pts, True)
        return lp <= self.l_bh + 1e-9, lp, blocked

    def access_margin(self, transport_pts, relay_pt):
        lp, blocked, d3 = self._loss(relay_pt, transport_pts, True)
        return self.l_acc - lp

    def backhaul_margin(self, relay_pts):
        lp, blocked, d3 = self._loss(self.gw, relay_pts, True)
        return self.l_bh - lp


def _hav(lon1, lat1, lon2, lat2):
    p1 = math.radians(lat1)
    p2 = np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dp / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * D.R_EARTH * np.arcsin(np.minimum(1.0, np.sqrt(a)))


# ---------------------------------------------------------------------------
# 通信缺口扫描
# ---------------------------------------------------------------------------
def scan_direct(inst, tracks, link: Link):
    """对每个架次航迹计算直连可用性；返回 {k: dict(t, ok, uncov_idx)} 及总缺口统计。"""
    out = {}
    tot = 0
    unc = 0
    for k, tr in tracks.items():
        ok, lp, blocked = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        out[k] = dict(track=tr, ok=ok, lp=lp, blocked=blocked, uncov=np.nonzero(~ok)[0])
        tot += len(ok)
        unc += int((~ok).sum())
    return out, dict(n_sample=tot, n_uncov=unc, uncov_rate=unc / max(1, tot))


# ---------------------------------------------------------------------------
# 影子模型：把"直连不可用时长"做成可缓存的快速估计，供 Q3 联合优化使用
# ---------------------------------------------------------------------------
class ShadowModel:
    """
    给定机型与航段，巡航海拔只取决于航段两端点与 DEM，因此"该航段上直连不可用的时长"
    可以一次性算好并缓存。垂直段（爬升/下降/投送悬停）只取决于节点与海拔，同样可缓存。
    这样把 Q3 的通信目标压缩为 O(航段数) 的查表，使通信感知的 ALNS 成为可能。
    """

    def __init__(self, inst, dem=None, step=100.0):
        self.inst = inst
        self.link = Link(inst, dem)
        self.step = step
        self._leg = {}
        self._vert = {}

    # -- 水平航段（固定巡航海拔） ------------------------------------------
    def leg_shadow(self, g, a, b):
        key = (g, a, b)
        hit = self._leg.get(key)
        if hit is not None:
            return hit
        inst = self.inst
        L = D.leg(inst.nodes, inst.types[g], a, b, 0.0)
        n = max(4, int(math.ceil(L.dist / self.step)) + 1)
        f = np.linspace(0.0, 1.0, n)
        na, nb = inst.nodes[a], inst.nodes[b]
        pts = np.c_[na.lon + (nb.lon - na.lon) * f,
                    na.lat + (nb.lat - na.lat) * f,
                    np.full(n, L.cruise_alt)]
        ok, lp, bl = self.link.direct_ok(pts)
        frac = float((~ok).mean())
        res = (frac * L.t_flight, frac)
        self._leg[key] = res
        return res

    # -- 垂直段（节点处爬升/下降/悬停） -------------------------------------
    def vert_shadow(self, node, alt):
        key = (node, round(float(alt), 1))
        hit = self._vert.get(key)
        if hit is not None:
            return hit
        nd = self.inst.nodes[node]
        ok, lp, bl = self.link.direct_ok(np.array([[nd.lon, nd.lat, float(alt)]]))
        v = not bool(ok[0])
        self._vert[key] = v
        return v

    # -- 架次缺口时长 -------------------------------------------------------
    def sortie_gap(self, s):
        """返回该架次直连不可用的总时长 (s)（爬升+巡航+下降+投送悬停）。"""
        inst = self.inst
        dt = inst.types[s.g]
        stops = ["O01"] + list(s.areas) + ["O01"]
        gap = 0.0
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            L = D.leg(inst.nodes, dt, a, b, 0.0)
            # 爬升
            na, nb = inst.nodes[a], inst.nodes[b]
            t_climb = L.h_up / dt.v_up
            n = max(2, int(math.ceil(t_climb / 20.0)))
            alts = na.op_alt + (L.cruise_alt - na.op_alt) * np.linspace(0, 1, n)
            gap += t_climb * np.mean([self.vert_shadow(a, x) for x in alts])
            # 巡航
            gap += self.leg_shadow(s.g, a, b)[0]
            # 下降
            t_desc = L.h_dn / dt.v_dn
            n = max(2, int(math.ceil(t_desc / 20.0)))
            alts = L.cruise_alt + (nb.op_alt - L.cruise_alt) * np.linspace(0, 1, n)
            gap += t_desc * np.mean([self.vert_shadow(b, x) for x in alts])
            # 投送悬停
            if b != "O01":
                hold = dt.t_hand_base + dt.t_hand_box * len(s.load[b])
                if self.vert_shadow(b, nb.op_alt):
                    gap += hold
        return gap

    def solution_gap(self, sorties):
        return sum(self.sortie_gap(s) for s in sorties)
