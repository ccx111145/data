# -*- coding: utf-8 -*-
"""
relay.py —— 中继覆盖求解器

思路
----
1. 把"运输无人机在时刻 t 失去直连"的每个采样点定义为一个**通信需求** r=(t, 3D 位置)。
2. 中继悬停候选点：DEM 覆盖范围内的网格点 × 若干悬停离地高度（<= 300 m）。
3. coverage[r][c] = 接入链路可用(运输机↔中继) 且 回传链路可用(中继↔G01)。
4. 对每个候选点 c 定义"完全覆盖时刻集" F_c = { t : 该时刻所有需求都被 c 覆盖 }；
   F_c 的极大连续时段即为该点可独立承担服务的时段（一个中继架次只能停在一个点上）。
5. 用区间覆盖（贪心，最优）选择最少的 (候选点, 时段) 组合覆盖全部需求时刻，
   再校验任意时刻同时占用的中继架次数 <= 2（中继无人机台数）。
6. 对选中的时段生成中继架次：分配中继无人机与能源组件，核算往返能耗 + 悬停/通信能耗，
   校验返航电量下限、充电周转与架次周转时间。
"""
from __future__ import annotations

import itertools
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

import dcore as D
import comm as C

OUT = D.RESULTS


# ---------------------------------------------------------------------------
# 候选点
# ---------------------------------------------------------------------------
def candidate_grid(inst, req_lon, req_lat, spacing=0.0030, pad=0.018,
                   agl=(50.0, 150.0, 300.0), dem=None):
    dem = dem or D.get_dem()
    lo0, lo1 = req_lon.min() - pad, req_lon.max() + pad
    la0, la1 = req_lat.min() - pad, req_lat.max() + pad
    lo0 = max(lo0, dem.lon.min()); lo1 = min(lo1, dem.lon.max())
    la0 = max(la0, dem.lat.min()); la1 = min(la1, dem.lat.max())
    lons = np.arange(lo0, lo1 + 1e-12, spacing)
    lats = np.arange(la0, la1 + 1e-12, spacing)
    pts = []
    meta = []
    for h in agl:
        for la in lats:
            for lo in lons:
                g = float(dem.at(lo, la))
                pts.append((lo, la, g + h))
                meta.append((lo, la, g, h))
    return np.array(pts, dtype=np.float64), meta


# ---------------------------------------------------------------------------
# 覆盖矩阵
# ---------------------------------------------------------------------------
def coverage_matrix(link: C.Link, req_pts: np.ndarray, cand: np.ndarray, chunk=64):
    """返回 (cov[n_req, n_cand], bh[n_cand], acc_loss[n_req,n_cand])。"""
    bh_ok, bh_lp, _ = link.backhaul_ok(cand)
    n = len(req_pts)
    m = len(cand)
    acc = np.empty((n, m), dtype=np.float32)
    for i0 in range(0, n, chunk):
        i1 = min(n, i0 + chunk)
        for i in range(i0, i1):
            lp, blocked, d3 = link._loss(tuple(req_pts[i]), cand, True)
            acc[i] = lp
    cov = (acc <= link.l_acc + 1e-9) & bh_ok[None, :]
    return cov, bh_ok, acc


# ---------------------------------------------------------------------------
# 极大覆盖时段
# ---------------------------------------------------------------------------
def fully_covering_runs(req_t: np.ndarray, cov: np.ndarray, cand_meta):
    """
    req_t 已按时间升序排列；同一时刻可能有多条需求（cov 的行）。
    返回 [(t_start, t_end, cand_index, n_covered)]，为该候选点可连续完全覆盖需求的极大时段。
    """
    n, m = cov.shape
    # 每个时刻的索引分组
    order = np.argsort(req_t, kind="stable")
    ts = req_t[order]
    uniq, starts = np.unique(ts, return_index=True)
    groups = np.split(order, starts[1:])
    # 对每个候选点：判断每个时刻组是否被完全覆盖
    full = np.ones((len(uniq), m), dtype=bool)
    for gi, g in enumerate(groups):
        full[gi] = cov[g].all(axis=0)
    runs = []
    for c in range(m):
        col = full[:, c]
        i = 0
        while i < len(uniq):
            if not col[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(uniq) and col[j + 1]:
                j += 1
            runs.append((float(uniq[i]), float(uniq[j]), c, len(uniq[i:j + 1])))
            i = j + 1
    return runs


def cover_schedule(req_t: np.ndarray, runs, horizon_pad=60.0):
    """
    区间覆盖：用最少的 run 覆盖所有需求时刻（贪心，一维区间覆盖最优）。
    返回选中的 run 列表。
    """
    uniq = np.unique(req_t)
    chosen = []
    idx = 0
    n = len(uniq)
    while idx < n:
        t0 = uniq[idx]
        best = None
        for r in runs:
            if r[0] <= t0 + 1e-9 and r[1] >= t0 - 1e-9:
                key = (r[1], r[3])
                if best is None or key > (best[1], best[3]):
                    best = r
        if best is None:
            return None, t0          # 该时刻无法被任何候选点完全覆盖
        chosen.append(best)
        # 跳过已覆盖的时刻
        while idx < n and uniq[idx] <= best[1] + 1e-9:
            idx += 1
    return chosen, None


def merge_runs(chosen):
    """合并同一候选点且相邻的时段；并按时段起点排序。"""
    chosen = sorted(chosen, key=lambda r: (r[2], r[0]))
    out = []
    for r in chosen:
        if out and out[-1][2] == r[2] and r[0] <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], r[1]), r[2], out[-1][3] + r[3])
        else:
            out.append(list(r) if False else (r[0], r[1], r[2], r[3]))
    return sorted(out, key=lambda r: r[0])


# ---------------------------------------------------------------------------
# 中继架次生成
# ---------------------------------------------------------------------------
@dataclass
class RelaySortie:
    rid: int
    drone: str
    comp: str
    lon: float
    lat: float
    hover_alt: float
    agl: float
    t_start: float
    t_link: float          # 建链完成时刻
    t_end: float           # 服务结束时刻
    t_back: float          # 返回 O01 时刻
    e_fly: float
    e_hover: float
    e_total: float
    soc_end: float
    chg: float


def build_relay_sorties(inst, chosen_runs, cand_meta, cand_pts, rtype, t_grid_start,
                        prep_extra=0.0):
    """
    为选中的覆盖时段生成中继架次，分配 2 架中继无人机与 6 组能源组件。
    返回 (sorties, infeasible_reasons)
    """
    rd = {"R01": 0.0, "R02": 0.0}            # 无人机可用时刻
    comp_free = {("R", k): 0.0 for k in range(1, inst.d["rbatt"][0] + 1)}
    out = []
    bad = []
    for i, (ta, tb, ci, _n) in enumerate(sorted(chosen_runs, key=lambda r: r[0])):
        lo, la, g, h = cand_meta[ci]
        hov = h
        rf = D.relay_flight(rtype, inst.nodes, lo, la, hov)
        # 需要提前到场并建链，服务结束后返航
        link_ready = ta
        t_start = link_ready - rtype.t_link - rf["t_out"]
        t_end = tb
        t_back = t_end + rf["t_back"]
        hover_dur = t_end - link_ready
        e_hover = (rtype.p_hover + rtype.p_comm) * hover_dur / 3600.0
        e_total = rf["e_fly"] + e_hover
        soc = 1.0 - e_total / rtype.e_use
        if soc < rtype.rho - 1e-9:
            bad.append(dict(reason="电量不足", lon=lo, lat=la, agl=hov, ta=ta, tb=tb,
                            e_total=e_total, soc=soc))
            continue
        chg = float(D.charge_time(soc, inst.d["rbatt"][1]))
        # 选择最早可用的中继无人机与能源组件
        dr = min(rd, key=lambda k: rd[k])
        cp = min(comp_free, key=lambda k: comp_free[k])
        if max(rd[dr], comp_free[cp]) > t_start + 1e-6:
            # 资源未就绪：记录（可通过延后服务时段或增加资源缓解）
            bad.append(dict(reason="资源未就绪", need=t_start,
                            drone_free=rd[dr], comp_free=comp_free[cp]))
        rd[dr] = t_back + rtype.t_turn
        comp_free[cp] = t_back + chg
        out.append(RelaySortie(rid=i + 1, drone=dr, comp="R-E%d" % cp[1], lon=lo, lat=la,
                               hover_alt=g + hov, agl=hov, t_start=t_start, t_link=link_ready,
                               t_end=t_end, t_back=t_back, e_fly=rf["e_fly"],
                               e_hover=e_hover, e_total=e_total, soc_end=soc, chg=chg))
    return out, bad
