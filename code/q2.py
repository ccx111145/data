# -*- coding: utf-8 -*-
"""
q2.py —— 问题二：异构运输无人机多点多架次运输调度

模型
----
决策：货箱组批（每个货箱恰好一次）、每个架次访问的服务区顺序、机型、执行无人机、
      共享电池、架次开始时刻。
约束：
  C1 货箱不可拆分、每箱一次；
  C2 载质量 <= q_max(g)、装载体积 <= v_cap(g)；
  C3 架次总能耗 <= (1-rho_g) * E_use(g)（返航安全余量，逐航段累计载荷）；
  C4 同型实体无人机在同一时刻只能执行一个架次；
  C5 同型共享电池：占用时段 [s, s+D) 与充电时段 [e, e+t_chg(SOC_e)) 不得与其他占用重叠
     （两阶段等效充电模型）；
  C6 医疗货箱 <= 期望送达时间；首批保障货箱 <= 首批截止时间；
  C7 每个架次可访问一个或多个服务区，完成后返回 O01。

算法
----
外层：ALNS（自适应大邻域搜索）在"架次集合"空间搜索（多目标加权标量化）；
内层：快速贪心排程（无人机-电池双资源时间轴）给出可行排程与各目标值；
终局：CP-SAT 对固定架次集合做**精确排程打磨**（起止时刻 + 无人机/电池可行性最优）。
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

import dcore as D

OUT = D.RESULTS
os.makedirs(OUT, exist_ok=True)
HORIZON = 43200.0          # 12 h 排程视界
BIG = 1e9


# ===========================================================================
# 基础对象
# ===========================================================================
class Instance:
    def __init__(self):
        d = D.load_all()
        self.d = d
        self.nodes = d["nodes"]
        self.types = d["ttypes"]
        self.boxes = d["boxes"]
        self.SIDS = d["SIDS"]
        self.fleet = d["fleet"]
        self.batt = d["batt"]
        self.rho = {g: d["ttypes"][g].rho for g in ("A", "B", "C")}
        self.bidx = D.box_index(self.boxes)
        self.boxes_by_area = {s: [b for b in self.boxes if b.sid == s] for s in self.SIDS}
        # 硬时限
        self.hard = {}
        self.soft = {}
        self.wpri = {}
        for b in self.boxes:
            dl = BIG
            if b.first_batch:
                dl = min(dl, b.first_deadline)
            if b.kind == "医疗物资":
                dl = min(dl, b.expect_time)
            self.hard[b.bid] = dl
            self.soft[b.bid] = b.expect_time
            self.wpri[b.bid] = b.priority
        self.tprep = {g: self.types[g].t_prep for g in ("A", "B", "C")}
        self.euse = {g: self.types[g].e_use for g in ("A", "B", "C")}
        self.tfull = {g: self.batt[g][1] for g in ("A", "B", "C")}
        self.nbat = {g: self.batt[g][0] for g in ("A", "B", "C")}
        self.ndrone = {g: len(self.fleet[g]) for g in ("A", "B", "C")}


@dataclass
class Sortie:
    g: str
    areas: List[str]                 # 访问顺序（不含 O01）
    load: Dict[str, List[str]]       # 服务区 -> 货箱编号
    dur: float = 0.0
    E: float = 0.0
    offs: Dict[str, float] = field(default_factory=dict)   # 服务区 -> 相对开始的交付完成时刻

    def mass(self, bidx):
        return sum(bidx[b].mass for s in self.areas for b in self.load[s])

    def vol(self, bidx):
        return sum(bidx[b].vol for s in self.areas for b in self.load[s])


# ===========================================================================
# 架次物理量计算
# ===========================================================================
def route_metrics(inst: Instance, g: str, areas: Sequence[str], load: Dict[str, List[str]]):
    """给定机型、访问顺序与各服务区卸下的货箱，计算 (时长, 能耗, 逐区交付偏移)。"""
    dt = inst.types[g]
    bx = inst.bidx
    stops = ["O01"] + list(areas) + ["O01"]
    remaining = sum(bx[b].mass for s in areas for b in load[s])
    loads = [remaining]
    n_at = [0]
    for s in areas:
        remaining -= sum(bx[b].mass for b in load[s])
        loads.append(remaining)
        n_at.append(len(load[s]))
    n_at.append(0)
    totE, legs = D.sortie_energy(inst.nodes, dt, stops, loads)
    t = dt.t_prep + dt.t_load_box * n_at[1:len(areas) + 1].__len__() * 0  # 占位，下面重算
    t = dt.t_prep + dt.t_load_box * sum(len(load[s]) for s in areas)
    offs = {}
    for i, s in enumerate(areas, start=1):
        t += legs[i - 1].t_flight
        t += dt.t_hand_base + dt.t_hand_box * len(load[s])
        offs[s] = t
    t += legs[-1].t_flight
    return t, totE, offs, legs


def best_route(inst: Instance, g: str, area_boxes: Dict[str, List[str]], exact_limit=6):
    """在给定各服务区货箱集合下，寻找使"作业时间"最短（并列取能耗小）的访问顺序。"""
    areas = list(area_boxes.keys())
    if len(areas) == 1:
        t, E, offs, legs = route_metrics(inst, g, areas, area_boxes)
        return areas, t, E, offs, legs
    import itertools
    best = None
    if len(areas) <= exact_limit:
        for perm in itertools.permutations(areas):
            r = route_metrics(inst, g, list(perm), area_boxes)
            key = (r[0], r[1])
            if best is None or key < best[0]:
                best = (key, list(perm), r)
    else:
        # 最近邻 + 2-opt
        cur = sorted(areas, key=lambda s: D.haversine(inst.nodes["O01"].lon, inst.nodes["O01"].lat,
                                                      inst.nodes[s].lon, inst.nodes[s].lat))
        improved = True
        while improved:
            improved = False
            for i in range(len(cur) - 1):
                for j in range(i + 1, len(cur)):
                    cand = cur[:i] + cur[i:j + 1][::-1] + cur[j + 1:]
                    a = route_metrics(inst, g, cur, area_boxes)
                    b = route_metrics(inst, g, cand, area_boxes)
                    if (b[0], b[1]) < (a[0], a[1]):
                        cur = cand
                        improved = True
        r = route_metrics(inst, g, cur, area_boxes)
        best = ((r[0], r[1]), cur, r)
    return best[1], best[2][0], best[2][1], best[2][2], best[2][3]


_FEAS_CACHE: Dict[tuple, tuple] = {}


def sortie_feasible(inst: Instance, g: str, area_boxes: Dict[str, List[str]]):
    """检查载质量/体积/返航能量。返回 (可行?, (顺序, 时长, 能耗, 偏移))。"""
    if not any(area_boxes.values()):
        return False, None
    key = (g, tuple(sorted((a, tuple(sorted(bs))) for a, bs in area_boxes.items() if bs)))
    hit = _FEAS_CACHE.get(key)
    if hit is not None:
        return hit
    dt = inst.types[g]
    m = sum(inst.bidx[b].mass for s in area_boxes for b in area_boxes[s])
    v = sum(inst.bidx[b].vol for s in area_boxes for b in area_boxes[s])
    if m > dt.q_max + 1e-9 or v > dt.v_cap + 1e-9:
        _FEAS_CACHE[key] = (False, None)
        return False, None
    areas, t, E, offs, legs = best_route(inst, g, area_boxes)
    res = (True, (areas, t, E, offs)) if E <= (1 - dt.rho) * dt.e_use + 1e-9 else (False, None)
    if len(_FEAS_CACHE) < 600_000:
        _FEAS_CACHE[key] = res
    return res


def make_sortie(inst: Instance, g: str, area_boxes: Dict[str, List[str]]) -> Sortie | None:
    ok, r = sortie_feasible(inst, g, area_boxes)
    if not ok:
        return None
    areas, t, E, offs = r
    return Sortie(g=g, areas=areas, load={s: list(area_boxes[s]) for s in areas}, dur=t, E=E, offs=offs)


def refresh(inst: Instance, s: Sortie) -> bool:
    ab = {a: s.load[a] for a in s.load if s.load[a]}
    if not ab:
        return False
    ok, r = sortie_feasible(inst, s.g, ab)
    if not ok:
        return False
    s.areas, s.dur, s.E, s.offs = r[0], r[1], r[2], r[3]
    s.load = {a: s.load[a] for a in s.areas}
    return True


# ===========================================================================
# 贪心排程：无人机 + 共享电池双资源时间轴
# ===========================================================================
def schedule_greedy(inst: Instance, sorties: List[Sortie], order_key="hs", air_cap=None):
    """列表排程。order_key:
         'hs'  主键硬时限、次键期望送达时间（默认）
         'soft'按最早期望送达时间
         'hard'按最早硬时限
         'long'/'short' 按时长
    air_cap: 若给定，则强制**同时在空中**的运输架次数不超过该值
             （Q3 要求：2 架中继才能保障全部失联运输机）。
    """
    K = len(sorties)
    idx = list(range(K))
    if order_key == "hs":
        def key(k):
            s = sorties[k]
            hd = min(inst.hard[b] for a in s.areas for b in s.load[a])
            sd = min(inst.soft[b] for a in s.areas for b in s.load[a])
            return (hd, sd, s.dur)
        idx.sort(key=key)
    elif order_key == "soft":
        due = [min(inst.soft[b] for a in s.areas for b in s.load[a]) for s in sorties]
        idx.sort(key=lambda k: due[k])
    elif order_key == "hard":
        due = [min(inst.hard[b] for a in s.areas for b in s.load[a]) for s in sorties]
        idx.sort(key=lambda k: due[k])
    elif order_key == "long":
        idx.sort(key=lambda k: -sorties[k].dur)
    else:
        idx.sort(key=lambda k: sorties[k].dur)

    drone_free = {g: [0.0] * inst.ndrone[g] for g in ("A", "B", "C")}
    bat_free = {g: [0.0] * inst.nbat[g] for g in ("A", "B", "C")}
    busy = []                      # 已在空区间 [(start, end)]
    assign, deliver = {}, {}
    for k in idx:
        s = sorties[k]
        g = s.g
        di = int(np.argmin(drone_free[g]))
        d_free = drone_free[g][di]
        bi = int(np.argmin(bat_free[g]))
        b_free = bat_free[g][bi]
        start = max(d_free, b_free)
        if air_cap is not None:
            start = _fit_start(start, s.dur, busy, air_cap)
        end = start + s.dur
        soc_end = 1.0 - s.E / inst.euse[g]
        r = float(D.charge_time(soc_end, inst.tfull[g]))
        drone_free[g][di] = end
        bat_free[g][bi] = end + r
        busy.append((start, end))
        assign[k] = dict(drone=inst.fleet[g][di], battery="%s-B%d" % (g, bi + 1),
                         start=start, end=end, soc=soc_end, chg=r)
        for a in s.areas:
            for b in s.load[a]:
                deliver[b] = start + s.offs[a]
    makespan = max(v["end"] for v in assign.values()) if assign else 0.0
    return assign, makespan, deliver


def _fit_start(start, dur, busy, cap):
    """把架次开始时刻向后推，使 [start, start+dur) 内已在空架次数 <= cap-1。"""
    if not busy:
        return start
    ev = sorted(busy)
    t = start
    for _ in range(len(ev) + 4):
        n = 0
        latest = t
        # 扫描区间内的最大重叠
        pts = [t]
        for (a, b) in ev:
            if b <= t or a >= t + dur:
                continue
            pts.append(max(t, a))
            pts.append(min(t + dur, b))
        pts = sorted(set(pts))
        mx = 0
        for p in pts:
            c = sum(1 for (a, b) in ev if a <= p < b)
            if c > mx:
                mx = c
        if mx < cap:
            return t
        # 推到使重叠减少的最早时刻
        cand = [b for (a, b) in ev if a < t + dur and b > t]
        if not cand:
            return t
        t = min(cand)
    return t

    drone_free = {g: [0.0] * inst.ndrone[g] for g in ("A", "B", "C")}
    bat_free = {g: [0.0] * inst.nbat[g] for g in ("A", "B", "C")}
    assign = {}
    deliver = {}
    for k in idx:
        s = sorties[k]
        g = s.g
        di = int(np.argmin(drone_free[g]))
        d_free = drone_free[g][di]
        bi = int(np.argmin(bat_free[g]))
        b_free = bat_free[g][bi]
        start = max(d_free, b_free)
        end = start + s.dur
        soc_end = 1.0 - s.E / inst.euse[g]
        r = float(D.charge_time(soc_end, inst.tfull[g]))
        drone_free[g][di] = end
        bat_free[g][bi] = end + r
        assign[k] = dict(drone=inst.fleet[g][di], battery="%s-B%d" % (g, bi + 1),
                         start=start, end=end, soc=soc_end, chg=r)
        for a in s.areas:
            for b in s.load[a]:
                deliver[b] = start + s.offs[a]
    makespan = max(v["end"] for v in assign.values()) if assign else 0.0
    return assign, makespan, deliver


def schedule_order(inst: Instance, sorties: List[Sortie], order: List[int], air_cap=None):
    """给定排程序列执行列表排程（与 schedule_greedy 同一规则）。"""
    drone_free = {g: [0.0] * inst.ndrone[g] for g in ("A", "B", "C")}
    bat_free = {g: [0.0] * inst.nbat[g] for g in ("A", "B", "C")}
    busy = []
    assign, deliver = {}, {}
    for k in order:
        s = sorties[k]
        g = s.g
        di = int(np.argmin(drone_free[g]))
        bi = int(np.argmin(bat_free[g]))
        start = max(drone_free[g][di], bat_free[g][bi])
        if air_cap is not None:
            start = _fit_start(start, s.dur, busy, air_cap)
        end = start + s.dur
        r = float(D.charge_time(1.0 - s.E / inst.euse[g], inst.tfull[g]))
        drone_free[g][di] = end
        bat_free[g][bi] = end + r
        busy.append((start, end))
        assign[k] = dict(drone=inst.fleet[g][di], battery="%s-B%d" % (g, bi + 1),
                         start=start, end=end, soc=1.0 - s.E / inst.euse[g], chg=r)
        for a in s.areas:
            for b in s.load[a]:
                deliver[b] = start + s.offs[a]
    mk = max((v["end"] for v in assign.values()), default=0.0)
    return assign, mk, deliver


def _viol(inst: Instance, deliver):
    hv = 0.0
    tard = 0.0
    for b, t in deliver.items():
        hd = inst.hard[b]
        if hd < BIG and t > hd + 1e-6:
            hv += t - hd
        d = t - inst.soft[b]
        if d > 0:
            tard += inst.wpri[b] * d
    return hv, tard


def schedule_ls(inst: Instance, sorties: List[Sortie], iters=4000, seed=0, air_cap=None):
    """对"架次执行顺序"做局部搜索（交换/插入），目标 = 硬违反 >> 加权延误 > 完工时间。"""
    K = len(sorties)
    if K == 0:
        return schedule_greedy(inst, sorties, air_cap=air_cap)
    rng = random.Random(seed)
    base = sorted(range(K), key=lambda k: (min(inst.hard[b] for a in sorties[k].areas for b in sorties[k].load[a]),
                                           min(inst.soft[b] for a in sorties[k].areas for b in sorties[k].load[a]),
                                           sorties[k].dur))
    best_order = list(base)
    _, mk, dv = schedule_order(inst, sorties, best_order, air_cap=air_cap)
    hv, tard = _viol(inst, dv)
    best = (1e6 * hv + tard + 1e-3 * mk, hv, tard, mk)

    def cost(order):
        _, mk2, dv2 = schedule_order(inst, sorties, order, air_cap=air_cap)
        hv2, tard2 = _viol(inst, dv2)
        return 1e6 * hv2 + tard2 + 1e-3 * mk2, hv2, tard2, mk2

    cur = list(best_order)
    curc = best
    for it in range(iters):
        cand = list(cur)
        if rng.random() < 0.6:
            i, j = rng.randrange(K), rng.randrange(K)
            cand[i], cand[j] = cand[j], cand[i]
        else:
            i = rng.randrange(K)
            j = rng.randrange(K)
            x = cand.pop(i)
            cand.insert(j, x)
        c = cost(cand)
        if c[0] < curc[0] or rng.random() < math.exp(-(c[0] - curc[0]) / max(1e-9, 0.02 * curc[0] + 1.0)):
            cur, curc = cand, c
            if c[0] < best[0]:
                best, best_order = c, list(cand)
    assign, mk, deliver = schedule_order(inst, sorties, best_order)
    return assign, mk, deliver


def _metrics(inst: Instance, sorties, assign, deliver, mk, air_cap=2):
    E = sum(s.E for s in sorties)
    tard = 0.0
    nlate = 0
    hv = 0.0
    for b, t in deliver.items():
        d = t - inst.soft[b]
        if d > 0:
            tard += inst.wpri[b] * d
            nlate += 1
        hd = inst.hard[b]
        if hd < BIG and t > hd + 1e-6:
            hv += t - hd
    ontime = sum(1 for b, t in deliver.items() if t <= inst.soft[b] + 1e-6)
    # 在空运输机并发（决定中继保障难度）
    ev = []
    for k, s in enumerate(sorties):
        ev.append((assign[k]["start"], 1))
        ev.append((assign[k]["end"], -1))
    ev.sort()
    cur = 0
    peak = 0
    excess = 0.0
    prev = 0.0
    for t, d in ev:
        if cur > air_cap:
            excess += (t - prev) * (cur - air_cap)
        cur += d
        peak = max(peak, cur)
        prev = t
    return dict(makespan=mk, energy=E, count=len(sorties), tardiness=tard, nlate=nlate,
                hard_violation=hv, ontime=ontime, nbox=len(deliver),
                ontime_rate=ontime / max(1, len(deliver)),
                avg_deliver=float(np.mean(list(deliver.values()))) if deliver else 0.0,
                max_deliver=max(deliver.values()) if deliver else 0.0,
                air_peak=peak, air_excess=excess)


def eval_solution(inst: Instance, sorties: List[Sortie], w, order_key="hs"):
    """返回 (标量目标, 指标字典, 排程)。w 可含 'comm'（影子缺口）/ 'cover'（单点可覆盖性）/
    'air'（在空并发超限时长）权重，供 Q3 联合优化使用。"""
    assign, mk, deliver = schedule_greedy(inst, sorties, order_key,
                                          air_cap=w.get("air_cap_hard"))
    met = _metrics(inst, sorties, assign, deliver, mk, air_cap=int(w.get("air_cap", 2)))
    wc, we, wt, wd = w["count"], w["energy"], w["makespan"], w["tardy"]
    obj = (wc * met["count"] / 20.0 + we * met["energy"] / 60.0 + wt * mk / 20000.0
           + wd * met["tardiness"] / 1e6 + 1e3 * met["hard_violation"] / 1000.0)
    wa = w.get("air", 0.0)
    if wa:
        cap = int(w.get("uncov_cap", 2))
        ex, peak, tot = _cover(inst).uncovered_concurrency(sorties, assign, cap=cap)
        met["uncov_excess"] = ex
        met["uncov_peak"] = peak
        met["uncov_total"] = tot
        obj += (wa * ex / 20000.0 + wa * 0.05 * max(0, peak - cap))
    wq = w.get("comm", 0.0)
    if wq:
        gap = _shadow(inst).solution_gap(sorties)
        met["gap"] = gap
        obj += wq * gap / 20000.0
    wc2 = w.get("cover", 0.0)
    if wc2:
        prof = _cover(inst).solution_profile(sorties)
        left = sum(p["best_left"] for p in prof)
        unc = sum(p["uncovered"] for p in prof)
        met["uncov_time"] = unc
        met["cover_left"] = left
        met["cover_rate"] = 1.0 - left / max(1.0, unc)
        obj += wc2 * left / 20000.0
    return obj, met, assign, deliver


_SHADOW = [None]
_COVER = [None]


def _shadow(inst):
    if _SHADOW[0] is None:
        import comm as _C
        _SHADOW[0] = _C.ShadowModel(inst)
    return _SHADOW[0]


def _cover(inst):
    if _COVER[0] is None:
        import cover_model as _CM
        _COVER[0] = _CM.CoverModel(inst)
    return _COVER[0]


# ===========================================================================
# 构造 + ALNS
# ===========================================================================
def type_candidates_for(inst: Instance, m, v):
    out = []
    for g in ("A", "B", "C"):
        dt = inst.types[g]
        if m <= dt.q_max + 1e-9 and v <= dt.v_cap + 1e-9:
            out.append(g)
    return out


def new_sortie_for_box(inst: Instance, b, prefer=None):
    best = None
    for g in (prefer or ("A", "B", "C")):
        if g is None:
            continue
        s = make_sortie(inst, g, {b.sid: [b.bid]})
        if s is None:
            continue
        if best is None or (s.dur, s.E) < (best.dur, best.E):
            best = s
    return best


def construct(inst: Instance, rng: random.Random, noise=0.0, w=None):
    """按（硬时限, 优先级）构造初始解。"""
    w = w or dict(count=1, energy=1, makespan=1, tardy=1)
    order = sorted(inst.boxes, key=lambda b: (inst.hard[b.bid],
                                              -b.priority, -b.mass))
    sol: List[Sortie] = []
    for b in order:
        best = None
        best_key = None
        for k, s in enumerate(sol):
            g = s.g
            dt = inst.types[g]
            m = s.mass(inst.bidx) + b.mass
            v = s.vol(inst.bidx) + b.vol
            if m > dt.q_max + 1e-9 or v > dt.v_cap + 1e-9:
                continue
            ab = {a: list(s.load[a]) for a in s.areas}
            ab.setdefault(b.sid, [])
            ab[b.sid] = ab[b.sid] + [b.bid]
            ok, r = sortie_feasible(inst, g, ab)
            if not ok:
                continue
            d_dur = r[1] - s.dur
            d_E = r[2] - s.E
            key = w["makespan"] * d_dur + w["energy"] * d_E * 100 + rng.random() * noise
            if best_key is None or key < best_key:
                best_key = key
                best = (k, ab, r)
        if best is not None:
            k, ab, r = best
            sol[k].areas, sol[k].dur, sol[k].E, sol[k].offs = r[0], r[1], r[2], r[3]
            sol[k].load = {a: ab[a] for a in r[0]}
        else:
            ns = new_sortie_for_box(inst, b)
            if ns is None:
                raise RuntimeError("无法为货箱 %s 构造架次（机型能力不足）" % b.bid)
            sol.append(ns)
    return sol


def destroy(inst: Instance, sol: List[Sortie], rng: random.Random, q: int):
    """返回 (保留的架次, 被移除的货箱编号集合)。"""
    sol = [Sortie(g=s.g, areas=list(s.areas), load={a: list(s.load[a]) for a in s.load},
                  dur=s.dur, E=s.E, offs=dict(s.offs)) for s in sol]
    removed = set()
    op = rng.random()
    if op < 0.35:                      # 随机移除货箱
        allb = [b for s in sol for a in s.areas for b in s.load[a]]
        rng.shuffle(allb)
        for bid in allb[:q]:
            removed.add(bid)
    elif op < 0.7:                     # 最差架次整体移除
        order = sorted(range(len(sol)), key=lambda k: -(sol[k].E + 0.001 * sol[k].dur))
        for k in order[:max(1, q // 4)]:
            for a in sol[k].areas:
                removed.update(sol[k].load[a])
    else:                              # 整区移除
        areas = sorted({s.areas[0] for s in sol})   # sorted 避免受 PYTHONHASHSEED 影响
        rng.shuffle(areas)
        for a in areas[:max(1, q // 5)]:
            for s in sol:
                if a in s.load:
                    removed.update(s.load[a])
    for s in sol:
        for a in list(s.load.keys()):
            s.load[a] = [b for b in s.load[a] if b not in removed]
    sol = [s for s in sol if refresh(inst, s)]
    return sol, removed


def repair(inst: Instance, sol: List[Sortie], removed, rng: random.Random, w, noise=0.0):
    order = sorted((inst.bidx[b] for b in removed),
                   key=lambda b: (inst.hard[b.bid], -b.priority, -b.mass))
    for b in order:
        best = None
        best_key = None
        for k, s in enumerate(sol):
            g = s.g
            dt = inst.types[g]
            m = s.mass(inst.bidx) + b.mass
            v = s.vol(inst.bidx) + b.vol
            if m > dt.q_max + 1e-9 or v > dt.v_cap + 1e-9:
                continue
            ab = {a: list(s.load[a]) for a in s.areas}
            ab.setdefault(b.sid, [])
            ab[b.sid] = ab[b.sid] + [b.bid]
            if len(ab) > 6:
                continue
            ok, r = sortie_feasible(inst, g, ab)
            if not ok:
                continue
            key = (w["makespan"] * (r[1] - s.dur) + w["energy"] * (r[2] - s.E) * 100
                   + rng.random() * noise)
            if best_key is None or key < best_key:
                best_key = key
                best = (k, ab, r)
        if best is not None:
            k, ab, r = best
            sol[k].areas, sol[k].dur, sol[k].E, sol[k].offs = r[0], r[1], r[2], r[3]
            sol[k].load = {a: ab[a] for a in r[0]}
        else:
            ns = new_sortie_for_box(inst, b)
            if ns is None:
                return None
            sol.append(ns)
    return sol


def compact(inst: Instance, sol: List[Sortie]):
    """尝试把两个架次合并为一个（跨服务区组批）。"""
    improved = True
    while improved:
        improved = False
        n = len(sol)
        for i in range(n):
            for j in range(i + 1, n):
                for g in ("A", "B", "C"):
                    ab = {}
                    for a in sol[i].areas:
                        ab.setdefault(a, []).extend(sol[i].load[a])
                    for a in sol[j].areas:
                        ab.setdefault(a, []).extend(sol[j].load[a])
                    if len(ab) > 6:
                        continue
                    ok, r = sortie_feasible(inst, g, ab)
                    if not ok:
                        continue
                    ns = Sortie(g=g, areas=r[0], load={a: ab[a] for a in r[0]},
                                dur=r[1], E=r[2], offs=r[3])
                    sol2 = [sol[k] for k in range(n) if k not in (i, j)] + [ns]
                    if len(sol2) < len(sol):
                        sol = sol2
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return sol


def alns(inst: Instance, w, seed=0, iters=4000, tlimit=120.0, init=None):
    rng = random.Random(seed)
    t0 = time.time()
    cur = init or compact(inst, construct(inst, rng, noise=1.0, w=w))
    cur_obj, cur_met, _, _ = eval_solution(inst, cur, w)
    best = [Sortie(**vars(s)) for s in cur]
    best_obj, best_met = cur_obj, cur_met
    T0, T1 = 0.20, 0.004
    it = 0
    while it < iters and time.time() - t0 < tlimit:
        it += 1
        frac = min(1.0, it / iters)
        T = T0 * (T1 / T0) ** frac
        q = rng.randint(2, 8)
        part, removed = destroy(inst, cur, rng, q)
        if not removed:
            continue
        cand = repair(inst, part, removed, rng, w, noise=0.05 * (1 - frac))
        if cand is None:
            continue
        if rng.random() < 0.3:
            cand = compact(inst, cand)
        obj, met, _, _ = eval_solution(inst, cand, w)
        if obj < cur_obj or rng.random() < math.exp(-(obj - cur_obj) / max(1e-9, T)):
            cur, cur_obj, cur_met = cand, obj, met
            if obj < best_obj:
                best = [Sortie(**vars(s)) for s in cand]
                best_obj, best_met = obj, met
    return best, best_obj, best_met, it


# ===========================================================================
# CP-SAT 精确排程打磨（固定架次集合 → 最优起止时刻 / 无人机-电池可行性）
# ===========================================================================
def schedule_cpsat(inst: Instance, sorties: List[Sortie], w_mk=1.0, w_tardy=1e-4, tlimit=60.0,
                   air_cap=None):
    from ortools.sat.python import cp_model
    K = len(sorties)
    m = cp_model.CpModel()
    H = int(HORIZON)
    start, end, dur, chg = {}, {}, {}, {}
    for k, s in enumerate(sorties):
        d = int(math.ceil(s.dur))
        dur[k] = m.NewIntVar(0, H, "d%d" % k)
        m.Add(dur[k] == d)
        start[k] = m.NewIntVar(0, H, "s%d" % k)
        end[k] = m.NewIntVar(0, H, "e%d" % k)
        m.Add(end[k] == start[k] + d)
    # 在空架次数上限（Q3：2 架中继的保障能力）
    if air_cap:
        iv = [m.NewIntervalVar(start[k], dur[k], end[k], "air%d" % k) for k in range(K)]
        m.AddCumulative(iv, [1] * K, air_cap)
    # 无人机容量（按机型）
    for g in ("A", "B", "C"):
        ks = [k for k, s in enumerate(sorties) if s.g == g]
        if not ks:
            continue
        iv = [m.NewIntervalVar(start[k], dur[k], end[k], "iv%d" % k) for k in ks]
        m.AddCumulative(iv, [1] * len(iv), inst.ndrone[g])
    # 电池容量：占用 + 充电串行
    for g in ("A", "B", "C"):
        ks = [k for k, s in enumerate(sorties) if s.g == g]
        if not ks:
            continue
        iv = [m.NewIntervalVar(start[k], dur[k], end[k], "ivb%d" % k) for k in ks]
        ch = []
        for k in ks:
            r = int(math.ceil(float(D.charge_time(1.0 - sorties[k].E / inst.euse[g],
                                                  inst.tfull[g]))))
            r = max(r, 1)
            c_end = m.NewIntVar(0, H + 3600, "ce%d" % k)
            ch.append(m.NewIntervalVar(end[k], r, c_end, "ci%d" % k))
        m.AddCumulative(iv + ch, [1] * (len(iv) + len(ch)), inst.nbat[g])
    # 硬时限
    for k, s in enumerate(sorties):
        for a in s.areas:
            for b in s.load[a]:
                hd = inst.hard[b]
                if hd < BIG:
                    m.Add(start[k] <= int(math.floor(hd - s.offs[a])))
    # 软延误
    tard = {}
    for k, s in enumerate(sorties):
        for a in s.areas:
            for b in s.load[a]:
                ex = int(math.floor(inst.soft[b] - s.offs[a]))
                t = m.NewIntVar(0, H, "t_%s" % b)
                m.Add(t >= start[k] - ex)
                m.Add(t >= 0)
                tard[b] = t
    mk = m.NewIntVar(0, H, "mk")
    m.AddMaxEquality(mk, [end[k] for k in range(K)])
    m.Minimize(int(w_mk * 1000) * mk
               + sum(int(w_tardy * 1000 * inst.wpri[b]) * tard[b] for b in tard))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tlimit
    solver.parameters.num_search_workers = 8
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    assign = {}
    deliver = {}
    for k, s in enumerate(sorties):
        stt = solver.Value(start[k])
        en = solver.Value(end[k])
        assign[k] = dict(start=float(stt), end=float(en),
                         soc=1.0 - s.E / inst.euse[s.g],
                         chg=float(D.charge_time(1.0 - s.E / inst.euse[s.g], inst.tfull[s.g])))
        for a in s.areas:
            for b in s.load[a]:
                deliver[b] = stt + s.offs[a]
    return dict(assign=assign, deliver=deliver,
                makespan=float(solver.Value(mk)),
                tard=float(sum(solver.Value(tard[b]) * inst.wpri[b] for b in tard)),
                status=solver.StatusName(st))


# ===========================================================================
# 多目标 Pareto
# ===========================================================================
WEIGHTS = [
    dict(name="P1-架次优先", count=4.0, energy=1.0, makespan=1.0, tardy=1.0),
    dict(name="P2-及时优先", count=0.5, energy=1.0, makespan=0.5, tardy=6.0),
    dict(name="P3-能耗优先", count=1.0, energy=6.0, makespan=1.0, tardy=1.0),
    dict(name="P4-完工优先", count=0.5, energy=0.5, makespan=6.0, tardy=1.0),
    dict(name="P5-均衡", count=1.5, energy=2.0, makespan=2.0, tardy=2.0),
]


def polish(inst: Instance, sol: List[Sortie], cpsat_limit=40.0, ls_iters=4000, air_cap=None):
    """终局打磨：顺序局部搜索 + CP-SAT 精确排程，返回三者中按 (硬违反, 加权延误, 完工) 最优者。"""
    cands = []
    a0, mk0, d0 = schedule_greedy(inst, sol, "hs", air_cap=air_cap)
    cands.append(("greedy", a0, mk0, d0))
    a1, mk1, d1 = schedule_ls(inst, sol, iters=ls_iters, air_cap=air_cap)
    cands.append(("ls", a1, mk1, d1))
    pol = schedule_cpsat(inst, sol, tlimit=cpsat_limit, air_cap=air_cap)
    if pol:
        cands.append(("cpsat", pol["assign"], pol["makespan"], pol["deliver"]))
    best = None
    for tag, a, mk, dv in cands:
        met = _metrics(inst, sol, a, dv, mk, air_cap=(air_cap if air_cap else 2))
        key = (round(met["hard_violation"], 3), met["tardiness"], mk, met["energy"])
        if best is None or key < best[0]:
            best = (key, tag, a, mk, dv, met)
    return dict(tag=best[1], assign=best[2], makespan=best[3], deliver=best[4], met=best[5],
                cpsat=pol)


def run_all(seed=0, iters=4000, tlimit=90.0, cpsat_limit=40.0, restarts=2, verbose=True):
    inst = Instance()
    out = {}
    for w in WEIGHTS:
        best = None
        for r in range(restarts):
            sol, obj, met, it = alns(inst, w, seed=seed + 17 * r, iters=iters, tlimit=tlimit)
            if best is None or obj < best[1]:
                best = (sol, obj, met, it)
        sol, obj, met, it = best
        pol = polish(inst, sol, cpsat_limit=cpsat_limit)
        rec = dict(pol["met"])
        rec["obj"] = obj
        rec["iters"] = it
        rec["polish"] = pol["tag"]
        out[w["name"]] = dict(sol=sol, met=pol["met"], pol=pol, w=w)
        if verbose:
            print("%-14s 架次=%2d 能耗=%7.2f kWh 完工=%7.0f s 加权延误=%9.0f 及时率=%.3f 硬违反=%.0f [%s]"
                  % (w["name"], rec["count"], rec["energy"], rec["makespan"], rec["tardiness"],
                     rec["ontime_rate"], rec["hard_violation"], pol["tag"]))
    return inst, out


def export(inst: Instance, name: str, sol: List[Sortie], pol, path=None):
    """按提交模板输出 Q2_运输架次 / Q2_逐箱交付 / Q2_资源使用。"""
    assign, mk, deliver_g = schedule_greedy(inst, sol)
    if pol:
        assign = pol["assign"]
        deliver_g = pol["deliver"]
    order = sorted(range(len(sol)), key=lambda k: (assign[k]["start"], k))
    code = {k: "Q2-%s-%02d" % (name, i + 1) for i, k in enumerate(order)}
    rows = []
    for k in order:
        s = sol[k]
        a = assign[k]
        rows.append(dict(架次编号=code[k], 无人机编号=a.get("drone", ""), 机型编号=s.g,
                         电池编号=a.get("battery", ""), 开始时刻_s=round(a["start"], 1),
                         访问服务区顺序="->".join(["O01"] + s.areas + ["O01"]),
                         返回O01时刻_s=round(a["end"], 1), 架次能耗_kWh=round(s.E, 4),
                         载质量_kg=round(s.mass(inst.bidx), 3), 体积_m3=round(s.vol(inst.bidx), 4),
                         返航SOC_pct=round(100 * (1 - s.E / inst.euse[s.g]), 2),
                         充电时长_s=round(a.get("chg", 0.0), 1),
                         箱数=sum(len(s.load[a2]) for a2 in s.areas)))
    df1 = pd.DataFrame(rows)
    box2sortie = {}
    for k in order:
        for a2 in sol[k].areas:
            for b in sol[k].load[a2]:
                box2sortie[b] = code[k]
    rows2 = []
    for b in sorted(deliver_g):
        t = deliver_g[b]
        rows2.append(dict(货箱编号=b, 架次编号=box2sortie.get(b, ""), 服务区编号=inst.bidx[b].sid,
                          交付完成时刻_s=round(t, 1),
                          期望送达时间_s=(inst.soft[b] if inst.soft[b] < BIG else ""),
                          硬时限_s=(inst.hard[b] if inst.hard[b] < BIG else ""),
                          是否及时=("是" if t <= inst.soft[b] + 1e-6 else "否")))
    df2 = pd.DataFrame(rows2)
    df_assign = pd.DataFrame([dict(架次编号=r["架次编号"], 无人机=r["无人机编号"], 电池=r["电池编号"],
                                   机型=r["机型编号"], 服务区=";".join(sol[order[i]].areas),
                                   开始=r["开始时刻_s"], 结束=r["返回O01时刻_s"],
                                   能耗_kWh=r["架次能耗_kWh"], 充电_s=r["充电时长_s"])
                              for i, r in enumerate(rows)])
    if path:
        with pd.ExcelWriter(path) as w:
            df1.to_excel(w, sheet_name="Q2_运输架次", index=False)
            df2.to_excel(w, sheet_name="Q2_逐箱交付", index=False)
            df_assign.to_excel(w, sheet_name="Q2_资源使用", index=False)
    return df1, df2, df_assign


def pick_pareto(out):
    """从多个权重解中提取 (及时性, 完工时间, 能耗, 架次数) 的非支配解集。"""
    pts = []
    for name, rec in out.items():
        met = rec["met"]
        pts.append(dict(name=name, count=met["count"], energy=met["energy"],
                        makespan=met["makespan"], tard=met["tardiness"],
                        hard=met["hard_violation"]))
    front = []
    for p in pts:
        if p["hard"] > 1e-6:
            continue
        if any((q["count"] <= p["count"] and q["energy"] <= p["energy"] + 1e-6
                and q["makespan"] <= p["makespan"] + 1e-6 and q["tard"] <= p["tard"] + 1e-6)
               and (q["count"], q["energy"], q["makespan"], q["tard"]) !=
               (p["count"], p["energy"], p["makespan"], p["tard"]) for q in pts
               if q["hard"] <= 1e-6):
            continue
        front.append(p)
    return front


if __name__ == "__main__":
    t0 = time.time()
    inst, out = run_all(iters=6000, tlimit=50.0, cpsat_limit=35.0, restarts=2)
    print("耗时 %.1f s" % (time.time() - t0))
    feas = [(k, v) for k, v in out.items() if v["met"]["hard_violation"] <= 1e-6]
    pool = feas or list(out.items())
    best = min(pool, key=lambda kv: (kv[1]["pol"]["makespan"], kv[1]["met"]["tardiness"]))
    export(inst, "P1", best[1]["sol"], best[1]["pol"], path=os.path.join(OUT, "Q2_结果.xlsx"))
    summary = {k: dict(v["met"], polish=v["pol"]["tag"]) for k, v in out.items()}
    json.dump(dict(summary=summary, front=pick_pareto(out)),
              open(os.path.join(OUT, "Q2_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n=== Pareto 前沿（硬约束可行解） ===")
    for p in pick_pareto(out):
        print("  %-14s 架次=%2d 能耗=%7.2f 完工=%7.0f 加权延误=%9.0f"
              % (p["name"], p["count"], p["energy"], p["makespan"], p["tard"]))
    print("\n输出：%s" % os.path.join(OUT, "Q2_结果.xlsx"))
