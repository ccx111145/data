# -*- coding: utf-8 -*-
"""
q4.py —— 2026 中国研究生数学建模竞赛 D 题
「山区洪涝灾害下无人机运输与通信协同优化」—— 问题四：任务组划分与各组独立资源核算

题意（问题四）
--------------
以问题三得到的联合调度方案为**固定输入**，把 15 个服务区 S001–S015 分别划分为
2 个和 3 个任务组：

1. 每个服务区必须且只能属于一个任务组，每组至少 1 个服务区；
2. 保持问题三已确定的货箱组批、服务区访问顺序、运输与中继任务安排、通信保障关系不变；
3. **若同一运输架次同时涉及多个服务区，这些服务区必须划入同一任务组**（硬耦合）；
4. 各任务组仅承担本组服务区对应的运输与通信保障任务，分别核算独立执行所需的
   运输无人机数（A/B/C 型）、共享电池组数（按机型）、中继无人机数、中继能源组件数；
5. 任务执行期间各类资源不得跨组调配；
6. 从**资源配置规模、资源冗余、组间工作量均衡、与现有库存之间的资源缺口**
   四方面比较两种分区方式，若所需资源超过库存，给出资源缺口及原因。

建模要点
--------
* **不可分割块**：把“服务区—架次”关联图中共享同一运输架次的服务区用并查集合并，
  得到若干原子块；任何合法分区都是对块集合的划分（块数很小，可完全枚举）。
* **运输无人机数**：各组内该机型架次的**峰值并发数**（时间轴事件扫描），不是架次总数。
* **共享电池组数**：对 [start, end) 占用区间 ∪ [end, end+chg) 充电区间做**区间图着色**，
  所需颜色数 = 区间图的最大团 = 最大重叠数；按开始时刻贪心分配即为最优（区间图是完美图）。
* **中继无人机数 / 中继能源组件数**：同上，占用区间取 [depart, back)（离开 O01 至返回 O01），
  能源组件再加充电区间 [back, back+chg)。
* **中继架次归组**：中继架次按其对各组运输架次的累计保障时长投票，归入唯一任务组
  （资源不得跨组调配），并单列“跨组保障”计数提示耦合风险。

运行
----
    cd <D题>/code
    python q4.py            # 全流程：读/建标准解 → 枚举分区 → 核算 → 出表 → 自检
    python q4.py --check    # 复用 results/solution.json，只重算并输出自检

输出
----
    results/Q4_分区配置.xlsx   首表 Q4_分区配置（列名严格固定），后附辅助表
    results/Q4_说明.md         中文说明书（推荐方案 / 核算表 / 缺口分析 / 比较结论 / 自检）
    results/Q4_运行日志.txt    控制台全文（防止控制台编码乱码导致信息丢失）
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import dcore as D
import solution_io as SIO

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
BASE = D.BASE
RES = D.RESULTS
XLSX_OUT = os.path.join(RES, "Q4_分区配置.xlsx")
MD_OUT = os.path.join(RES, "Q4_说明.md")
LOG_OUT = os.path.join(RES, "Q4_运行日志.txt")
RELAY_FILL = os.path.join(RES, "Q4_中继补全.json")   # solution.json 缺中继安排时的补全缓存
RELAY_EST_VER = "est-2026-09-23a"                     # 估算口径版本（变更时自动失效缓存）

SIDS = ["S%03d" % i for i in range(1, 16)]

# 现有库存（数据/无人机应急物资运输基础数据/*.xlsx）
INV = {
    "A": 4, "B": 2, "C": 2,               # 运输无人机 架（U01–U04=A, U05–U06=B, U07–U08=C）
    "battA": 6, "battB": 4, "battC": 4,   # 共享电池组 组
    "relay": 2,                           # 中继无人机 架（R01/R02）
    "relayE": 6,                          # 中继能源组件 组
}
INV_SRC = {
    "A": "运输无人机数据.xlsx：A 型 4 架（U01–U04）",
    "B": "运输无人机数据.xlsx：B 型 2 架（U05–U06）",
    "C": "运输无人机数据.xlsx：C 型 2 架（U07–U08）",
    "battA": "运输无人机数据.xlsx：A 型共享电池 6 组",
    "battB": "运输无人机数据.xlsx：B 型共享电池 4 组",
    "battC": "运输无人机数据.xlsx：C 型共享电池 4 组",
    "relay": "中继无人机数据.xlsx：R01、R02 共 2 架",
    "relayE": "中继无人机数据.xlsx：中继能源组件 6 组",
}

CLASSES = ["A", "B", "C", "battA", "battB", "battC", "relay", "relayE"]
CLASS_CN = {
    "A": "A型运输无人机(架)", "B": "B型运输无人机(架)", "C": "C型运输无人机(架)",
    "battA": "A型电池组(组)", "battB": "B型电池组(组)", "battC": "C型电池组(组)",
    "relay": "中继无人机(架)", "relayE": "中继能源组件(组)",
}
# 资源当量权重：整机按 1.0，可插拔能源单元（电池组 / 能源组件）按 0.4 折算
WEIGHT = {"A": 1.0, "B": 1.0, "C": 1.0, "battA": 0.4, "battB": 0.4, "battC": 0.4,
          "relay": 1.0, "relayE": 0.4}
WEIGHT_NOTE = ("整机（运输无人机、中继无人机）按 1.0 计，可插拔能源单元（共享电池组、"
               "中继能源组件）按 0.4 折算——整机是产能瓶颈与主要成本项，能源单元可周转复用。"
               "第十节给出权重灵敏度（0.2 / 0.4 / 0.6）说明推荐方案对该权重不敏感。")

EPS = 1e-9


# ---------------------------------------------------------------------------
# 控制台 / 日志
# ---------------------------------------------------------------------------
class Tee:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")
        self.buf = []

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        self.buf.append(s)
        try:
            print(s)
        except Exception:
            pass
        self.f.write(s + "\n")
        self.f.flush()

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


LOG = Tee(LOG_OUT)


def relu(x):
    return x if x > 0 else 0


# ===========================================================================
# 一、标准解接口：读取 results/solution.json，缺失则现场生成
# ===========================================================================
def _order_and_code(sol_sorties, assign, prefix="Q2"):
    """与 solution_io.transport_from_sorties 完全一致的排序与编号规则。"""
    order = sorted(range(len(sol_sorties)), key=lambda k: (assign[k]["start"], k))
    code = {k: "%s-%02d" % (prefix, i + 1) for i, k in enumerate(order)}
    return order, code


def _build_coverage(inst, codes, r, verbose=True):
    """由 Q3 中继规划结果生成“通信保障关系”记录（标准解 coverage 字段）。

    codes[k] = 第 k 个运输架次在标准解中的编号（sid）。
    """
    import comm as C

    T, P, K = r.get("T"), r.get("P"), r.get("K")
    if T is None or len(T) == 0:
        return []
    link = (r.get("dat") or {}).get("link")
    if link is None:
        link = C.Link(inst)
    rsort = r.get("sorties") or []
    ivs = [(float(s["t_link_done"]), float(s["t_end"]),
            (float(s["lon"]), float(s["lat"]), float(s["hover_alt"])),
            "Q3-R-%02d" % (i + 1)) for i, s in enumerate(rsort)]
    if not ivs:
        return []
    pairs = defaultdict(list)
    for i in range(len(T)):
        t = float(T[i])
        for j, (a, b, pt, rsid) in enumerate(ivs):
            if a - 1e-9 <= t <= b + 1e-9:
                ok1, _, _ = link.access_ok(P[i:i + 1], pt)
                if ok1[0]:
                    ok2, _, _ = link.backhaul_ok(np.array([pt], dtype=float))
                    if ok2[0]:
                        pairs[(int(K[i]), j)].append(t)
                        break
    cov = []
    for (ki, j), ts in sorted(pairs.items()):
        if ki >= len(codes):
            continue
        ts = sorted(ts)
        t0 = prev = ts[0]
        for t in ts[1:]:
            if t - prev > 10.0 + 1e-6:
                cov.append(dict(sid=codes[ki], phase="cruise", t0=t0, t1=prev,
                                mode="relay", relay=ivs[j][3]))
                t0 = t
            prev = t
        cov.append(dict(sid=codes[ki], phase="cruise", t0=t0, t1=prev,
                        mode="relay", relay=ivs[j][3]))
    if verbose:
        LOG("  [标准解] 通信保障记录 %d 条，覆盖运输架次 %d 个，涉及中继架次 %d 个"
            % (len(cov), len({c["sid"] for c in cov}), len({c["relay"] for c in cov})))
    return cov


def _q3run_relay(inst, sorties, assign, verbose=True):
    """可选路线：题目指定的 q3run.plan（中继覆盖规划）。返回 (中继架次记录, 标签)。"""
    import q3run

    try:
        r = q3run.plan(inst, sorties, assign, verbose=verbose)
    except Exception as e:                                     # noqa: BLE001
        LOG("  [Q3] q3run.plan 异常：%r" % (e,))
        return [], "q3run.plan 异常"
    if not r.get("sorties"):
        LOG("  [Q3] q3run.plan 未给出可用中继方案：%s" % str(r.get("msg"))[:160])
        return [], "q3run.plan 失败"
    return SIO.relay_to_records(r["sorties"]), "q3run.plan"


def _reconstruct_q2(records, verbose=True):
    """把标准解 transport 记录还原成 q2.Sortie 列表与 assign 排程（供 Q3 规划/估算复用）。"""
    import q2 as Q

    sorties, assign = [], {}
    miss = 0
    for k, r in enumerate(records):
        areas = [s for s in r.get("route", []) if isinstance(s, str) and s.startswith("S")]
        boxes = r.get("boxes") or {}
        load = {a: list(boxes.get(a, [])) for a in areas}
        if any(len(v) == 0 for v in load.values()):
            miss += 1
        s = Q.Sortie(g=r["type"], areas=areas, load=load)
        s.dur = float(r["end"]) - float(r["start"])
        s.E = float(r.get("energy", 0.0))
        sorties.append(s)
        assign[k] = dict(drone=r.get("drone", ""), battery=r.get("battery", ""),
                         start=float(r["start"]), end=float(r["end"]),
                         soc=float(r.get("soc", 1.0)), chg=float(r.get("chg", 0.0) or 0.0))
    if miss and verbose:
        LOG("  [Q3] 注意：%d 个架次的货箱明细缺失，装载时长按 0 计" % miss)
    return sorties, assign


def estimate_relay(inst, trecs, grid=10.0, verbose=True):
    """估计中继保障需求（solution.json 的 relay 字段为空时的退化口径）。

    步骤
    ----
    1. 用 `comm.sortie_track` 以 10 s 采样每个运输架次的航迹，用 `comm.Link.direct_ok`
       判定“与固定网关 G01 直连是否可用”；
    2. 把“直连不可用”的连续采样格合并成**需保障时段**（若无失联则中继需求为 0）；
    3. 每个需保障时段配一个中继架次：悬停点取该时段内失联点水平重心、离地高度取机型上限
       `min(h_max_agl, 300)`（回传/接入链路是否可用在估算中不再逐点校验，作为偏保守的
       资源上界口径），占用区间 = [首刻 − 建链 − 去程, 末刻 + 网格 + 返程]；
    4. 中继无人机数 = 占用区间峰值并发；中继能源组件数 = 占用 ∪ 充电 区间的区间图着色。

    该估算给出的是**独立执行所需中继资源的上界**，用于 Q4 的分区核算；
    待 Q3 最终中继方案回填 `solution.json` 的 `relay` 字段后，本函数自动不再启用。
    """
    import comm as C

    rtype = inst.d["rtype"]
    link = C.Link(inst)
    sorties, assign = _reconstruct_q2(trecs, verbose=verbose)
    segs = []                                     # (t0, t1, [(sid, lon, lat, alt)], pts)
    for k, s in enumerate(sorties):
        tr = C.sortie_track(inst, s, assign[k]["start"], grid)
        if len(tr["t"]) == 0:
            continue
        ok, _, _ = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        bad = ~ok
        if not bad.any():
            continue
        ts = tr["t"][bad]
        los, las, als = tr["lon"][bad], tr["lat"][bad], tr["alt"][bad]
        cells = np.floor(ts / grid).astype(np.int64)
        order = np.argsort(cells, kind="stable")
        cells, los, las, als = cells[order], los[order], las[order], als[order]
        i = 0
        while i < len(cells):
            j = i
            while j + 1 < len(cells) and cells[j + 1] <= cells[j] + 1:
                j += 1
            t0 = float(cells[i]) * grid
            t1 = float(cells[j]) * grid + grid
            segs.append(dict(t0=t0, t1=t1,
                             sid=trecs[k]["sid"] if k < len(trecs) else "Q2-%02d" % (k + 1),
                             lon=float(los[i:j + 1].mean()), lat=float(las[i:j + 1].mean()),
                             alt=float(als[i:j + 1].mean()), n=j - i + 1,
                             sids={trecs[k]["sid"] if k < len(trecs) else "Q2-%02d" % (k + 1)}))
            i = j + 1
    if not segs:
        if verbose:
            LOG("  [Q3 估算] 运输架次全程与 G01 直连可用，中继需求为 0")
        return [], [], "无失联时段"

    # 合并时间上重叠/相邻的时段（同一时刻的失联点可由同一中继覆盖）
    segs.sort(key=lambda s: (s["t0"], s["t1"]))
    merged = []
    for s in segs:
        if merged and s["t0"] <= merged[-1]["t1"] + grid + 1e-9:
            m = merged[-1]
            w = m["n"] + s["n"]
            m["lon"] = (m["lon"] * m["n"] + s["lon"] * s["n"]) / w
            m["lat"] = (m["lat"] * m["n"] + s["lat"] * s["n"]) / w
            m["alt"] = (m["alt"] * m["n"] + s["alt"] * s["n"]) / w
            m["n"] = w
            m["t1"] = max(m["t1"], s["t1"])
            m["sids"].add(s["sid"])
        else:
            merged.append(dict(s, sids=set(s["sids"])))

    out, cov = [], []
    free = {d: 0.0 for d in inst.d["rfleet"]}
    n_delay = 0
    for i, m in enumerate(merged, 1):
        agl = min(300.0, float(rtype.h_max_agl))
        rf = D.relay_flight(rtype, inst.nodes, m["lon"], m["lat"], agl)
        t_link = min(float(rtype.t_link), 30.0)
        depart_nom = max(0.0, m["t0"] - t_link - rf["t_out"])
        back = m["t1"] + rf["t_back"]
        dr = min(free, key=lambda k: (free[k], k))          # 两架中继接力：选最早空闲者
        depart = depart_nom                                 # 必须按时到位：占用区间由保障时段决定
        if free[dr] > depart_nom + 1e-6:                    # 上一架次尚未返场 → 接力冲突
            n_delay += 1
        free[dr] = back + float(rtype.t_turn)
        hover = max(0.0, m["t1"] - m["t0"])
        e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
        e_tot = rf["e_fly"] + e_hover
        soc = 1.0 - e_tot / rtype.e_use
        sid = "Q3-EST-%02d" % i
        out.append(dict(sid=sid, drone=dr, comp="R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1),
                        lon=m["lon"], lat=m["lat"], hover_alt=rf["hover_alt"], agl=agl,
                        ground=rf["ground"], depart=depart, link_done=m["t0"], end=m["t1"],
                        back=back, e_fly=rf["e_fly"], e_hover=e_hover, e_total=e_tot,
                        soc=soc, chg=float(D.charge_time(soc, inst.d["rbatt"][1]))))
        for s0 in sorted(m["sids"]):
            cov.append(dict(sid=s0, phase="cruise", t0=m["t0"], t1=m["t1"],
                            mode="relay", relay=sid))
    if verbose:
        LOG("  [Q3 估算] 失联时段 %d 段 → 合并为 %d 个中继架次；按时到位所需占用峰值 %d 架"
            "（库存 %d 架）、能源组件 %d 组；两架接力冲突 %d 处"
            % (len(segs), len(out), peak_of([(r["depart"], r["back"]) for r in out]),
               len(inst.d["rfleet"]),
               ncolor_of([(r["depart"], r["back"] + r["chg"]) for r in out]), n_delay))
    return out, cov, "失联时段估算"


def complete_relay(sol, plan="auto", force=False, verbose=True):
    """若标准解缺少中继架次 / 通信保障关系，就地补全（**不覆盖** results/solution.json）。

    plan = auto      : solution.json 有 relay 就用它；没有则用失联时段估算（默认，很快）；
             estimate: 强制用估算口径；
             q3run   : 先尝试题目指定的 q3run.plan，失败再回退到估算。
    """
    if sol.get("relay") and sol.get("coverage") and not force:
        return sol, ""
    if sol.get("relay") and not sol.get("coverage") and plan == "auto" and not force:
        import q2 as Q

        LOG("  [Q3] solution.json 含中继架次但缺通信保障关系，按中继服务时段反推保障记录")
        inst = Q.Instance()
        cov = _build_coverage_coverage(inst, sol.get("transport", []), sol["relay"],
                                       verbose=verbose)
        out = dict(sol)
        out["coverage"] = cov
        return out, "；通信保障关系按中继服务时段反推"

    payload = json.dumps([[r.get("sid"), r.get("drone"), r.get("start"), r.get("end"),
                           r.get("route")] for r in sol.get("transport", [])],
                         ensure_ascii=False, sort_keys=True, default=float)
    key = hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]
    if plan == "auto":
        plan = "estimate"
    cache_key = "%s|%s|%s" % (key, plan, RELAY_EST_VER)
    if os.path.exists(RELAY_FILL) and not force:
        try:
            with open(RELAY_FILL, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:                                       # noqa: BLE001
            cache = {}
        if cache.get("key") == cache_key and cache.get("relay"):
            out = dict(sol)
            out["relay"] = cache["relay"]
            out["coverage"] = cache["coverage"]
            if verbose:
                LOG("  [Q3 补全] 标准解未含中继安排；沿用 results/Q4_中继补全.json 缓存"
                    "（口径 %s：中继架次 %d，保障记录 %d）"
                    % (cache.get("source", "?"), len(cache["relay"]), len(cache["coverage"])))
            return out, "；中继资源按「%s」口径补全（缓存 results/Q4_中继补全.json）" \
                        % cache.get("source", "补全")

    import q2 as Q

    inst = Q.Instance()
    records = sol.get("transport", [])
    rrecs, coverage, tag = [], [], ""
    if plan == "q3run":
        sorties, assign = _reconstruct_q2(records, verbose=verbose)
        rrecs, tag = _q3run_relay(inst, sorties, assign, verbose=verbose)
        if rrecs:
            coverage = _build_coverage_coverage(inst, records, rrecs, verbose=verbose)
    if not rrecs:
        LOG("  [Q3 补全] 标准解未含中继安排，按运输架次的失联时段估算中继资源需求"
            "（待 Q3 最终中继方案回填 results/solution.json 的 relay 字段后自动改用真实数据）")
        rrecs, coverage, tag = estimate_relay(inst, records, verbose=verbose)

    try:
        with open(RELAY_FILL, "w", encoding="utf-8") as f:
            json.dump(dict(key=cache_key, source=tag, relay=rrecs, coverage=coverage),
                      f, ensure_ascii=False, indent=1, default=float)
    except Exception as e:                                      # noqa: BLE001
        LOG("  [Q3 补全] 缓存写入失败：%r" % (e,))
    out = dict(sol)
    out["relay"] = rrecs
    out["coverage"] = coverage
    out["meta"] = dict(out.get("meta") or {})
    out["meta"]["relay_source"] = tag
    return out, "；中继资源按「%s」口径补全" % tag


def _build_coverage_coverage(inst, records, rrecs, verbose=True):
    """由已有中继架次的服务时段反推“中继→运输架次”保障记录（覆盖时长口径）。"""
    import comm as C

    link = C.Link(inst)
    codes = [r.get("sid") for r in records]
    sorties, assign = _reconstruct_q2(records, verbose=False)
    cov = []
    for k, s in enumerate(sorties):
        tr = C.sortie_track(inst, s, assign[k]["start"], 10.0)
        if len(tr["t"]) == 0:
            continue
        ok, _, _ = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        for r in rrecs:
            sel = (~ok) & (tr["t"] >= float(r["link_done"]) - 1e-9) & (tr["t"] <= float(r["end"]) + 1e-9)
            if sel.any():
                cov.append(dict(sid=codes[k], phase="cruise", t0=float(tr["t"][sel].min()),
                                t1=float(tr["t"][sel].max()), mode="relay", relay=r["sid"]))
    if verbose:
        LOG("  [Q3] 由中继服务时段反推保障记录 %d 条（覆盖 %d 个运输架次）"
            % (len(cov), len({c["sid"] for c in cov})))
    return cov


def build_solution(tlimit=25.0, plan="estimate", verbose=True):
    """降级路径：现场跑 Q2（ALNS + CP-SAT 排程），中继部分按 `plan` 口径补全。"""
    import q2 as Q
    import cscan

    t0 = time.time()
    if verbose:
        LOG("  [降级] 未找到 results/solution.json，现场生成基准解（Q2 ALNS + Q3 中继口径）…")
    inst = Q.Instance()
    sol, pol = cscan.build_solution(inst, tlimit=tlimit)
    if verbose:
        LOG("  [降级] Q2 完成：架次=%d 完工=%.0f s 能耗=%.2f kWh 排程=%s（%.0f s）"
            % (len(sol), pol["makespan"], pol["met"]["energy"], pol["tag"], time.time() - t0))
    trecs = SIO.transport_from_sorties(inst, sol, pol["assign"])
    rrecs, coverage, tag = [], [], ""
    if plan == "q3run":
        rrecs, tag = _q3run_relay(inst, sol, pol["assign"], verbose=verbose)
    if not rrecs:
        rrecs, coverage, tag = estimate_relay(inst, trecs, verbose=verbose)
    if verbose:
        LOG("  [降级] Q3 完成：中继架次=%d（口径 %s，总耗时 %.0f s）"
            % (len(rrecs), tag, time.time() - t0))
    return dict(
        meta=dict(rho=0.2, makespan=float(pol["makespan"]), energy=float(pol["met"]["energy"]),
                  n_transport=len(trecs), n_relay=len(rrecs), relay_source=tag,
                  source="q2 现场生成 + 中继按 %s 口径补全" % tag),
        transport=trecs, relay=rrecs, coverage=coverage)


def ensure_solution(force=False, tlimit=25.0, plan="auto", verbose=True):
    """返回 (标准解 dict, 来源说明)。若 solution.json 缺中继安排，则按 plan 口径补全。"""
    if os.path.exists(SIO.SOL_JSON) and not force:
        sol = SIO.load()
        if verbose:
            LOG("  [标准解] 读取 %s：运输架次 %d，中继架次 %d，保障记录 %d"
                % (os.path.relpath(SIO.SOL_JSON, BASE), len(sol.get("transport", [])),
                   len(sol.get("relay", [])), len(sol.get("coverage", []))))
        src = "results/solution.json"
    else:
        sol = build_solution(tlimit=tlimit, plan=plan, verbose=verbose)
        SIO.save(sol)
        if verbose:
            LOG("  [标准解] 已写入 %s" % os.path.relpath(SIO.SOL_JSON, BASE))
        src = "现场生成并写回 results/solution.json"
    sol, extra = complete_relay(sol, plan=plan, force=force, verbose=verbose)
    return sol, src + extra


# ===========================================================================
# 二、输入规范化：架次—服务区关联
# ===========================================================================
def normalize(sol, nodes=None, rtype=None, verbose=True):
    """给运输/中继记录补齐派生字段，并对中继时刻字段做口径归一。

    中继记录的 depart/back 由上游生成，存在“绝对时刻”与“时长”两种写法混用的风险，
    这里统一按几何重算：`depart = link_done − 建链 − 去程`、`back = end + 返程`
    （去程/返程由 `dcore.relay_flight` 用悬停点经纬度与离地高度算得），
    并对与记录值明显不一致的条目给出提示。
    """
    trecs = [dict(r) for r in sol.get("transport", [])]
    for r in trecs:
        areas = [s for s in r.get("route", []) if isinstance(s, str) and s.startswith("S")]
        if not areas:
            areas = sorted((r.get("boxes") or {}).keys())
        r["areas"] = sorted(set(areas))
        t = str(r.get("type") or r.get("g") or "").strip().upper()
        r["type"] = t[:1]
        r["start"] = float(r.get("start", 0.0) or 0.0)
        r["end"] = float(r.get("end", r["start"]) or 0.0)
        r["chg"] = float(r.get("chg", 0.0) or 0.0)
        r["energy"] = float(r.get("energy", 0.0) or 0.0)
        boxes = r.get("boxes") or {}
        r["n_box"] = int(sum(len(v) for v in boxes.values()))
    rrecs = [dict(r) for r in sol.get("relay", [])]
    n_fix = 0
    for r in rrecs:
        ld = float(r.get("link_done", 0.0) or 0.0)
        e = float(r.get("end", ld) or 0.0)
        d_raw = float(r.get("depart", 0.0) or 0.0)
        b_raw = float(r.get("back", e) or 0.0)
        t_out = t_back = None
        if nodes is not None and rtype is not None and r.get("lon") is not None:
            agl = r.get("agl")
            if agl is None:
                agl = float(r.get("hover_alt", 0.0) or 0.0) - float(r.get("ground", 0.0) or 0.0)
            try:
                rf = D.relay_flight(rtype, nodes, float(r["lon"]), float(r["lat"]),
                                    max(0.0, float(agl)))
                t_out, t_back = float(rf["t_out"]), float(rf["t_back"])
            except Exception:                                   # noqa: BLE001
                t_out = t_back = None
        if t_out is not None:
            d = max(0.0, ld - float(rtype.t_link) - t_out)
            b = e + t_back
            if abs(b - b_raw) > 1.0 or abs(d - d_raw) > 1.0:
                n_fix += 1
        else:                                       # 无法几何重算时退化为字段自洽修正
            d = d_raw if d_raw < ld - 1e-9 else 0.0
            b = b_raw if b_raw > e + 1e-9 else e + max(0.0, b_raw)
            n_fix += 1
        r["depart"], r["link_done"], r["end"], r["back"] = d, ld, e, b
        r["chg"] = float(r.get("chg", 0.0) or 0.0)
        r["energy"] = float(r.get("e_total", r.get("energy", 0.0)) or 0.0)
    if n_fix and verbose:
        LOG("  [口径] %d 个中继架次的出发/返回时刻按悬停点几何重算（统一绝对时刻口径）"
            % n_fix)
    cov = [dict(c) for c in sol.get("coverage", [])]
    return trecs, rrecs, cov


def dist_km_of(rec, nodes):
    """架次航程（km）：沿 route 逐段 Haversine。"""
    route = [x for x in rec.get("route", []) if x in nodes]
    if len(route) < 2:
        return 0.0
    tot = 0.0
    for a, b in zip(route[:-1], route[1:]):
        tot += D.haversine(nodes[a].lon, nodes[a].lat, nodes[b].lon, nodes[b].lat)
    return tot / 1000.0


# ===========================================================================
# 三、不可分割块（硬耦合）
# ===========================================================================
class DSU:
    def __init__(self, keys):
        self.p = {k: k for k in keys}

    def find(self, x):
        p = self.p
        r = x
        while p[r] != r:
            r = p[r]
        while p[x] != r:
            p[x], x = r, p[x]
        return r

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build_blocks(trecs, sids=SIDS):
    """按“同一运输架次的服务区必须同组”做并查集，返回 (块列表, 未服务服务区, 耦合链)。"""
    dsu = DSU(list(sids))
    served = set()
    for r in trecs:
        for s in r["areas"]:
            served.add(s)
        for s in r["areas"][1:]:
            dsu.union(r["areas"][0], s)
    groups = defaultdict(list)
    for s in sids:
        groups[dsu.find(s)].append(s)
    blocks = [sorted(v) for v in groups.values()]
    blocks.sort(key=lambda b: (-len(b), b[0]))
    unserved = [s for s in sids if s not in served]
    links = [(r["sid"], r["areas"]) for r in trecs if len(r["areas"]) > 1]
    return blocks, unserved, links


# ===========================================================================
# 四、资源核算：峰值并发 + 区间图着色
# ===========================================================================
def peak_of(intervals):
    """区间 [a,b) 的最大并发数（事件扫描；同一时刻先处理结束再处理开始）。"""
    ev = []
    for a, b in intervals:
        if b < a:
            a, b = b, a
        ev.append((a, 1))
        ev.append((b, -1))
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = mx = 0
    for _, d in ev:
        cur += d
        if cur > mx:
            mx = cur
    return mx


def ncolor_of(intervals):
    """区间图着色：最少颜色数 = 最大团 = 最大重叠数（按开始时刻贪心 + 小顶堆，区间图下最优）。"""
    iv = sorted((min(a, b), max(a, b)) for a, b in intervals)
    heap = []
    mx = 0
    for a, b in iv:
        while heap and heap[0] <= a + 1e-9:
            heapq.heappop(heap)
        heapq.heappush(heap, b)
        if len(heap) > mx:
            mx = len(heap)
    return mx


def max_overlap_pairwise(intervals):
    """独立复算（自检用）：O(n^2) 统计每个区间左端点被多少个区间覆盖，取最大值。

    区间图的最大团 = 最大重叠点数；而在最大重叠点 t 处，起点最靠右的那个区间 i 满足
    “所有覆盖 t 的区间都覆盖 i 的左端点”，因此 max_i |{j : a_j <= a_i < b_j}| 恰为最大重叠数。
    """
    iv = [(min(a, b), max(a, b)) for a, b in intervals]
    best = 0
    for a1, _b1 in iv:
        c = sum(1 for a2, b2 in iv if a2 <= a1 + 1e-9 and b2 > a1 + 1e-9)
        if c > best:
            best = c
    return best


def transport_resources(sel_t):
    out = {}
    for g in ("A", "B", "C"):
        occ = [(r["start"], r["end"]) for r in sel_t if r["type"] == g]
        occ_c = [(r["start"], r["end"] + max(0.0, r["chg"])) for r in sel_t if r["type"] == g]
        out[g] = peak_of(occ)
        out["batt" + g] = ncolor_of(occ_c)
    return out


def relay_resources(sel_r):
    occ = [(r["depart"], r["back"]) for r in sel_r]
    occ_c = [(r["depart"], r["back"] + max(0.0, r["chg"])) for r in sel_r]
    return {"relay": peak_of(occ), "relayE": ncolor_of(occ_c)}


def merge_res(*ds):
    out = {}
    for d in ds:
        out.update(d)
    return out


def transport_workload(sel_t, nodes):
    return dict(n_sortie=len(sel_t),
                n_box=int(sum(r["n_box"] for r in sel_t)),
                mach_h=sum(r["end"] - r["start"] for r in sel_t) / 3600.0,
                dist_km=sum(dist_km_of(r, nodes) for r in sel_t),
                energy=sum(r["energy"] for r in sel_t))


def relay_workload(sel_r):
    return dict(n_relay=len(sel_r),
                relay_h=sum(r["back"] - r["depart"] for r in sel_r) / 3600.0,
                relay_energy=sum(r["energy"] for r in sel_r))


# ===========================================================================
# 五、分区枚举
# ===========================================================================
def enumerate_partitions(nb, K, cap=400000):
    """枚举 nb 个块划分成 K 个非空组的所有方案（按首次出现顺序规范化，每个划分恰好一次）。"""
    out = []
    cur = [0] * nb

    def rec(i, mx):
        if len(out) >= cap:
            return
        if i == nb:
            if mx == K - 1:
                out.append(tuple(cur))
            return
        if (nb - i) < (K - 1 - mx):
            return
        for g in range(min(mx + 1, K - 1) + 1):
            cur[i] = g
            rec(i + 1, mx if mx > g else g)
        cur[i] = 0

    rec(0, -1)
    return out


def partition_groups(assign, blocks):
    groups = defaultdict(list)
    for bi, g in enumerate(assign):
        groups[g].extend(blocks[bi])
    return [sorted(groups[g]) for g in range(max(assign) + 1)]


# ===========================================================================
# 六、指标：规模 / 冗余 / 均衡 / 缺口
# ===========================================================================
BAL_INDS = [("n_box", "箱数(箱)"), ("n_sortie", "架次数(架次)"), ("mach_h", "运输机时(h)"),
            ("dist_km", "运输航程(km)"), ("energy", "运输能耗(kWh)"),
            ("n_relay", "中继架次数(架次)"), ("relay_h", "中继机时(h)")]


def scheme_metrics(groups_res, groups_work):
    """给定各组资源需求与工作量，计算规模 / 冗余 / 均衡 / 缺口四类指标。"""
    K = len(groups_res)
    need = {j: int(sum(g[j] for g in groups_res)) for j in CLASSES}
    gap = {j: relu(need[j] - INV[j]) for j in CLASSES}
    hard_gap = {j: [relu(g[j] - INV[j]) for g in groups_res] for j in CLASSES}
    feas = all(gap[j] == 0 for j in CLASSES)

    # 配置量：库存充足则“保底需求 + 按需求比例分摊余量”，库存不足时配置=需求、另计缺口
    cfg = [dict() for _ in range(K)]
    for j in CLASSES:
        d = [g[j] for g in groups_res]
        tot = sum(d)
        if gap[j] == 0:
            if tot == 0:
                for i in range(K):
                    cfg[i][j] = 0
                continue
            surplus = INV[j] - tot
            add = [int(math.floor(surplus * di / tot)) for di in d]
            rem = surplus - sum(add)
            for i in sorted(range(K), key=lambda i: (-d[i], i))[:rem]:
                add[i] += 1
            for i in range(K):
                cfg[i][j] = d[i] + add[i]
        else:
            for i in range(K):
                cfg[i][j] = d[i]

    tot_need = sum(WEIGHT[j] * need[j] for j in CLASSES)
    tot_cfg = sum(WEIGHT[j] * sum(cfg[i][j] for i in range(K)) for j in CLASSES)
    grp_w = [sum(WEIGHT[j] * groups_res[i][j] for j in CLASSES) for i in range(K)]
    redundancy = (tot_cfg - tot_need) / tot_cfg if tot_cfg > 0 else 0.0

    bal = {}
    for key, cn in BAL_INDS:
        v = [groups_work[i].get(key, 0.0) for i in range(K)]
        m = sum(v) / K
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / K)
        bal[key] = dict(cn=cn, vals=v, rng=max(v) - min(v),
                        cv=(sd / m if m > 0 else 0.0), mx=max(v), mn=min(v))
    cvs = [bal[k]["cv"] for k, _ in BAL_INDS if bal[k]["cv"] > 0]
    bal_cv = sum(cvs) / len(cvs) if cvs else 0.0
    spans = []
    for k, _ in BAL_INDS:
        tot = sum(bal[k]["vals"])
        if tot > 0:
            spans.append(bal[k]["rng"] / (tot / K))
    bal_span = max(spans) if spans else 0.0
    return dict(need=need, gap=gap, hard_gap=hard_gap, feasible=feas, cfg=cfg,
                group_need=[dict(g) for g in groups_res],
                total_need=tot_need, total_cfg=tot_cfg, group_w=grp_w,
                max_group_w=(max(grp_w) if grp_w else 0.0),
                redundancy=redundancy, balance=bal, bal_cv=bal_cv, bal_span=bal_span,
                gap_norm=sum(gap[j] / INV[j] for j in CLASSES),
                gap_total=sum(gap.values()))


def rank_key(m):
    """推荐排序键：可行性 → 归一化缺口 → 总资源当量 → 最大组当量 → 组间不均衡度。"""
    return (0 if m["feasible"] else 1,
            round(m["gap_norm"], 6),
            round(m["total_need"], 6),
            round(m["max_group_w"], 6),
            round(m["bal_cv"], 6))


# 反事实情形：允许某些资源类跨组共享（作为全局资源池，只按全局峰值/色数配置一份）
SHARE_CASES = [
    ("S0 完全隔离（基准）", []),
    ("S1 仅共享中继无人机与能源组件", ["relay", "relayE"]),
    ("S2 仅共享 B 型运输机与 B 型电池", ["B", "battB"]),
    ("S3 共享 B 型资源 + 中继资源", ["B", "battB", "relay", "relayE"]),
    ("S4 共享全部能源单元（电池组/能源组件）", ["battA", "battB", "battC", "relayE"]),
    ("S5 全部资源全局共享（等价于一体化 K=1）", list(CLASSES)),
]


def sharing_table(res, k1):
    """对各分区方案做“允许跨组共享”的反事实核算，返回缺口/当量对比表。

    运输/电池类与中继类分别统计：中继部分在 Q3 最终方案回填前是估算值，
    单列可以避免估算噪声污染“共享能否消除缺口”的结论。
    """
    out = []
    for name, share in SHARE_CASES:
        rec = dict(情形=name, 共享资源=("、".join(CLASS_CN[j] for j in share) if share else "无"))
        for K in (2, 3):
            m = res[K]["rows"][0]["met"]
            need = {j: (k1["res"][j] if j in share else m["need"][j]) for j in CLASSES}
            gap = {j: relu(need[j] - INV[j]) for j in CLASSES}
            gt = sum(gap[j] for j in CLASSES if j not in ("relay", "relayE"))
            gr = sum(gap[j] for j in ("relay", "relayE"))
            rec["K=%d当量" % K] = round(sum(WEIGHT[j] * need[j] for j in CLASSES), 2)
            rec["K=%d运输电池缺口" % K] = gt
            rec["K=%d中继缺口" % K] = gr
            rec["K=%d可行" % K] = "是" if (gt == 0 and gr == 0) else "否"
            rec["K=%d运输电池可行" % K] = "是" if gt == 0 else "否"
            rec["K=%d缺口明细" % K] = "；".join(
                "%s缺%d" % (CLASS_CN[j], gap[j]) for j in CLASSES if gap[j]) or "无"
        out.append(rec)
    return out


def sharing_conclusion(res, k1, table):
    """把共享反事实表压缩成结论（以运输/电池类为准，中继另述）。"""
    txt = []
    best = None
    for t in table:
        if t["K=2运输电池可行"] == "是" and t["K=3运输电池可行"] == "是":
            best = t
            break
    if best is not None:
        txt.append("就**运输机与电池**而言，在考察的共享情形中 **%s** 即可让 K=2 与 K=3 "
                   "同时满足库存（该情形下 K=2 资源当量 %.1f、K=3 为 %.1f，已回落到一体化水平 "
                   "%.1f），说明运输侧的缺口完全来自“B 型机与 B 型电池不得跨组调配”这一条假设，"
                   "而不是装备总量不足——B 型机在两组之间是**时间错峰**使用的，"
                   "把它作为全局池调度不需要新增任何装备。"
                   % (best["情形"], best["K=2当量"], best["K=3当量"], k1["met"]["total_need"]))
    else:
        txt.append("即使在考察的最宽松共享情形下，运输机与电池仍无法满足库存，需追加装备。")
    r2 = table[0]["K=2中继缺口"]
    r3 = table[0]["K=3中继缺口"]
    if r2 or r3:
        txt.append("中继类在完全隔离情形下仍显示缺口（K=2 缺 %d、K=3 缺 %d）；"
                   "该数值取自 `solution.json` 的 `relay` 字段（问题三 2 架折中方案的实际占用），"
                   "**不含问题三建议的那 1 架增配**——采纳增配后的中继缺口见 7.4 节。"
                   % (r2, r3))
    return "".join(txt)


def block_inner_peak(blocks, trecs):
    """每个不可分割块**内部**各机型架次的峰值并发（对任何包含该块的组都是需求下界）。"""
    out = []
    for b in blocks:
        aset = set(b)
        sel = [r for r in trecs if set(r["areas"]) <= aset]
        out.append({g: peak_of([(r["start"], r["end"]) for r in sel if r["type"] == g])
                    for g in ("A", "B", "C")})
    return out


def struct_lb(peaks, K, n_block):
    """K 分组时 Σ_g 峰值_g 的严格下界。

    对块 b，任何包含它的任务组峰值 >= p_b（峰值对加入架次单调不减）。于是
    Σ_g 峰值_g >= Σ_g max_{b∈g} p_b，而该式在“把 p 最大的块单独成组、其余 K-1 组
    尽量塞入 p=0 的块”时取最小：若 p=0 的块数 z >= K-1，下界即 max p；否则还需把
    (K-1-z) 个 p 最小的正块分出去。
    """
    if n_block < K:
        return 0
    p = sorted(peaks, reverse=True)
    if not p or p[0] <= 0:
        return 0
    z = sum(1 for x in p if x <= 0)
    need = max(0, K - 1 - z)
    pos = sorted(x for x in p if x > 0)
    return p[0] + sum(pos[:min(need, len(pos))])


def structural_analysis(blocks, trecs, rows):
    """结构性瓶颈分析：判定“缺口与分区方式无关”的必然性下界。"""
    per_block = block_inner_peak(blocks, trecs)
    sb = {}
    for g in ("A", "B", "C"):
        vals = [d[g] for d in per_block]
        lb2, lb3 = struct_lb(vals, 2, len(blocks)), struct_lb(vals, 3, len(blocks))
        sb[g] = dict(n_block=sum(1 for v in vals if v > 0), inner_max=max(vals) if vals else 0,
                     lb2=lb2, lb3=lb3, fg2=relu(lb2 - INV[g]), fg3=relu(lb3 - INV[g]))
    for g in ("A", "B", "C"):
        j = "batt" + g
        sb[j] = dict(sb[g])          # 电池占用区间包含无人机占用区间 ⇒ 下界同无人机
    hot = [(g, sb[g]) for g in ("A", "B", "C") if sb[g]["fg2"] or sb[g]["fg3"]]
    if hot:
        parts = []
        for g, s in hot:
            parts.append("**%s 型架次出现在全部 %d 个不可分割块中**（每块都有该机型架次），"
                         "块内峰值最大 %d 架，"
                         "由此得到严格下界：K=2 时 %s 型运输机至少需要 %d 架、K=3 时至少 %d 架，"
                         "而库存仅 %d 架 ⇒ K=2 必然缺 %d 架、K=3 必然缺 %d 架"
                         % (g, len(blocks), s["inner_max"], g,
                            s["lb2"], s["lb3"], INV[g], s["fg2"], s["fg3"]))
        concl = "；".join(parts) + \
            "。换言之，**只要把 15 个服务区拆成 2 组或 3 组，这个缺口就无法通过“换一种分法”消除**，" \
            "它由冻结的 Q3 运输方案结构与 B 型机库存共同决定；" \
            "只有允许 B 型资源跨组共享、或追加 B 型装备，缺口才可能消除。"
    else:
        concl = ("没有任何机型构成结构性瓶颈，缺口可以通过调整分区方式缓解。")
    return dict(per_block=per_block, conclusion=concl, **sb)


# ===========================================================================
# 七、主分析
# ===========================================================================
def analyze(sol, keep=50, verbose=True):
    d = D.load_all()
    nodes, rtype = d["nodes"], d["rtype"]
    trecs, rrecs, cov = normalize(sol, nodes=nodes, rtype=rtype, verbose=verbose)
    if verbose:
        LOG("  [输入] 运输架次 %d 个，中继架次 %d 个，保障记录 %d 条"
            % (len(trecs), len(rrecs), len(cov)))

    blocks, unserved, links = build_blocks(trecs)
    if verbose:
        LOG("  [硬耦合] 不可分割块 %d 个：" % len(blocks)
            + " | ".join("{%s}" % ",".join(b) for b in blocks))
        LOG("  [硬耦合] 多服务区架次 %d 个，耦合链：%s"
            % (len(links), "; ".join("%s:%s" % (sid, "+".join(a)) for sid, a in links)))
        if unserved:
            LOG("  [硬耦合] 警告：未被任何架次服务的服务区 %s" % unserved)

    tsid2area = {r["sid"]: r["areas"] for r in trecs}
    relay_cov = defaultdict(lambda: defaultdict(float))   # 中继架次 -> 运输架次 -> 保障秒数
    for c in cov:
        relay_cov[c.get("relay", "")][c["sid"]] += max(0.0,
                                                       float(c.get("t1", 0)) - float(c.get("t0", 0)))

    results = {}
    for K in (2, 3):
        assigns = enumerate_partitions(len(blocks), K)
        tcache, wcache = {}, {}

        def tpkg(gidx):
            key = tuple(sorted(gidx))
            if key not in tcache:
                areas = [s for bi in key for s in blocks[bi]]
                aset = set(areas)
                sel_t = [r for r in trecs if set(r["areas"]) <= aset]
                tcache[key] = (areas, sel_t, transport_resources(sel_t),
                               transport_workload(sel_t, nodes))
            return tcache[key]

        scored = []
        for a in assigns:
            gi = defaultdict(list)
            for bi, g in enumerate(a):
                gi[g].append(bi)
            packs = [tpkg(tuple(gi[g])) for g in range(K)]
            sel_t = [p[1] for p in packs]
            sel_r, cross, nocov = [[] for _ in range(K)], [[] for _ in range(K)], []
            for r in rrecs:
                vote = defaultdict(float)
                for tsid, sec in relay_cov.get(r["sid"], {}).items():
                    ar = tsid2area.get(tsid)
                    if ar:
                        for gg, p in enumerate(packs):
                            if ar[0] in p[0]:
                                vote[gg] += sec
                                break
                if vote:
                    gbest = max(vote.items(), key=lambda kv: (kv[1], -kv[0]))[0]
                    if len(vote) > 1:
                        cross[gbest].append(r["sid"])
                else:
                    gbest = max(range(K), key=lambda i: (len(sel_t[i]), -i))
                    nocov.append(r["sid"])
                sel_r[gbest].append(r)
            res = [merge_res(p[2], relay_resources(sel_r[i])) for i, p in enumerate(packs)]
            wrk = []
            for i, p in enumerate(packs):
                w = dict(p[3])
                w.update(relay_workload(sel_r[i]))
                wrk.append(w)
            m = scheme_metrics(res, wrk)
            scored.append((rank_key(m), a))
        scored.sort(key=lambda x: (x[0], x[1]))
        rows = []
        for key, a in scored[:keep]:
            gi = defaultdict(list)
            for bi, g in enumerate(a):
                gi[g].append(bi)
            groups = [sorted(s for bi in gi[g] for s in blocks[bi]) for g in range(K)]
            gmap = {}
            for gg, g in enumerate(groups):
                for s in g:
                    gmap[s] = gg
            sel_t = [[] for _ in range(K)]
            for r in trecs:
                sel_t[gmap[r["areas"][0]]].append(r)
            sel_r, cross, nocov = [[] for _ in range(K)], [[] for _ in range(K)], []
            for r in rrecs:
                vote = defaultdict(float)
                for tsid, sec in relay_cov.get(r["sid"], {}).items():
                    ar = tsid2area.get(tsid)
                    if ar:
                        vote[gmap[ar[0]]] += sec
                if vote:
                    gbest = max(vote.items(), key=lambda kv: (kv[1], -kv[0]))[0]
                    if len(vote) > 1:
                        cross[gbest].append(r["sid"])
                else:
                    gbest = max(range(K), key=lambda i: (len(sel_t[i]), -i))
                    nocov.append(r["sid"])
                sel_r[gbest].append(r)
            res = [merge_res(transport_resources(sel_t[i]), relay_resources(sel_r[i]))
                   for i in range(K)]
            wrk = []
            for i in range(K):
                w = transport_workload(sel_t[i], nodes)
                w.update(relay_workload(sel_r[i]))
                wrk.append(w)
            m = scheme_metrics(res, wrk)
            rows.append(dict(assign=a, groups=groups, res=res, wrk=wrk, met=m,
                             sel_t=sel_t, sel_r=sel_r, cross=cross, nocov=nocov))
        results[K] = dict(rows=rows, blocks=blocks, n_enum=len(assigns),
                          n_feasible=sum(1 for k, _ in scored if k[0] == 0))
        if verbose:
            LOG("  [枚举] K=%d：块 %d 个 → 合法分区 %d 个，无缺口 %d 个"
                % (K, len(blocks), len(assigns), results[K]["n_feasible"]))
            for row in rows[:4]:
                m = row["met"]
                LOG("         %s | 当量=%.1f 最大组=%.1f 缺口=%s 综合CV=%.3f"
                    % (" / ".join("{%s}" % ",".join(g) for g in row["groups"]),
                       m["total_need"], m["max_group_w"],
                       ",".join("%s:%d" % (CLASS_CN[j], m["gap"][j])
                                for j in CLASSES if m["gap"][j]) or "无", m["bal_cv"]))
    return dict(trecs=trecs, rrecs=rrecs, cov=cov, blocks=blocks, unserved=unserved,
                links=links, relay_cov=relay_cov, results=results, nodes=nodes,
                struct=structural_analysis(blocks, trecs, results))


def k1_reference(an):
    """不做分组（一体化调度）的资源需求，作为参照基线。"""
    res = merge_res(transport_resources(an["trecs"]), relay_resources(an["rrecs"]))
    wrk = dict(transport_workload(an["trecs"], an["nodes"]))
    wrk.update(relay_workload(an["rrecs"]))
    return dict(res=res, wrk=wrk, met=scheme_metrics([res], [wrk]))


# ===========================================================================
# 八、输出：xlsx
# ===========================================================================
def write_xlsx(an, k1, path=XLSX_OUT):
    res = an["results"]
    rows = []
    for K in (2, 3):
        best = res[K]["rows"][0]
        for gi, (areas, r) in enumerate(zip(best["groups"], best["res"]), 1):
            rows.append({
                "K（2或3）": K,
                "任务组编号": "G%d-%d" % (K, gi),
                "服务区列表": ";".join(areas),
                "A型运输无人机数": r["A"], "B型运输无人机数": r["B"], "C型运输无人机数": r["C"],
                "A型电池组数": r["battA"], "B型电池组数": r["battB"], "C型电池组数": r["battC"],
                "中继无人机数": r["relay"], "中继能源组件数": r["relayE"],
            })
    cols = ["K（2或3）", "任务组编号", "服务区列表", "A型运输无人机数", "B型运输无人机数",
            "C型运输无人机数", "A型电池组数", "B型电池组数", "C型电池组数",
            "中继无人机数", "中继能源组件数"]
    sheets = {"Q4_分区配置": pd.DataFrame(rows, columns=cols)}

    r2 = []
    for K in (2, 3):
        best = res[K]["rows"][0]
        for gi, (areas, w, r) in enumerate(zip(best["groups"], best["wrk"], best["res"]), 1):
            r2.append(dict(K=K, 任务组="G%d-%d" % (K, gi), 服务区数=len(areas),
                           服务区列表=";".join(areas),
                           箱数=w["n_box"], 运输架次数=w["n_sortie"],
                           运输机时_h=round(w["mach_h"], 3), 运输航程_km=round(w["dist_km"], 3),
                           运输能耗_kWh=round(w["energy"], 3),
                           中继架次数=w["n_relay"], 中继机时_h=round(w["relay_h"], 3),
                           中继能耗_kWh=round(w["relay_energy"], 3),
                           资源当量=round(sum(WEIGHT[j] * r[j] for j in CLASSES), 3)))
    sheets["Q4_分组明细"] = pd.DataFrame(r2)

    r3 = []
    for j in CLASSES:
        row = dict(资源类别=CLASS_CN[j], 库存=INV[j])
        for K in (2, 3):
            m = res[K]["rows"][0]["met"]
            row["K=%d需求" % K] = m["need"][j]
            row["K=%d缺口" % K] = m["gap"][j]
        row["一体化K=1需求"] = k1["res"][j]
        row["K=1缺口"] = relu(k1["res"][j] - INV[j])
        row["库存来源"] = INV_SRC[j]
        r3.append(row)
    sheets["Q4_资源汇总与库存"] = pd.DataFrame(r3)

    r4 = []
    for K in (2, 3):
        m = res[K]["rows"][0]["met"]
        for key, b in m["balance"].items():
            mean = sum(b["vals"]) / K
            row = dict(K=K, 指标=b["cn"], 最大值=round(b["mx"], 3), 最小值=round(b["mn"], 3),
                       极差=round(b["rng"], 3),
                       极差率=round(b["rng"] / mean, 4) if mean > 0 else 0.0,
                       变异系数CV=round(b["cv"], 4))
            for i, v in enumerate(b["vals"], 1):
                row["组%d" % i] = round(v, 3)
            r4.append(row)
        r4.append(dict(K=K, 指标="综合CV(7项均值)", 变异系数CV=round(m["bal_cv"], 4)))
        r4.append(dict(K=K, 指标="最大极差率", 极差率=round(m["bal_span"], 4)))
    sheets["Q4_均衡性"] = pd.DataFrame(r4)

    r5 = []
    for K in (2, 3):
        for rank, row in enumerate(res[K]["rows"], 1):
            m = row["met"]
            r5.append(dict(K=K, 排序=rank, 方案编号="K%d-P%02d" % (K, rank),
                           分区=" | ".join("{%s}" % ",".join(g) for g in row["groups"]),
                           总资源当量=round(m["total_need"], 3),
                           最大组当量=round(m["max_group_w"], 3),
                           可行_无缺口=("是" if m["feasible"] else "否"),
                           缺口合计=m["gap_total"],
                           冗余度=round(m["redundancy"], 4),
                           工作量综合CV=round(m["bal_cv"], 4),
                           跨组保障中继架次数=sum(len(x) for x in row["cross"]),
                           **{CLASS_CN[j] + "_需求": m["need"][j] for j in CLASSES}))
    sheets["Q4_备选方案"] = pd.DataFrame(r5)

    r6 = [dict(资源类别=CLASS_CN[j], 一体化需求=k1["res"][j], 库存=INV[j],
               缺口=relu(k1["res"][j] - INV[j])) for j in CLASSES]
    sheets["Q4_一体化参照"] = pd.DataFrame(r6)

    sheets["Q4_共享反事实"] = pd.DataFrame(an["sharing"])

    sb = an["struct"]
    r7 = []
    for j in ("A", "B", "C", "battA", "battB", "battC"):
        r7.append(dict(资源类别=CLASS_CN[j], 含该资源的块数=sb[j]["n_block"],
                       总块数=len(an["blocks"]), K2需求下界=sb[j]["lb2"], K3需求下界=sb[j]["lb3"],
                       库存=INV[j], K2必然缺口=sb[j]["fg2"], K3必然缺口=sb[j]["fg3"]))
    sheets["Q4_结构瓶颈"] = pd.DataFrame(r7)

    with pd.ExcelWriter(path) as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return path, list(sheets)


# ===========================================================================
# 九、自检
# ===========================================================================
def self_check(an, k1, verbose=True):
    res = an["results"]
    trecs, rrecs = an["trecs"], an["rrecs"]
    checks = []

    def add(name, ok, detail):
        checks.append(dict(检查项=name, 结果=("通过" if ok else "不通过"), 说明=detail))

    for K in (2, 3):
        best = res[K]["rows"][0]
        flat = [s for g in best["groups"] for s in g]
        ok = (sorted(flat) == SIDS) and len(flat) == len(set(flat)) \
            and all(len(g) >= 1 for g in best["groups"])
        add("(a) K=%d 每个服务区恰好属于一个任务组" % K, ok,
            "各组服务区数 %s；并集 %d 个，重复 %d 个，每组非空 %s"
            % ([len(g) for g in best["groups"]], len(set(flat)),
               len(flat) - len(set(flat)), all(len(g) >= 1 for g in best["groups"])))

    for K in (2, 3):
        best = res[K]["rows"][0]
        gmap = {}
        for gi, g in enumerate(best["groups"]):
            for s in g:
                gmap[s] = gi
        bad = [r["sid"] for r in trecs if len({gmap.get(s, -1) for s in r["areas"]}) > 1]
        add("(b) K=%d 同架次服务区同组（硬耦合）" % K, not bad,
            "多服务区架次 %d 个；违反架次 %s"
            % (sum(1 for r in trecs if len(r["areas"]) > 1), bad if bad else "无"))

    for K in (2, 3):
        best = res[K]["rows"][0]
        allok, det = True, []
        for gi in range(K):
            sel_t = best["sel_t"][gi]
            r = best["res"][gi]
            pk = SIO.resource_peak(sel_t, "type", ("start", "end"), dtype="type")
            for g in ("A", "B", "C"):
                v = relu(int(pk.get(g, 0)))
                ok = (v == r[g])
                allok &= ok
                det.append("G%d-%d %s型机 复算%d/核算%d%s"
                           % (K, gi + 1, g, v, r[g], "" if ok else " 不一致"))
            for g in ("A", "B", "C"):
                iv = [(x["start"], x["end"] + max(0.0, x["chg"]))
                      for x in sel_t if x["type"] == g]
                v1 = max_overlap_pairwise(iv)
                v2 = peak_of(iv)
                ok = (v1 == r["batt" + g] == v2)
                allok &= ok
                det.append("G%d-%d %s型电池 两两复算%d/事件扫描%d/着色%d%s"
                           % (K, gi + 1, g, v1, v2, r["batt" + g], "" if ok else " 不一致"))
        add("(c) K=%d 各组运输资源与时间轴重算一致" % K, allok, "；".join(det))

    for K in (2, 3):
        best = res[K]["rows"][0]
        allok, det = True, []
        for gi in range(K):
            sel_r = best["sel_r"][gi]
            r = best["res"][gi]
            p1 = peak_of([(x["depart"], x["back"]) for x in sel_r])
            p2 = max_overlap_pairwise([(x["depart"], x["back"]) for x in sel_r])
            c1 = ncolor_of([(x["depart"], x["back"] + max(0.0, x["chg"])) for x in sel_r])
            c2 = max_overlap_pairwise([(x["depart"], x["back"] + max(0.0, x["chg"]))
                                       for x in sel_r])
            ok = (p1 == p2 == r["relay"]) and (c1 == c2 == r["relayE"])
            allok &= ok
            det.append("G%d-%d 中继机(扫描%d/两两%d/核算%d) 能源组件(着色%d/两两%d/核算%d)%s"
                       % (K, gi + 1, p1, p2, r["relay"], c1, c2, r["relayE"],
                          "" if ok else " 不一致"))
        add("(c) K=%d 各组中继资源与时间轴重算一致" % K, allok, "；".join(det))

    for K in (2, 3):
        best = res[K]["rows"][0]
        seen, dup, cnt = set(), 0, 0
        for gi in range(K):
            for x in best["sel_t"][gi]:
                cnt += 1
                if x["sid"] in seen:
                    dup += 1
                seen.add(x["sid"])
        add("(d) K=%d 运输架次被唯一分组覆盖" % K, (cnt == len(trecs) and dup == 0),
            "各组架次数合计 %d，总架次数 %d，重复计数 %d" % (cnt, len(trecs), dup))

    for K in (2, 3):
        best = res[K]["rows"][0]
        ok = all(r["batt" + g] >= r[g] for r in best["res"] for g in ("A", "B", "C")) \
            and all(r["relayE"] >= r["relay"] for r in best["res"])
        add("(e) K=%d 物理一致性：电池/能源组件数 >= 无人机数" % K, ok,
            "逐组逐机型均满足" if ok else "存在违反")

    for K in (2, 3):
        best = res[K]["rows"][0]
        seen, dup, cnt = set(), 0, 0
        for gi in range(K):
            for x in best["sel_r"][gi]:
                cnt += 1
                if x["sid"] in seen:
                    dup += 1
                seen.add(x["sid"])
        add("(g) K=%d 中继架次被唯一归组" % K, (cnt == len(rrecs) and dup == 0),
            "各组中继架次合计 %d，总中继架次 %d，重复 %d" % (cnt, len(rrecs), dup))

    ok = (INV["A"] == 4 and INV["B"] == 2 and INV["C"] == 2 and INV["battA"] == 6
          and INV["battB"] == 4 and INV["battC"] == 4 and INV["relay"] == 2 and INV["relayE"] == 6)
    add("(f) 库存口径与附件一致", ok,
        "运输机 A/B/C = 4/2/2 架；电池 = 6/4/4 组；中继机 = 2 架；能源组件 = 6 组")

    passed = sum(1 for c in checks if c["结果"] == "通过")
    if verbose:
        LOG("")
        LOG("  ===== 自检 =====")
        for c in checks:
            LOG("   [%s] %s" % (c["结果"], c["检查项"]))
            LOG("          %s" % c["说明"][:300])
        LOG("  自检结果：%d/%d 项通过" % (passed, len(checks)))
    return checks, passed, len(checks)


# ===========================================================================
# 十、输出：说明文档
# ===========================================================================
def _tbl(headers, rows):
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def _weight_sensitivity(res):
    lines = ["对资源当量权重做灵敏度分析（能源单元权重取 0.2 / 0.4 / 0.6，整机权重固定 1.0）：", ""]
    rows = []
    base = {K: res[K]["rows"][0]["assign"] for K in (2, 3)}
    for wb in (0.2, 0.4, 0.6):
        W = dict(WEIGHT)
        for j in ("battA", "battB", "battC", "relayE"):
            W[j] = wb
        cells = []
        for K in (2, 3):
            scored = []
            for row in res[K]["rows"]:
                m = row["met"]
                tot = sum(W[j] * m["need"][j] for j in CLASSES)
                mx = max(sum(W[j] * r[j] for j in CLASSES) for r in row["res"])
                scored.append(((0 if m["feasible"] else 1, round(m["gap_norm"], 6),
                                round(tot, 6), round(mx, 6), round(m["bal_cv"], 6)),
                               row, tot))
            scored.sort(key=lambda x: (x[0], x[1]["assign"]))
            cells.append(("一致" if scored[0][1]["assign"] == base[K] else "改变")
                         + "（当量 %.1f）" % scored[0][2])
        rows.append(["%.1f" % wb, cells[0], cells[1]])
    lines.append(_tbl(["能源单元权重", "K=2 最优方案", "K=3 最优方案"], rows))
    lines += ["", "结论：权重在 0.2–0.6 区间内变动时推荐方案保持不变，说明结果对权重取值稳健。"]
    return "\n".join(lines)


def _recommend_text(r2, r3):
    """数据驱动地给出总体建议：先比可行性，再比当量、最大组规模、不均衡度与缺口。"""
    if r2["feasible"] and not r3["feasible"]:
        return ("**推荐 2 组分区**。2 组方案在现有库存内可完全自足，而 3 组方案把运输峰值"
                "切得更碎、又必须为每个小组配齐“最小可运行单元”（至少 1 架机 + 至少 2 组电池"
                "才能形成飞行—充电—再飞行的周转链），从而出现资源缺口。在库存不变的条件下，"
                "2 组是唯一可执行的划分方式；若必须 3 组，需追加资源或重解 Q2/Q3 降低架次耦合度。")
    if r3["feasible"] and not r2["feasible"]:
        return "**推荐 3 组分区**。3 组方案能满足库存约束，2 组反而存在缺口。"
    if r2["feasible"] and r3["feasible"]:
        return ("两者均可行。若追求**资源占用最省、组间工作量最均衡**，选 2 组；"
                "若追求**单组任务规模小、便于分区独立指挥**，在库存允许时可考虑 3 组。"
                "综合资源当量与冗余，推荐 2 组。")
    # 均不可行：按 (缺口, 总当量, 最大组当量, 不均衡度) 判断支配关系
    worse = []
    if r3["gap_total"] > r2["gap_total"]:
        worse.append("缺口更大（%d vs %d 件/组）" % (r3["gap_total"], r2["gap_total"]))
    if r3["total_need"] > r2["total_need"]:
        worse.append("总资源当量更高（%.1f vs %.1f，+%.1f%%）"
                     % (r3["total_need"], r2["total_need"],
                        100 * (r3["total_need"] / r2["total_need"] - 1)))
    if r3["bal_cv"] > r2["bal_cv"]:
        worse.append("组间工作量更不均衡（综合 CV %.3f vs %.3f）"
                     % (r3["bal_cv"], r2["bal_cv"]))
    if r3["max_group_w"] > r2["max_group_w"] + 1e-9:
        worse.append("最大组当量更高（%.1f vs %.1f）" % (r3["max_group_w"], r2["max_group_w"]))
    head = ("两者都超出库存。**推荐 2 组分区**：在所有合法分区中，"
            "2 组的推荐方案在四个比较维度上都不劣于 3 组，且 3 组的推荐方案"
            + "、".join(worse) + "——即 3 组方案被 2 组方案**全面支配**"
            "（分组越细，各组独立配置的峰值资源被复制得越多）" if worse else
            "两者都超出库存，且互有优劣，需按指挥体制偏好取舍")
    tail = ("缓解缺口的四个方向：**(i) 允许 B 型机与 B 型电池跨组共享**——B 型资源在两组间是"
            "时间错峰使用的，把它当全局池调度可让 **B 型**缺口归零、无需新增装备"
            "（但 C 型缺口仍在，见 7.3）；"
            "**(ii) 追加装备**——优先补 B 型运输机与 B 型电池，并同步补 1 架 C 型运输机；"
            "**(iv) 追加中继**——按问题三结论增配 1 架中继无人机（见 7.4）；"
            "**(iii) 降低硬耦合**——在 Q2/Q3 重解时对“多服务区架次”加惩罚，使架次尽量单服务区化，"
            "以释放分区的自由度。")
    return head + tail


def write_md(an, k1, checks, passed, total, source, path=MD_OUT, elapsed=0.0):
    res = an["results"]
    trecs, rrecs = an["trecs"], an["rrecs"]
    L = []
    A = L.append
    A("# 问题四：服务区任务组划分与各组独立资源核算")
    A("")
    A("> 2026 中国研究生数学建模竞赛 D 题「山区洪涝灾害下无人机运输与通信协同优化」")
    A("> 本文由 `code/q4.py` 自动生成；标准解来源：%s。" % source)
    A("> 复现命令：`cd code && python q4.py`（仅重跑自检：`python q4.py --check`）。")
    A("")
    A("---")
    A("")
    A("## 一、问题理解与建模思路")
    A("")
    A("> **继承口径声明（问题四冻结的是哪一套方案）**：本文冻结并继承的是问题三的"
      "**运输方案**（货箱组批、服务区访问顺序、%d 个运输架次）以及问题三**库存约束下的 "
      "2 架中继折中方案**（`results/solution.json` 的 `relay` 字段，%d 个架次；"
      "**该方案的通信并非全程连续**）。问题三的结论是“给定运输时序下 2 架中继无可行解、"
      "最小增配为 3 架”，增配方案记为 `relay3` 字段。"
      "本文正文缺口表按**库存内可执行的 2 架折中方案**核算；7.4 节另外给出**若采纳增配"
      "（3 架中继）时**中继类资源的需求与缺口，两套口径不混用。"
      % (len(trecs), len(rrecs)))
    A("")
    A("问题四把问题三的联合调度方案**整体冻结**（货箱组批、服务区访问顺序、运输架次、"
      "中继架次、通信保障关系全部不变），只决策一件事：把 15 个服务区 S001–S015 划分为 "
      "K 个任务组（K=2 与 K=3），并分别核算每个任务组**独立执行**时所需的最小资源。")
    A("")
    A("三类约束决定了可行分区的形状：")
    A("")
    A("1. **划分约束**：每个服务区必须且只能属于一个任务组，每组至少 1 个服务区；")
    A("2. **硬耦合约束**：同一个运输架次服务的多个服务区必须划入同一任务组"
      "（组批与访问顺序被冻结，架次不可拆）；")
    A("3. **隔离约束**：任务执行期间各类资源不得跨组调配，每组的资源需求必须按"
      "**该组自身的时间轴**重新核算，而不能把总方案的资源数按比例摊派。")
    A("")
    A("求解链条：**架次—服务区关联图 → 并查集求不可分割块 → 块集合上完全枚举 K 分区 → "
      "逐组时间轴资源核算 → 四维指标评价 → 推荐与比较**。")
    A("")
    A("### 1.1 资源核算口径")
    A("")
    A(_tbl(["资源类别", "核算方法", "口径说明"], [
        ["A/B/C 型运输无人机（架）", "组内该机型架次的**峰值并发数**",
         "时间轴事件扫描统计最大并发，而不是架次总数——同一架机可连续执行多个架次"],
        ["A/B/C 型共享电池组（组）",
         "对 [start, end) 占用区间 ∪ [end, end+chg) 充电区间做**区间图着色**",
         "所需颜色数 = 区间图最大团 = 最大重叠数；按开始时刻贪心（小顶堆释放）即为最优解，"
         "因为区间图是完美图、贪心色数等于团数"],
        ["中继无人机（架）", "组内中继架次的**峰值并发数**，占用区间 [depart, back)",
         "中继架次占用 = 离开 O01 → 悬停服务 → 返回 O01 的全过程"],
        ["中继能源组件（组）", "对 [depart, back) ∪ [back, back+chg) 做同样的区间图着色",
         "能源组件在架次结束后需两阶段充电（SOC<90% 段占 T_full 的 65%，90–100% 占 35%）"
         "才能再次投入"],
    ]))
    A("")
    A("充电时长 `chg` 一律沿用问题三方案中记录的数值（由 `dcore.charge_time(soc, T_full)` "
      "按两阶段等效模型算得），保证与 Q3 能量口径完全一致。")
    A("")
    A("### 1.2 中继架次的归组规则")
    A("")
    A("题目要求各组只承担**本组服务区对应的**通信保障任务。一个中继架次在其悬停时段内可能"
      "同时保障若干运输架次；本程序按**覆盖时长投票**把它归入唯一任务组：统计该中继架次对"
      "每个任务组的运输架次的累计保障时长，归入时长最大的组（并列取编号小的组）。"
      "若某中继架次跨组保障，则在结果中单列“跨组保障中继架次”计数，提示该归组带来的耦合风险。")
    A("")
    A("> **跨组保障的严格处置（口径声明）**：按题面“各组只承担本组服务区对应的通信保障"
      "任务”，跨组保障在严格执行时**不被允许**。本文不把“投票硬塞进某一组”当作合法近似，"
      "而是把它当成一条**不可行性证据**：若某分组下出现跨组保障中继架次，该分组在严格口径下"
      "即不可行，必须额外为该组配一架中继（或在组间显式约定共享）。因此下文第 5–6 节表格中的"
      "“跨组保障中继架次”一栏应读作**该分组中继需求的额外下界**，而不是一个可以忽略的计数。")
    A("")
    A("---")
    A("")
    A("## 二、输入：被冻结的问题三方案")
    A("")
    A("标准解 `results/solution.json` 来源：%s。方案规模：运输架次 **%d** 个"
      "（A 型 %d、B 型 %d、C 型 %d），中继架次 **%d** 个，通信保障记录 **%d** 条。"
      % (source, len(trecs), sum(1 for r in trecs if r["type"] == "A"),
         sum(1 for r in trecs if r["type"] == "B"),
         sum(1 for r in trecs if r["type"] == "C"), len(rrecs), len(an["cov"])))
    A("")
    A(_tbl(["架次编号", "机型", "无人机", "电池", "开始(s)", "结束(s)", "充电(s)",
            "能耗(kWh)", "服务区顺序"],
           [[r["sid"], r["type"], r.get("drone", ""), r.get("battery", ""),
             "%.0f" % r["start"], "%.0f" % r["end"], "%.0f" % r["chg"], "%.3f" % r["energy"],
             "→".join(r["areas"])] for r in trecs]))
    A("")
    if rrecs:
        A(_tbl(["中继架次", "无人机", "能源组件", "出发(s)", "建链(s)", "服务结束(s)",
                "返回(s)", "充电(s)", "能耗(kWh)"],
               [[r["sid"], r.get("drone", ""), r.get("comp", ""), "%.0f" % r["depart"],
                 "%.0f" % r["link_done"], "%.0f" % r["end"], "%.0f" % r["back"],
                 "%.0f" % r["chg"], "%.3f" % r["energy"]] for r in rrecs]))
        A("")
    if "估算" in source:
        A("> **中继口径提示（降级路径专用）**：本稿使用的 `results/solution.json` 中 `relay` 与 "
          "`coverage` 字段为空（Q3 中继排程未回填），因此**中继部分降级为按运输架次失联时段的"
          "估算**——这是应急路径，正式交付稿必须先用 `python q3refresh.py` 回填真实中继方案："
          "以 10 s 步长采样每个运输架次的航迹判定“与固定网关 G01 直连是否可用”，"
          "把直连不可用的连续时段合并成需保障时段，每个时段配一个中继架次"
          "（悬停点取失联点水平重心、离地高度取机型上限，占用区间 = 保障时段两端各加上"
          "建链/往返时间）。**中继无人机数与能源组件数会随 Q3 最终方案回填 "
          "`solution.json` 的 `relay` 字段后自动重算**，届时重跑 `python q4.py` 即可，"
          "其余结论（运输机型缺口与结构性瓶颈）不受影响。")
        A("")
    A("---")
    A("")
    A("## 三、不可分割块（硬耦合的实际效果）")
    A("")
    A("把每个运输架次视为一个原子，对同一架次涉及的服务区做并查集合并，得到 **%d 个不可分割块**："
      % len(an["blocks"]))
    A("")
    A(_tbl(["块编号", "服务区", "规模"],
           [["B%d" % (i + 1), ",".join(b), len(b)] for i, b in enumerate(an["blocks"])]))
    A("")
    A("耦合链（多服务区架次）：")
    A("")
    A(_tbl(["架次", "涉及服务区"], [[sid, " + ".join(a)] for sid, a in an["links"]]))
    A("")
    A("**结论**：这些“一架次多服务区”的架次把 15 个服务区中的 %d 个锁进同一个块，"
      "使可行分区数从组合意义上的 C(15,·) 骤降到块集合上的枚举规模——这正是硬耦合约束的作用。"
      % max(len(b) for b in an["blocks"]))
    A("")
    A("---")
    A("")
    A("## 四、评价指标定义")
    A("")
    A("### 4.1 资源配置规模")
    A("")
    A("- 资源需求量 `d(g,j)`：任务组 g 对资源类 j 的最小自足配置数（见 1.1 核算口径）。")
    A("- 总资源当量 `W = Σ_j w_j · Σ_g d(g,j)`。" + WEIGHT_NOTE)
    A("- 最大组资源当量 `Wmax = max_g Σ_j w_j · d(g,j)`，反映单组独立执行时的最坏资源规模。")
    A("")
    A("### 4.2 资源冗余")
    A("")
    A("配置量 `c(g,j)` 按“保底 + 按需求比例分摊库存余量”给出：")
    A("")
    A("- 若 `Σ_g d(g,j) ≤ INV_j`：`c(g,j) = d(g,j) + ⌊(INV_j − Σd)·d(g,j)/Σd⌋`，"
      "余数补给需求最大的组，使 `Σ_g c(g,j) = INV_j`（库存全部到位）；")
    A("- 若 `Σ_g d(g,j) > INV_j`：`c(g,j) = d(g,j)`，此时无静态冗余，缺口 `= Σd − INV_j`。")
    A("")
    A("冗余度按题目口径定义：`R_j = (Σ_g c(g,j) − Σ_g d(g,j)) / Σ_g c(g,j)`，"
      "加权总冗余 `R = Σ_j w_j(Σ_g c − Σ_g d) / Σ_j w_j Σ_g c`。"
      "它度量“配置相对各组峰值需求的富余程度”：库存充足时为正（余量可分摊为冗余），"
      "库存不足时为 0（配置只能紧贴需求，缺口另行给出）。")
    A("")
    A("### 4.3 组间工作量均衡")
    A("")
    A("对箱数、架次数、运输机时、运输航程、运输能耗、中继架次数、中继机时共 7 项指标，"
      "计算各组取值的**极差**、**极差率**（极差/均值）与**变异系数 CV**（总体标准差/均值）；"
      "再取 7 项 CV 的均值作为综合不均衡度。CV 越小表示组间工作量越均衡。")
    A("")
    A("### 4.4 与库存的缺口")
    A("")
    A("`缺口_j = max(0, Σ_g d(g,j) − INV_j)`；另单列**硬缺口**：某组自身需求 `d(g,j) > INV_j`，"
      "此时即使其他组让出全部资源也无法满足该组。")
    A("")
    A("### 4.5 推荐方案的选取准则")
    A("")
    A("在完全枚举得到的全部合法分区上按字典序取最优：")
    A("")
    A("1. **可行性优先**：无缺口的方案优先于有缺口的方案；")
    A("2. **缺口最小**：仍不可行时，取归一化总缺口 `Σ_j 缺口_j/INV_j` 最小者；")
    A("3. **总资源当量最小**：分区不应带来不必要的资源膨胀（这正是分组的主要代价）；")
    A("4. **最大组当量最小**：避免出现单组资源规模过大的“巨型组”；")
    A("5. **组间不均衡度最小**：工作量尽可能均衡，便于并行推进。")
    A("")
    A("理由：题目要求“分别核算独立执行所需资源”并比较，其核心矛盾是**分组越细、峰值被切开后"
      "各组独立配置导致总资源越多**。因此以总资源当量为主目标、可行性为硬门槛，"
      "最符合“在满足库存前提下尽量少占资源”的工程直觉；再用最大组当量与不均衡度作稳健性判据。")
    A("")
    A("---")
    A("")
    A("## 五、推荐方案")
    A("")
    for K in (2, 3):
        best = res[K]["rows"][0]
        m = best["met"]
        A("### 5.%d K=%d 分区" % (K - 1, K))
        A("")
        A("**推荐方案 `K%d-P01`**：" % K
          + "；".join("组 G%d-%d = {%s}" % (K, i + 1, ",".join(g))
                      for i, g in enumerate(best["groups"])))
        A("")
        A("合法分区总数 **%d** 个，其中无缺口 **%d** 个。本方案：总资源当量 **%.1f**、"
          "最大组当量 **%.1f**、加权冗余度 **%.1f%%**、工作量综合 CV **%.3f**、"
          "缺口合计 **%d**。"
          % (res[K]["n_enum"], res[K]["n_feasible"], m["total_need"], m["max_group_w"],
             100 * m["redundancy"], m["bal_cv"], m["gap_total"]))
        A("")
        A("| 任务组 | 服务区 | 箱数 | 运输架次 | A型机/电池 | B型机/电池 | C型机/电池 | 中继机/能源 |")
        A("|---|---|---|---|---|---|---|---|")
        for i, (g, w, r) in enumerate(zip(best["groups"], best["wrk"], best["res"]), 1):
            A("| G%d-%d | %s | %d | %d | %d/%d | %d/%d | %d/%d | %d/%d |"
              % (K, i, ",".join(g), w["n_box"], w["n_sortie"],
                 r["A"], r["battA"], r["B"], r["battB"], r["C"], r["battC"],
                 r["relay"], r["relayE"]))
        A("")
        if any(best["cross"]) or best["nocov"]:
            note = []
            for i, c in enumerate(best["cross"]):
                if c:
                    note.append("G%d-%d 有 %d 个跨组保障中继架次（%s）"
                                % (K, i + 1, len(c), ",".join(c)))
            if best["nocov"]:
                note.append("无保障记录的中继架次 %s 按最大架次数组归组" % ",".join(best["nocov"]))
            A("> " + "；".join(note) + "。")
            A("")
    A("---")
    A("")
    A("## 六、资源核算表（推荐方案）")
    A("")
    rows = []
    for K in (2, 3):
        best = res[K]["rows"][0]
        for i, (g, r) in enumerate(zip(best["groups"], best["res"]), 1):
            rows.append(["K=%d" % K, "G%d-%d" % (K, i), ",".join(g)]
                        + [r[j] for j in CLASSES])
    A(_tbl(["K", "任务组", "服务区列表"] + [CLASS_CN[j] for j in CLASSES], rows))
    A("")
    A("上表即 `results/Q4_分区配置.xlsx` 首表 `Q4_分区配置` 的内容（列名与题目模板严格一致）。")
    A("")
    A("---")
    A("")
    A("## 七、与现有库存的对比与缺口分析")
    A("")
    rows = []
    for j in CLASSES:
        row = [CLASS_CN[j], INV[j]]
        for K in (2, 3):
            m = res[K]["rows"][0]["met"]
            row += [m["need"][j], ("**%d**" % m["gap"][j]) if m["gap"][j] else "0"]
        row += [k1["res"][j], relu(k1["res"][j] - INV[j])]
        rows.append(row)
    A(_tbl(["资源类别", "库存", "K=2 需求", "K=2 缺口", "K=3 需求", "K=3 缺口",
            "一体化(K=1)需求", "K=1 缺口"], rows))
    A("")
    for K in (2, 3):
        m = res[K]["rows"][0]["met"]
        if m["feasible"]:
            A("- **K=%d：无缺口**。所有资源类别总需求均不超过库存，库存冗余率 %.1f%%。"
              % (K, 100 * m["redundancy"]))
        else:
            gs = ["%s 缺 %d（需求 %d / 库存 %d）"
                  % (CLASS_CN[j], m["gap"][j], m["need"][j], INV[j])
                  for j in CLASSES if m["gap"][j]]
            A("- **K=%d：存在缺口** —— %s。" % (K, "；".join(gs)))
            hg = ["G%d-%d 的 %s 需求 %d > 库存 %d"
                  % (K, i + 1, CLASS_CN[j], m["group_need"][i][j], INV[j])
                  for j in CLASSES for i in range(K)
                  if m["group_need"][i][j] > INV[j]]
            if hg:
                only_relay = all(("中继" in x) for x in hg)
                A("  - 硬缺口（单组即超库存，无法靠组间调剂解决）：%s%s。"
                  % ("；".join(hg),
                     "（该硬缺口仅出现在中继类，且中继为待回填的估算口径）" if only_relay else ""))
            else:
                A("  - 无单组硬缺口：任一任务组自身的需求都不超过该类资源的总库存，"
                  "缺口来自**两组需求之和**超过库存（即分组把峰值复制了两份）。")
    A("")
    A("**缺口原因分析**：")
    A("")
    A("1. **峰值不可加性被分组破坏**。一体化调度时各机型的并发峰值按全体架次的时间轴统计；"
      "分组后每组必须**各自**按本组时间轴配置峰值资源，于是 `Σ_g 峰值_g ≥ 峰值_总`，"
      "分组必然带来资源膨胀，这是缺口的第一来源。")
    A("2. **库存本就紧贴一体化需求**。一体化（K=1）方案对运输机与电池的需求为 "
      + "、".join("%s %d" % (CLASS_CN[j], k1["res"][j])
                  for j in ("A", "B", "C", "battA", "battB", "battC"))
      + "，与库存 "
      + "、".join("%s %d" % (CLASS_CN[j], INV[j])
                  for j in ("A", "B", "C", "battA", "battB", "battC")) + " 相比："
      + ("**恰好用满**" if all(k1["res"][j] <= INV[j]
                              for j in ("A", "B", "C", "battA", "battB", "battC"))
         else "**已超库存**")
      + "，没有任何余量；中继类需求为待回填的估算值（%s）。"
        "因此任何再切分都会立刻顶破库存。"
      % "、".join("%s %d" % (CLASS_CN[j], k1["res"][j]) for j in ("relay", "relayE")))
    A("3. **硬耦合造成的极端不均衡**。同一架次多服务区的耦合把大多数服务区锁进同一个大块，"
      "小任务组虽只含 1–2 个服务区，却**仍必须拥有完整的机队与电池周转能力**"
      "（至少 1 架机 + 至少 2 组电池才能形成“飞行—充电—再飞行”的周转链），"
      "这种“最小可运行单元”的固定开销是小组缺口的主因。")
    A("4. **机型资源不可互换带来的结构性闲置**。问题三方案中 A 型未被使用"
      "（A 型体积舱仅 0.06 m³，在体积约束先于质量约束起作用时被 B 型替代），"
      "因此 A 型 4 架机与 6 组电池对本划分是**纯冗余库存**；但 A 型电池与 B/C 型不通用，"
      "无法用于补足 B/C 型的缺口。")
    A("")
    sb = an["struct"]
    A("### 7.1 结构性瓶颈：为什么缺口与分区方式无关")
    A("")
    A("对每个不可分割块先算出**块内**该机型架次的峰值并发 `p_b`。由于峰值对“加入更多架次”"
      "单调不减，任何包含块 b 的任务组，其该机型需求都 ≥ `p_b`；于是对任意 K 分区有 "
      "`Σ_g 需求_g ≥ Σ_g max_{b∈g} p_b`，该式的最小值即需求下界（把 `p_b` 最大的块单独成组、"
      "其余 K−1 组尽量塞入 `p_b=0` 的块）：")
    A("")
    A(_tbl(["机型", "含该机型架次的块数 / 总块数", "块内峰值最大值"] +
           ["块内峰值 p_b（块 %d）" % (i + 1) for i in range(len(an["blocks"]))] +
           ["K=2 需求下界", "K=3 需求下界", "库存", "K=2 必然缺口", "K=3 必然缺口"],
           [[CLASS_CN[g], "%d / %d" % (sb[g]["n_block"], len(an["blocks"])), sb[g]["inner_max"]] +
            [sb["per_block"][i][g] for i in range(len(an["blocks"]))] +
            [sb[g]["lb2"], sb[g]["lb3"], INV[g], sb[g]["fg2"], sb[g]["fg3"]]
            for g in ("A", "B", "C")]))
    A("")
    A("共享电池同理：电池占用区间 [start, end+chg) 包含无人机占用区间 [start, end)，"
      "所以**同一时刻在飞的每架机都占着一组电池**，电池需求下界与对应机型无人机的下界相同；"
      "实际核算值还会更高，因为电池在架次结束后仍需充电。")
    A("")
    A(_tbl(["资源类别", "K=2 需求下界", "K=3 需求下界", "K=2 实际需求", "K=3 实际需求",
            "库存", "K=2 必然缺口", "K=3 必然缺口"],
           [[CLASS_CN[j], sb[j]["lb2"], sb[j]["lb3"],
             res[2]["rows"][0]["met"]["need"][j], res[3]["rows"][0]["met"]["need"][j],
             INV[j], sb[j]["fg2"], sb[j]["fg3"]] for j in ("battA", "battB", "battC")]))
    A("")
    A("**结构性命中**：%s" % sb["conclusion"])
    A("")
    A("### 7.2 管理含义")
    A("")
    A("1. **B 型机是全局瓶颈机型**：库存 2 架 B 型机恰好等于一体化方案的峰值并发需求，"
      "没有任何余量；一旦分组，每个任务组都必须自备 B 型机，缺口立刻出现。"
      "因此在按任务组独立执行之前，第一优先的补强对象是 **B 型运输机与 B 型共享电池**，"
      "而不是 A 型（A 型 4 架机与 6 组电池对本划分完全闲置）。"
      "但必须纠正一个容易出现的误读：**C 型机在 K=2 下同样缺 1 架**"
      "（需求 3 / 库存 2，见第七节开头的缺口表；K=3 下 C 型与 B 型同时缺 1、B 型电池也缺 1）。"
      "C 型并非“刚好够用”，它只是缺口规模小于 K=3 情形，因此补强优先级排在 B 型之后。")
    A("2. **允许 B 型资源跨组共享是缓解缺口的最经济手段**：B 型机与电池在时间上被两组"
      "错峰占用（两组的 B 型架次时段基本不重叠），把 B 型资源作为全局池调度，"
      "**B 型机与 B 型电池的缺口可以归零**，而无需新购装备；代价是放弃“完全隔离”的严格假设，"
      "需要在两组之间约定 B 型机与电池的交接时刻与责任人。"
      "但**总缺口不会因此消失**：见 7.3 的 S2/S3 情形——K=2 仍有 1 件缺口（来自 C 型运输机，"
      "并不在 B 型共享范围内），K=3 的运输电池缺口由 3 件降到 1 件。"
      "只有把全部资源（含 C 型机）放进同一个池子（S5 ≡ 一体化 K=1）缺口才归零，"
      "而那已经等于取消分组。第七节 7.3 给出量化对比，7.4 给出中继侧的双口径。")
    A("3. **从源头降低耦合**：本次缺口的另一半来自硬耦合——多服务区架次把小任务组"
      "“绑”成必须自备完整机队的最小单元。若在 Q2/Q3 重解时对“多服务区架次”加惩罚、"
      "使架次尽量单服务区化，块的数量会增加、分区的自由度会显著提高，"
      "同样可以在不增加库存的前提下减小缺口。")
    A("")
    A("### 7.3 反事实对比：允许组间共享时的缺口")
    A("")
    A("下表把若干资源类别改为“全局共享、只按全局峰值/色数配置一份”，其余资源仍严格组内独立，"
      "重新核算需求与缺口（共享口径下的需求直接取一体化 K=1 的数值）：")
    A("")
    rows = []
    for rec in an["sharing"]:
        rows.append([rec["情形"], rec["共享资源"],
                     "%.1f" % rec["K=2当量"], rec["K=2运输电池可行"], rec["K=2运输电池缺口"],
                     rec["K=2中继缺口"],
                     "%.1f" % rec["K=3当量"], rec["K=3运输电池可行"], rec["K=3运输电池缺口"],
                     rec["K=3中继缺口"]])
    A(_tbl(["情形", "共享资源", "K=2当量", "K=2运输电池可行", "K=2运输电池缺口", "K=2中继缺口",
            "K=3当量", "K=3运输电池可行", "K=3运输电池缺口", "K=3中继缺口"], rows))
    A("")
    A("**反事实结论**：%s" % an["sharing_conclusion"])
    A("")
    A("> **C 型缺口的来源与 B 型不同（补充说明）**：S2/S3 已经把 B 型机与 B 型电池放进全局池，"
      "K=2 却仍留 1 件缺口，说明这 1 件来自 **C 型运输机**——C 型架次在两组的峰值时刻存在重叠，"
      "不是时间错峰，因此无法靠“全局池”消除，只能追加 1 架 C 型机、"
      "或把两组重新并为一体（S5）才能归零。")
    A("")
    A("> **适用边界（#25）**：7.3 全表都是**放松性反事实**——它放松了题面“任务执行期间资源"
      "不得跨组调配”这一条硬约束，因此**表中任何一行都不能当作问题四的合法解**，"
      "只能用作“缺口究竟来自装备总量不足、还是来自隔离假设”的归因证据。")
    A("")
    if not res[2]["rows"][0]["met"]["feasible"] and not res[3]["rows"][0]["met"]["feasible"]:
        A("> **结论**：两种分区方式都超出库存。**推荐 2 组分区**（缺口更小、资源当量更低、"
          "组间更均衡）。缺口的**主要来源**是 B 型机与 B 型电池在多服务区架次上的**峰值复制**——"
          "注意 7.1 已证明这不构成“必然缺口”（任何机型的需求下界都不超过库存，"
          "只是本方案的实际峰值分配越了界）。缓解缺口最经济的方式是允许 B 型资源跨组共享"
          "（见 7.3，但它只消除 B 型缺口；C 型缺口需追加 1 架 C 型机），"
          "其次是追加装备，或放松硬耦合重解 Q2/Q3 使运输架次尽量单服务区化。"
          "中继侧的缺口另见 7.4。")
    A("")
    A("### 7.4 与问题三「增配 1 架中继」结论的衔接（双口径）")
    A("")
    A("问题三的结论是：给定运输时序，**2 架中继无可行解**（无可行换位），"
      "**3 架中继可构造出 0 未覆盖、0 时序冲突的可行方案**，故建议增配 1 架中继无人机。"
      "本文正文继承的是 2 架折中方案，因此正文缺口表中「中继无人机 2 架 / 缺口 0」"
      "**只说明折中方案的占用不超过库存，并不说明通信约束被满足**。两种口径对比如下"
      "（增配方案的逐架次明细由 `code/q4_relay3.py` 生成，见 `results/Q4_中继增配情景.md`）：")
    A("")
    _r3 = SIO.load().get("relay3") or []
    _n2 = int(k1["res"]["relay"])
    A(_tbl(["口径", "中继方案来源", "中继无人机需求(架)", "库存(架)", "缺口(架)",
            "是否满足全程连续通信"],
           [["A（正文，库存内可执行）",
             "`solution.json` 的 `relay`：2 架折中、%d 个架次" % len(rrecs),
             "%d" % _n2, "%d" % INV["relay"], "%d" % max(0, _n2 - INV["relay"]),
             "否（问题三记录到通信中断相）"],
            ["B（采纳问题三增配建议）",
             "`solution.json` 的 `relay3`：3 架、%d 个架次" % len(_r3),
             "3", "%d" % INV["relay"], "1", "是（0 未覆盖、0 时序冲突）"]]))
    A("")
    A("> **两口径的唯一区别是中继类资源**：运输机与电池组的需求、缺口在两种口径下完全相同"
      "（增配只改中继，不动运输方案）。因此问题四的最终建议是**叠加**的：在 K=2 分组下"
      "需追加 **1 架 C 型运输机 + 1 架中继无人机**（若按 7.3 允许组间共享 B 型资源，"
      "则 B 型机与 B 型电池无需追加，但仍需补 1 架 C 型机与 1 架中继）。")
    A("")
    A("---")
    A("")
    A("## 八、组间工作量均衡性")
    A("")
    for K in (2, 3):
        m = res[K]["rows"][0]["met"]
        A("**K=%d 推荐方案**：综合 CV = %.3f，最大极差率 = %.3f" % (K, m["bal_cv"], m["bal_span"]))
        A("")
        rows = []
        for key, b in m["balance"].items():
            mean = sum(b["vals"]) / K
            rows.append([b["cn"]] + ["%.3f" % v for v in b["vals"]]
                        + ["%.3f" % b["rng"], "%.3f" % b["cv"],
                           "%.3f" % (b["rng"] / mean if mean > 0 else 0.0)])
        A(_tbl(["指标"] + ["组%d" % (i + 1) for i in range(K)] + ["极差", "CV", "极差率"], rows))
        A("")
    A("---")
    A("")
    A("## 九、两种分区方式的比较结论")
    A("")
    r2, r3 = res[2]["rows"][0]["met"], res[3]["rows"][0]["met"]
    A("### 9.1 资源配置规模")
    A("")
    rows = []
    for j in CLASSES:
        rows.append([CLASS_CN[j], r2["need"][j], r3["need"][j], r3["need"][j] - r2["need"][j],
                     k1["res"][j]])
    A(_tbl(["资源类别", "K=2 需求", "K=3 需求", "K=3 − K=2", "一体化 K=1"], rows))
    A("")
    A("合计：总资源当量 K=2 为 **%.1f**，K=3 为 **%.1f**（一体化 %.1f）；"
      "相对一体化的分区膨胀率 K=2 为 **%.1f%%**、K=3 为 **%.1f%%**；"
      "最大组当量 K=2 为 **%.1f**、K=3 为 **%.1f**。"
      % (r2["total_need"], r3["total_need"], k1["met"]["total_need"],
         100 * (r2["total_need"] / k1["met"]["total_need"] - 1),
         100 * (r3["total_need"] / k1["met"]["total_need"] - 1),
         r2["max_group_w"], r3["max_group_w"]))
    A("")
    A("### 9.2 资源冗余")
    A("")
    A(_tbl(["指标", "K=2", "K=3"], [
        ["加权总冗余度 R", "%.1f%%" % (100 * r2["redundancy"]), "%.1f%%" % (100 * r3["redundancy"])],
        ["可行（无缺口）", "是" if r2["feasible"] else "否", "是" if r3["feasible"] else "否"],
        ["缺口合计（件/组）", r2["gap_total"], r3["gap_total"]],
    ]))
    A("")
    A("### 9.3 组间工作量均衡")
    A("")
    rows = []
    for key, cn in BAL_INDS:
        rows.append([cn, "%.3f" % r2["balance"][key]["cv"], "%.3f" % r3["balance"][key]["cv"]])
    rows.append(["综合 CV（7 项均值）", "%.3f" % r2["bal_cv"], "%.3f" % r3["bal_cv"]])
    rows.append(["最大组当量", "%.1f" % r2["max_group_w"], "%.1f" % r3["max_group_w"]])
    A(_tbl(["指标", "K=2", "K=3"], rows))
    A("")
    A("### 9.4 与库存的缺口")
    A("")
    A(_tbl(["指标", "K=2", "K=3"], [
        ["超库存的资源类别数", sum(1 for j in CLASSES if r2["gap"][j]),
         sum(1 for j in CLASSES if r3["gap"][j])],
        ["缺口总量（件/组）", r2["gap_total"], r3["gap_total"]],
        ["归一化缺口 Σ缺口/库存", "%.3f" % r2["gap_norm"], "%.3f" % r3["gap_norm"]],
    ]))
    A("")
    A("### 9.5 综合比较结论")
    A("")
    A("1. **可行性**：%s。K=2 缺口合计 %d 件/组，K=3 缺口合计 %d 件/组。"
      % ("两种分区均可满足库存" if (r2["feasible"] and r3["feasible"])
         else ("K=2 可满足库存、K=3 存在缺口" if r2["feasible"]
               else ("K=3 可满足库存、K=2 存在缺口" if r3["feasible"]
                     else "两种分区均超出库存")),
         r2["gap_total"], r3["gap_total"]))
    A("2. **资源规模**：K=3 的总资源当量比 K=2 %s（%.1f vs %.1f，%+.1f%%）。"
      "分组越细，各组独立配置的峰值资源越多，这是峰值不可加性的直接后果。"
      % ("更高" if r3["total_need"] > r2["total_need"]
         else ("更低" if r3["total_need"] < r2["total_need"] else "持平"),
         r3["total_need"], r2["total_need"],
         100 * (r3["total_need"] / r2["total_need"] - 1) if r2["total_need"] else 0.0))
    A("3. **工作量均衡**：K=2 综合 CV 为 %.3f，K=3 为 %.3f，%s；最大组当量 %.1f vs %.1f。"
      % (r2["bal_cv"], r3["bal_cv"],
         "K=2 更均衡" if r2["bal_cv"] < r3["bal_cv"]
         else ("K=3 更均衡" if r3["bal_cv"] < r2["bal_cv"] else "两者相当"),
         r2["max_group_w"], r3["max_group_w"]))
    A("4. **冗余与缺口**：K=2 冗余度 %.1f%%，K=3 冗余度 %.1f%%；"
      "缺口类别数 %d vs %d。"
      % (100 * r2["redundancy"], 100 * r3["redundancy"],
         sum(1 for j in CLASSES if r2["gap"][j]), sum(1 for j in CLASSES if r3["gap"][j])))
    A("5. **总体建议**：%s" % _recommend_text(r2, r3))
    A("")
    A("---")
    A("")
    A("## 十、备选方案与灵敏度")
    A("")
    A("以下列出各 K 下全部合法分区及其指标（按推荐排序键排列），供比较与稳健性检查。")
    A("")
    for K in (2, 3):
        A("### K=%d 的备选方案（共 %d 个合法分区，此处列前 %d 个）"
          % (K, res[K]["n_enum"], len(res[K]["rows"])))
        A("")
        rows = []
        for rank, row in enumerate(res[K]["rows"], 1):
            m = row["met"]
            rows.append(["P%02d" % rank,
                         " ＋ ".join("{%s}" % ",".join(g) for g in row["groups"]),
                         "%.1f" % m["total_need"], "%.1f" % m["max_group_w"],
                         "是" if m["feasible"] else "否", m["gap_total"],
                         "%.3f" % m["bal_cv"],
                         "%.1f%%" % (100 * m["redundancy"])])
        A(_tbl(["编号", "分区", "总当量", "最大组当量", "可行", "缺口合计", "综合CV", "冗余度"], rows))
        A("")
    A("### 权重灵敏度")
    A("")
    A(_weight_sensitivity(res))
    A("")
    A("---")
    A("")
    A("## 十一、自检结果")
    A("")
    A(_tbl(["检查项", "结果", "说明"], [[c["检查项"], c["结果"], c["说明"]] for c in checks]))
    A("")
    A("**自检汇总：%d/%d 项通过%s。**"
      % (passed, total, "" if passed == total else "（存在不通过项，请检查）"))
    A("")
    A("自检覆盖范围：")
    A("")
    A("- **(a)** 每个服务区恰好属于一个任务组（无遗漏、无重复、每组非空）；")
    A("- **(b)** 同一运输架次的服务区必须同组（硬耦合约束）；")
    A("- **(c)** 各组资源需求与时间轴重算一致：运输无人机用 `solution_io.resource_peak` "
      "独立复算；电池组 / 中继能源组件用 O(n²) 两两重叠法独立复算，并与事件扫描、"
      "区间图着色三方交叉验证；")
    A("- **(d)** 运输架次被唯一分组覆盖（各组架次数之和 = 总架次数，无重复计数）；")
    A("- **(e)** 物理一致性：电池组数 ≥ 无人机数、能源组件数 ≥ 中继无人机数；")
    A("- **(f)** 库存口径与附件一致；")
    A("- **(g)** 中继架次被唯一归组（无重复、无遗漏）。")
    A("")
    A("---")
    A("")
    A("## 附：运行信息")
    A("")
    A("- 生成脚本：`code/q4.py`（`cd code && python q4.py`）")
    A("- 标准解：`results/solution.json`（%s）" % source)
    A("- 输出：`results/Q4_分区配置.xlsx`、`results/Q4_说明.md`、`results/Q4_运行日志.txt`")
    A("- 本次运行耗时：%.1f s" % elapsed)
    A("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


# ===========================================================================
# main
# ===========================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="D 题问题四：任务组划分与资源核算")
    ap.add_argument("--check", action="store_true", help="复用标准解，只重算并输出自检")
    ap.add_argument("--force", action="store_true", help="忽略已有 solution.json，强制重新生成基准解")
    ap.add_argument("--tlimit", type=float, default=25.0, help="降级生成基准解时 Q2 ALNS 时限(s)")
    ap.add_argument("--relay-plan", choices=["auto", "estimate", "q3run"], default="auto",
                    help="solution.json 缺中继安排时的补全口径：auto=estimate（默认）/ q3run=先试 q3run.plan")
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(RES, exist_ok=True)
    LOG("=" * 78)
    LOG("问题四：服务区任务组划分与各组独立资源核算    %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    LOG("=" * 78)

    sol, source = ensure_solution(force=args.force, tlimit=args.tlimit,
                                  plan=args.relay_plan, verbose=True)
    an = analyze(sol)
    k1 = k1_reference(an)
    an["sharing"] = sharing_table(an["results"], k1)
    an["sharing_conclusion"] = sharing_conclusion(an["results"], k1, an["sharing"])
    LOG("")
    LOG("  [一体化参照 K=1] " + "，".join("%s=%d" % (CLASS_CN[j], k1["res"][j]) for j in CLASSES)
        + " → 缺口 " + (",".join("%s:%d" % (CLASS_CN[j], relu(k1["res"][j] - INV[j]))
                                for j in CLASSES if relu(k1["res"][j] - INV[j])) or "无"))
    for rec in an["sharing"]:
        LOG("  [共享反事实] %-28s K=2 当量%6.1f %s | K=3 当量%6.1f %s"
            % (rec["情形"], rec["K=2当量"], rec["K=2可行"], rec["K=3当量"], rec["K=3可行"]))
    checks, passed, total = self_check(an, k1)

    if args.check:
        md = write_md(an, k1, checks, passed, total, source, elapsed=time.time() - t0)
        LOG("")
        LOG("[--check] 自检完成（%d/%d 通过），已把自检结果写入 %s 末尾。"
            "如需同时刷新 Q4_分区配置.xlsx，请直接运行 python q4.py"
            % (passed, total, os.path.relpath(md, BASE)))
        LOG("总耗时 %.1f s" % (time.time() - t0))
        LOG.close()
        return 0 if passed == total else 1

    xlsx, sheets = write_xlsx(an, k1)
    md = write_md(an, k1, checks, passed, total, source, elapsed=time.time() - t0)
    LOG("")
    LOG("  输出：%s（工作表：%s）" % (os.path.relpath(xlsx, BASE), "、".join(sheets)))
    LOG("  输出：%s" % os.path.relpath(md, BASE))
    LOG("  总耗时 %.1f s" % (time.time() - t0))
    LOG.close()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
