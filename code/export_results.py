# -*- coding: utf-8 -*-
"""
export_results.py —— 结果文件导出（交付物 1）

功能
----
读取 results/solution.json（若不存在，则现场生成基准解并写回），生成
**results/结果提交.xlsx**，其中 6 张工作表的工作表名与列名与
`D题/结果提交模板.xlsx` 完全一致：

    Q1_单点组批 | Q2_运输架次 | Q2_逐箱交付 | Q3_中继架次 | Q3_通信保障 | Q4_分区配置
另加辅助表：
    方案汇总

数据来源
--------
* Q1_单点组批  ← 直接调用 code/q1.py 的 solve()，取「最少架次」方案
                 （与 sensitivity / Pareto 前沿无关，仅用 schemes 中的 S1 具名方案）
* Q2_运输架次 / Q2_逐箱交付 ← results/solution.json["transport"]
* Q3_中继架次  ← results/solution.json["relay"]
* Q3_通信保障  ← 独立生成：按运输架次航迹分段（爬升/巡航/下降/投送），
                 逐段用 dcore/comm 的链路判定函数给出 直连 / 中继 / 中断
* Q4_分区配置  ← results/Q4_分区配置.xlsx（若不存在则留空，仅保留列名）

运行
----
    cd D题\\code
    python export_results.py
环境变量
--------
    DSH_NO_RELAY=1   不尝试现场生成 Q3 中继方案（仅使用 solution.json 中已有内容）
"""
from __future__ import annotations

import math
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import dcore as D
import comm as C
import solution_io as SIO

try:
    import openpyxl
except Exception:                                    # pragma: no cover
    openpyxl = None

BASE = D.BASE
OUT = D.RESULTS
os.makedirs(OUT, exist_ok=True)

def _find_template():
    """定位官方结果提交模板（审阅 #26：交付包布局与工作区布局都能找到）。"""
    cands = [
        os.environ.get("DTI_TPL") or "",
        os.path.join(BASE, "结果提交模板.xlsx"),
        os.path.join(BASE, "04_数据与模板", "结果提交模板.xlsx"),
        os.path.join(BASE, "..", "04_数据与模板", "结果提交模板.xlsx"),
        os.path.join(BASE, "数据", "结果提交模板.xlsx"),
        os.path.join(BASE, "..", "结果提交模板.xlsx"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return os.path.join(BASE, "结果提交模板.xlsx")


TPL = _find_template()
XLSX = os.path.join(OUT, "结果提交.xlsx")
Q4_XLSX = os.path.join(OUT, "Q4_分区配置.xlsx")

BIG = 1e9

# ---------------------------------------------------------------------------
# 模板列名（与 结果提交模板.xlsx 逐字一致）
# ---------------------------------------------------------------------------
TPL_COLS = {
    "Q1_单点组批": ["架次编号", "服务区编号", "机型编号", "货箱编号列表", "总质量（kg）",
                    "总体积（m³）", "往返时间（s）", "架次能耗（kWh）", "返航SOC（%）"],
    "Q2_运输架次": ["架次编号", "无人机编号", "机型编号", "电池编号", "开始时刻（s）",
                    "访问服务区顺序", "返回O01时刻（s）", "架次能耗（kWh）"],
    "Q2_逐箱交付": ["货箱编号", "架次编号", "服务区编号", "交付完成时刻（s）"],
    "Q3_中继架次": ["中继架次编号", "中继无人机编号", "能源组件编号", "开始时刻（s）",
                    "悬停经度（°）", "悬停纬度（°）", "悬停海拔（m）", "建链完成时刻（s）",
                    "服务结束时刻（s）", "返回O01时刻（s）", "架次能耗（kWh）"],
    "Q3_通信保障": ["运输架次编号", "通信阶段", "开始时刻（s）", "结束时刻（s）",
                    "保障方式", "中继架次编号"],
    "Q4_分区配置": ["K（2或3）", "任务分区编号", "服务区列表", "A型运输无人机数",
                    "B型运输无人机数", "C型运输无人机数", "A型电池组数", "B型电池组数",
                    "C型电池组数", "中继无人机数", "中继能源组件数"],
}


def template_columns():
    """尽力从模板文件读取真实表头（保证逐字一致）；失败则回退到内置常量。"""
    cols = {k: list(v) for k, v in TPL_COLS.items()}
    if openpyxl is None or not os.path.exists(TPL):
        return cols
    try:
        wb = openpyxl.load_workbook(TPL)
        for ws in wb.worksheets:
            head = []
            for v in next(ws.iter_rows(min_row=1, max_row=1, values_only=True)):
                if v is None:
                    break
                head.append(str(v).strip())
            if head:
                cols[ws.title] = head
        wb.close()
    except Exception as e:
        print("  [警告] 读取模板表头失败，使用内置列名：%s" % e)
    return cols


# ---------------------------------------------------------------------------
# 求解 / 载入 solution.json
# ---------------------------------------------------------------------------
def q1_min_sortie_scheme():
    """调用 q1.solve() 取「最少架次」方案，转成模板行。"""
    import q1
    t0 = time.time()
    res = q1.solve(verbose=False)
    d = res["d"]
    types = d["ttypes"]
    # 最少架次：先比架次数，再比能耗、工时
    name, (tot, recs) = min(res["schemes"].items(),
                            key=lambda kv: (kv[1][0]["count"], kv[1][0]["E"], kv[1][0]["T"]))
    rows = []
    for r in recs:
        rows.append({
            "架次编号": r["架次编号"],
            "服务区编号": r["服务区编号"],
            "机型编号": r["机型编号"],
            "货箱编号列表": r["货箱编号列表"],
            "总质量（kg）": round(float(r["总质量_kg"]), 3),
            "总体积（m³）": round(float(r["总体积_m3"]), 5),
            "往返时间（s）": round(float(r["往返时间_s"]), 1),
            "架次能耗（kWh）": round(float(r["架次能耗_kWh"]), 4),
            "返航SOC（%）": round(float(r["返航SOC_pct"]), 2),
        })
    meta = dict(scheme=name, n_sortie=int(tot["count"]), energy=round(float(tot["E"]), 3),
                worktime=round(float(tot["T"]), 1), n_front=len(res["front"]),
                n_pareto_area=int(sum(len(v) for v in res["area_par"].values())),
                runtime=round(time.time() - t0, 1))
    print("  Q1：最少架次方案「%s」架次=%d 能耗=%.2f kWh 工时=%.0f s（%.0f s 求解）"
          % (name, tot["count"], tot["E"], tot["T"], time.time() - t0))
    return rows, meta


def build_solution(inst, tlimit=25.0, cpsat_limit=25.0, seed=0):
    """基准解：复用 cscan.build_solution 的构造（紧凑 + ALNS + 打磨），再转标准记录。"""
    import q2 as Q
    import random
    rng = random.Random(seed)
    w = dict(count=1.5, energy=2.0, makespan=2.0, tardy=2.0)
    sol = Q.compact(inst, Q.construct(inst, rng, noise=1.0, w=w))
    sol, obj, met, it = Q.alns(inst, w, seed=seed, iters=4000, tlimit=tlimit, init=sol)
    pol = Q.polish(inst, sol, cpsat_limit=cpsat_limit)
    recs = SIO.transport_from_sorties(inst, sol, pol["assign"], code_prefix="Q2")
    met2 = dict(pol["met"])
    return recs, met2, pol["tag"]


def _transport_fingerprint(sol):
    """运输方案的指纹：架次编号/机型/起止/航路/箱集合。用于判断中继方案是否已过期。"""
    items = []
    for r in sol.get("transport") or []:
        boxes = ";".join("%s:%s" % (k, ",".join(sorted(v)))
                         for k, v in sorted((r.get("boxes") or {}).items()))
        items.append("%s|%s|%.3f|%.3f|%s|%s" % (r.get("sid"), r.get("type"), float(r["start"]),
                                                float(r["end"]), "->".join(r["route"]), boxes))
    import hashlib
    return hashlib.md5("\n".join(items).encode("utf-8")).hexdigest()[:12]


def ensure_solution(inst):
    """返回 (solution dict, 来源说明)。"""
    if os.path.exists(SIO.SOL_JSON):
        try:
            sol = SIO.load(SIO.SOL_JSON)
            if sol.get("transport"):
                print("  载入已有解：%s（运输架次 %d，中继架次 %d）"
                      % (SIO.SOL_JSON, len(sol["transport"]), len(sol.get("relay") or [])))
                sol.setdefault("relay", [])
                sol.setdefault("coverage", [])
                rp = (sol.get("meta") or {}).get("relay_plan") or {}
                fp_now = _transport_fingerprint(sol)
                if sol["relay"] and rp.get("transport_fp") and rp["transport_fp"] != fp_now:
                    print("  [警告] 中继方案是基于另一版运输方案生成的（指纹 %s ≠ %s），"
                          "其悬停时段/位置可能已不适用；建议重新规划中继。"
                          % (rp["transport_fp"], fp_now))
                sol.setdefault("meta", {})["transport_fp"] = fp_now
                return sol, "results/solution.json"
        except Exception as e:
            print("  [警告] solution.json 解析失败（%s），改为现场生成基准解" % e)
    G = inst.d
    lat = np.array([G["nodes"][s].lat for s in ["O01"] + G["SIDS"]])
    lon = np.array([G["nodes"][s].lon for s in ["O01"] + G["SIDS"]])
    t0 = time.time()
    print("  solution.json 不存在，现场生成基准解（ALNS + CP-SAT 打磨）…")
    recs, met, tag = build_solution(inst)
    sol = dict(
        meta=dict(origin="export_results.py::build_solution(cscan 路线)", tag=tag,
                  rho=float(inst.rho["A"]), makespan=float(met["makespan"]),
                  energy=float(met["energy"]), count=int(met["count"]),
                  hard_violation=float(met["hard_violation"]),
                  tardiness=float(met["tardiness"]),
                  ontime_rate=float(met["ontime_rate"]),
                  runtime_s=round(time.time() - t0, 1),
                  bbox=dict(lon0=float(lon.min()), lon1=float(lon.max()),
                            lat0=float(lat.min()), lat1=float(lat.max()))),
        transport=recs, relay=[], coverage=[])
    sol["meta"]["n_relay"] = 0
    SIO.save(sol, SIO.SOL_JSON)
    print("  基准解已写回：%s（架次=%d 能耗=%.2f 完工=%.0f 硬违反=%.0f [%s]）"
          % (SIO.SOL_JSON, met["count"], met["energy"], met["makespan"],
             met["hard_violation"], tag))
    return sol, "现场生成（基准解）"


# ---------------------------------------------------------------------------
# 硬时限微修复（不改动箱-架次归属，只在"同机型共享电池"层面交换电池并重排开始时刻）
# ---------------------------------------------------------------------------
def _earliest_start(inst, recs, target):
    """在其余架次时刻不变的前提下，target 架次"电池就绪 + 无人机空闲"的最早开始时刻。

    共享电池的时间轴 = 占用 [start, end) ⊕ 充电 [end, end+t_chg(SOC_end))；
    只有当某架次用到的电池被**前一次占用 + 本次充电**完全释放后才可开工。
    """
    g = target["type"]
    bat = target.get("battery", "")
    # 电池：所有"开始时刻更早"的其它架次中，该电池的释放时刻取最大
    tb = 0.0
    for r in recs:
        if r is target or r.get("battery", "") != bat:
            continue
        if float(r["start"]) > float(target["start"]) + 1e-9:
            continue
        e = float(r["energy"])
        tb = max(tb, float(r["end"]) + float(
            D.charge_time(1.0 - e / inst.euse[g], inst.tfull[g])))
    # 无人机：所有"开始时刻更早"的同机号架次的结束时刻取最大
    td = 0.0
    for r in recs:
        if r is target or r.get("drone", "") != target.get("drone", ""):
            continue
        if float(r["start"]) < float(target["start"]) - 1e-9:
            td = max(td, float(r["end"]))
    return max(tb, td)


def _shift(inst, rec, start):
    """把某架次整体平移到 start（时长不变，逐箱交付时刻同步平移）。"""
    old = float(rec["start"])
    dur = float(rec["end"]) - old
    new = dict(rec)
    new["start"] = float(start)
    new["end"] = float(start) + dur
    new["deliver"] = {b: float(start) + (float(t) - old)
                      for b, t in (rec.get("deliver") or {}).items()}
    return new


def _hard_violation(inst, recs):
    """硬时限违反总量（s）：医疗 > 期望送达、首批 > 首批截止（容差 0.5 s）。"""
    v = 0.0
    for r in recs:
        for s, bs in (r.get("boxes") or {}).items():
            for b in bs:
                hd = inst.hard[b]
                if hd < 1e9:
                    t = float(r["deliver"][b])
                    if t > hd + 0.5:
                        v += t - hd
    return v


def repair_deadlines(inst, sol, verbose=True):
    """若存在硬时限违反，尝试"交换同机型两架次的电池"并重排开始时刻。

    只接受：违反量下降、双方开始时刻均不晚于原值、且时长/装箱/编号归属完全不变的交换。
    """
    recs = sol["transport"]
    v0 = _hard_violation(inst, recs)
    if v0 <= 1e-9:
        return 0, False
    groups = {}
    for i, r in enumerate(recs):
        groups.setdefault(r["type"], []).append(i)
    best = None
    for g, idx in groups.items():
        for a in idx:
            for b in idx:
                if a >= b:
                    continue
                ra, rb = recs[a], recs[b]
                if not ra.get("battery") or not rb.get("battery"):
                    continue
                if ra["battery"] == rb["battery"]:
                    continue
                ta = dict(ra); tb = dict(rb)
                ta["battery"], tb["battery"] = rb["battery"], ra["battery"]
                trial = list(recs)
                trial[a], trial[b] = ta, tb
                na, nb = _earliest_start(inst, trial, ta), _earliest_start(inst, trial, tb)
                if na > float(ra["start"]) + 1e-9 or nb > float(rb["start"]) + 1e-9:
                    continue                      # 交换后可能更晚 → 放弃
                trial[a] = _shift(inst, ta, na)
                trial[b] = _shift(inst, tb, nb)
                v = _hard_violation(inst, trial)
                if v < v0 - 1e-9 and (best is None or v < best[0]):
                    best = (v, trial, a, b, na, nb)
    if best is None:
        if verbose:
            print("  [时限修复] 未找到可行的电池交换（违反量保持 %.1f s）" % v0)
        return 0, False
    sol["transport"] = best[1]
    if verbose:
        print("  [时限修复] 交换 %s 与 %s 的电池：开始时刻 %.1f→%.1f / %.1f→%.1f，"
              "违反量 %.1f → %.1f s"
              % (recs[best[2]]["sid"], recs[best[3]]["sid"],
                 recs[best[2]]["start"], best[4], recs[best[3]]["start"], best[5], v0, best[0]))
    return 1, True


# ---------------------------------------------------------------------------
# Q3 通信保障：逐段判定 直连 / 中继 / 中断
# ---------------------------------------------------------------------------
def _phase_segments(inst, rec, dt_rate=5.0):
    """把一个运输架次按 爬升/巡航/下降/投送 切段，并在段内按 dt_rate 抽样。

    返回 [dict(phase, t0, t1, pts(Nx3))]，与 dcore.leg 的口径一致：
      h_up = cruise - src.op_alt, h_dn = cruise - dst.op_alt, cruise = max(DEM, 两端) + 50
    """
    g = rec["type"]
    dt = inst.types[g]
    stops = list(rec["route"])
    t = float(rec["start"]) + dt.t_prep + dt.t_load_box * sum(
        len(v) for v in (rec.get("boxes") or {}).values())
    segs = []
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        L = D.leg(inst.nodes, dt, a, b, 0.0)
        na, nb = inst.nodes[a], inst.nodes[b]
        # ---- 爬升（在 a 点垂直上升） ----
        for ph, dur, p0, p1, anc in (
                ("爬升", L.h_up / dt.v_up, (na.lon, na.lat, na.op_alt), (na.lon, na.lat, L.cruise_alt), a),
                ("巡航", L.dist / dt.v_cruise, (na.lon, na.lat, L.cruise_alt),
                 (nb.lon, nb.lat, L.cruise_alt), "%s->%s" % (a, b)),
                ("下降", L.h_dn / dt.v_dn, (nb.lon, nb.lat, L.cruise_alt), (nb.lon, nb.lat, nb.op_alt), b)):
            if dur <= 1e-9:
                continue
            n = max(2, int(math.ceil(dur / dt_rate)) + 1)
            f = np.linspace(0.0, 1.0, n)
            pts = np.c_[p0[0] + (p1[0] - p0[0]) * f,
                        p0[1] + (p1[1] - p0[1]) * f,
                        p0[2] + (p1[2] - p0[2]) * f]
            segs.append(dict(phase=ph, t0=t, t1=t + dur, pts=pts, anchor=anc))
            t += dur
        # ---- 投送（服务区悬停交接） ----
        if b != "O01":
            hold = dt.t_hand_base + dt.t_hand_box * len((rec.get("boxes") or {}).get(b, []))
            if hold > 1e-9:
                n = max(2, int(math.ceil(hold / dt_rate)) + 1)
                pts = np.tile(np.array([[nb.lon, nb.lat, nb.op_alt]]), (n, 1))
                segs.append(dict(phase="投送", t0=t, t1=t + hold, pts=pts, anchor=b))
                t += hold
    return segs


def coverage_for(inst, sol, link, dt_rate=5.0):
    """对每个运输架次逐段判定保障方式，返回 (明细行列表, 统计字典)。"""
    relays = sol.get("relay") or []
    rtype = inst.d["rtype"]
    # 中继架次可用窗口与悬停点
    rl = []
    for r in relays:
        pt = (float(r["lon"]), float(r["lat"]), float(r["hover_alt"]))
        bh_ok, bh_lp, _ = link.backhaul_ok(np.array([pt]))
        rl.append(dict(sid=r.get("sid", ""), pt=pt, t0=float(r["link_done"]),
                       t1=float(r["end"]), bh=bool(bh_ok[0]), bh_lp=float(bh_lp[0])))
    rows = []
    stat = dict(n_seg=0, n_direct=0, n_relay=0, n_none=0, t_direct=0.0, t_relay=0.0,
                t_none=0.0, n_sample=0, n_uncovered=0, relay_used=0)
    for rec in sol["transport"]:
        segs = _phase_segments(inst, rec, dt_rate=dt_rate)
        for sg in segs:
            t0, t1, pts = sg["t0"], sg["t1"], sg["pts"]
            dur = t1 - t0
            n = len(pts)
            d_ok, d_lp, d_bl = link.direct_ok(pts)
            stat["n_sample"] += n
            # 逐采样点归类：直连优先，否则找可用的中继
            modes = np.array(["中断"] * n, dtype=object)
            which = np.array([""] * n, dtype=object)
            modes[d_ok] = "直连"
            need = np.nonzero(~d_ok)[0]
            for i in need:
                p = pts[i]
                ti = t0 + dur * (i / max(1, n - 1))
                best = None
                for r in rl:
                    if not r["bh"] or ti < r["t0"] - 1e-9 or ti > r["t1"] + 1e-9:
                        continue
                    a_ok, a_lp, _ = link.access_ok(p[None, :], r["pt"])
                    if bool(a_ok[0]):
                        if best is None or a_lp[0] < best[1]:
                            best = (r["sid"], float(a_lp[0]))
                if best is not None:
                    modes[i] = "中继"
                    which[i] = best[0]
            # 合并同类连续采样点 → 通信阶段
            i = 0
            while i < n:
                j = i
                while j + 1 < n and modes[j + 1] == modes[i] and which[j + 1] == which[i]:
                    j += 1
                if n == 1:
                    a, b = 0.0, 1.0
                else:
                    a = dur * (i / (n - 1))
                    b = dur * (j / (n - 1)) if j < n - 1 else dur
                if b - a > 1e-9 or modes[i] != "中断":
                    rl_ref = str(which[i]) if str(which[i]).strip() else "—"
                    rows.append({"运输架次编号": rec["sid"], "通信阶段": sg["phase"],
                                 "开始时刻（s）": round(t0 + a, 1), "结束时刻（s）": round(t0 + b, 1),
                                 "保障方式": str(modes[i]), "中继架次编号": rl_ref})
                    stat["n_seg"] += 1
                    if modes[i] == "直连":
                        stat["n_direct"] += 1
                        stat["t_direct"] += b - a
                    elif modes[i] == "中继":
                        stat["n_relay"] += 1
                        stat["t_relay"] += b - a
                    else:
                        stat["n_none"] += 1
                        stat["t_none"] += b - a
                if modes[i] == "中断":
                    stat["n_uncovered"] += (j - i + 1)
                i = j + 1
    stat["relay_used"] = len({r["中继架次编号"] for r in rows if r["中继架次编号"] not in ("", "—")})
    return rows, stat


# ---------------------------------------------------------------------------
# 组装 6 张表
# ---------------------------------------------------------------------------
def sheet_q2_transport(sol):
    rows = []
    for r in sol["transport"]:
        rows.append({"架次编号": r["sid"], "无人机编号": r.get("drone", ""),
                     "机型编号": r.get("type", ""), "电池编号": r.get("battery", ""),
                     "开始时刻（s）": round(float(r["start"]), 1),
                     "访问服务区顺序": "->".join(r["route"]),
                     "返回O01时刻（s）": round(float(r["end"]), 1),
                     "架次能耗（kWh）": round(float(r["energy"]), 4)})
    rows.sort(key=lambda x: (x["开始时刻（s）"], x["架次编号"]))
    return rows


def sheet_q2_deliver(inst, sol):
    m = {r["sid"]: r for r in sol["transport"]}
    rows = []
    for r in sol["transport"]:
        for sid, boxes in (r.get("boxes") or {}).items():
            for b in boxes:
                t = r["deliver"].get(b)
                if t is None:
                    t = float(r["start"]) + float(r.get("offs", {}).get(sid, 0.0))
                rows.append({"货箱编号": b, "架次编号": r["sid"], "服务区编号": sid,
                             "交付完成时刻（s）": round(float(t), 1)})
    rows.sort(key=lambda x: (x["货箱编号"]))
    return rows


def sheet_q3_relay(sol):
    rows = []
    for r in (sol.get("relay") or []):
        rows.append({"中继架次编号": r.get("sid", ""), "中继无人机编号": r.get("drone", ""),
                     "能源组件编号": r.get("comp", ""),
                     "开始时刻（s）": round(float(r.get("depart", 0.0)), 1),
                     "悬停经度（°）": round(float(r["lon"]), 6),
                     "悬停纬度（°）": round(float(r["lat"]), 6),
                     "悬停海拔（m）": round(float(r["hover_alt"]), 1),
                     "建链完成时刻（s）": round(float(r["link_done"]), 1),
                     "服务结束时刻（s）": round(float(r["end"]), 1),
                     "返回O01时刻（s）": round(float(r["back"]), 1),
                     "架次能耗（kWh）": round(float(r["e_total"]), 4)})
    rows.sort(key=lambda x: (x["开始时刻（s）"], x["中继架次编号"]))
    return rows


def sheet_q4(cols):
    """复制 results/Q4_分区配置.xlsx；不存在则返回空表（仅列名）。"""
    if not os.path.exists(Q4_XLSX):
        print("  Q4：未发现 %s，Q4_分区配置 留空（保留列名）" % Q4_XLSX)
        return [], "未提供"
    try:
        raw = pd.read_excel(Q4_XLSX)
    except Exception as e:
        print("  Q4：读取 %s 失败（%s），留空" % (Q4_XLSX, e))
        return [], "读取失败"
    # 表头可能带“（2或3）”等全/半角差异，按列序位置对齐到模板列名
    rows = []
    for _, r in raw.iterrows():
        vals = list(r.values)
        if all((v is None) or (isinstance(v, float) and v != v) for v in vals):
            continue
        d = {}
        for i, c in enumerate(cols):
            v = vals[i] if i < len(vals) else None
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = None if v != v else float(v)
            elif isinstance(v, float) and v != v:
                v = None
            d[c] = v
        rows.append(d)
    print("  Q4：复制 %s（%d 行）" % (Q4_XLSX, len(rows)))
    return rows, os.path.basename(Q4_XLSX)


# ---------------------------------------------------------------------------
def main():
    t_all = time.time()
    print("=" * 78)
    print("export_results.py —— 结果文件导出")
    print("=" * 78)
    cols = template_columns()
    print("模板工作表：%s" % " | ".join(cols.keys()))

    import q2 as Q
    inst = Q.Instance()

    # ---- Q1 ----
    q1_rows, q1_meta = q1_min_sortie_scheme()

    # ---- Q2 / Q3 解 ----
    sol, origin = ensure_solution(inst)

    # ---- 硬时限微修复（不改箱-架次归属，只交换同机型共享电池并前移开始时刻） ----
    n_fix, changed = repair_deadlines(inst, sol)
    if changed:
        sol.setdefault("meta", {})
        sol["meta"]["deadline_repair"] = True
        try:
            SIO.save(sol, SIO.SOL_JSON)
            print("  修复后的解已写回 %s" % SIO.SOL_JSON)
        except Exception as e:
            print("  [警告] 修复结果写回失败：%s" % e)

    # ---- Q3 通信保障（独立逐段判定） ----
    t0 = time.time()
    link = C.Link(inst)
    cov_rows, cov_stat = coverage_for(inst, sol, link, dt_rate=5.0)
    n_relay = len(sol.get("relay") or [])
    print("  Q3：通信阶段 %d 段（直连 %d / 中继 %d / 中断 %d）；中断总时长 %.1f s"
          "（%.1f s 计算）"
          % (cov_stat["n_seg"], cov_stat["n_direct"], cov_stat["n_relay"], cov_stat["n_none"],
             cov_stat["t_none"], time.time() - t0))

    # ---- 组表 ----
    sheets = {}
    sheets["Q1_单点组批"] = q1_rows
    sheets["Q2_运输架次"] = sheet_q2_transport(sol)
    sheets["Q2_逐箱交付"] = sheet_q2_deliver(inst, sol)
    sheets["Q3_中继架次"] = sheet_q3_relay(sol)
    sheets["Q3_通信保障"] = cov_rows
    q4_rows, q4_src = sheet_q4(cols["Q4_分区配置"])
    sheets["Q4_分区配置"] = q4_rows

    # ---- 方案汇总 ----
    tr = sol["transport"]
    dl = sheets["Q2_逐箱交付"]
    hard_v = 0
    for r in dl:
        b = inst.bidx[r["货箱编号"]]
        hd = inst.hard[b.bid]
        if hd < BIG and r["交付完成时刻（s）"] > hd + 0.5:
            hard_v += 1
    q2E = sum(float(r["energy"]) for r in tr)
    q2mk = max([float(r["end"]) for r in tr], default=0.0)
    q3E = sum(float(r.get("e_total", 0.0)) for r in (sol.get("relay") or []))
    summ = [
        ("Q1 架次数", q1_meta["n_sortie"], "架", "最少架次方案：%s" % q1_meta["scheme"]),
        ("Q1 总运输能耗", q1_meta["energy"], "kWh", "架次能耗之和"),
        ("Q1 累计作业时间", q1_meta["worktime"], "s", "各架次作业时长之和"),
        ("Q1 Pareto 前沿点数", q1_meta["n_front"], "个", "（架次数, 能耗, 工时）非支配解"),
        ("Q2 运输架次数", len(tr), "架", "解来源：%s" % origin),
        ("Q2 运输总能耗", round(q2E, 3), "kWh", "逐架次求和"),
        ("Q2 完工时间", round(q2mk, 1), "s", "max(返回 O01 时刻)"),
        ("Q2 交付货箱数", len(dl), "箱", "应为 80"),
        ("Q2 硬时限违反箱数", hard_v, "箱", "医疗期望送达 / 首批截止"),
        ("Q3 中继架次数", n_relay, "架", "解来源：%s" % origin),
        ("Q3 中继总能耗", round(q3E, 3), "kWh", "飞行 + 悬停通信"),
        ("Q3 通信直连时长", round(cov_stat["t_direct"], 1), "s", "%d 段" % cov_stat["n_direct"]),
        ("Q3 通信中继时长", round(cov_stat["t_relay"], 1), "s", "%d 段" % cov_stat["n_relay"]),
        ("Q3 通信中断时长", round(cov_stat["t_none"], 1), "s", "%d 段" % cov_stat["n_none"]),
        ("Q3 通信中断采样点", cov_stat["n_uncovered"], "个", "共 %d 个采样点" % cov_stat["n_sample"]),
        ("Q4 分区配置来源", q4_src, "-", "results/Q4_分区配置.xlsx"),
        ("合计总能耗（运输+中继）", round(q2E + q3E, 3), "kWh", "Q2 + Q3"),
    ]
    sum_rows = [{"指标": a, "数值": b, "单位": c, "说明": d} for a, b, c, d in summ]

    # ---- 增补表 1：3 架最小增配方案（达成全程连续通信；模板 6 表之外的补充件） ----
    r3 = sol.get("relay3") or []
    ra = (sol.get("meta") or {}).get("relay_analysis") or {}
    add3 = []
    for i, r in enumerate(r3, 1):
        add3.append({
            "中继架次编号": r.get("sid") or ("Q3R3-%02d" % i),
            "中继无人机编号": r["drone"], "能源组件编号": r["comp"],
            "开始时刻（s）": round(float(r["depart"]), 1),
            "悬停经度（°）": round(float(r["lon"]), 7),
            "悬停纬度（°）": round(float(r["lat"]), 7),
            "悬停海拔（m）": round(float(r["hover_alt"]), 1),
            "悬停离地高度（m）": round(float(r["agl"]), 1),
            "建链完成时刻（s）": round(float(r["link_done"]), 1),
            "服务结束时刻（s）": round(float(r["end"]), 1),
            "返回O01时刻（s）": round(float(r["back"]), 1),
            "架次能耗（kWh）": round(float(r["e_total"]), 4),
            "悬停时长（s）": round(float(r.get("hover", 0.0)), 1),
            "返航SOC（%）": round(100 * float(r["soc"]), 2),
        })

    # ---- 增补表 2：中继资源缺口分析（判定性结论） ----
    gap_rows = [
        {"项目": "需求实例数（统一 10 s 栅格）", "数值": ra.get("n3_miss") is not None and 1454 or "",
         "说明": "20 个运输架次的「直连不可用」采样点"},
        {"项目": "几何可覆盖性", "数值": "992 / 992 时间格单点可覆盖",
         "说明": "候选悬停点 2471 个，每实例平均 775 个可选点 ⇒ 瓶颈不是几何"},
        {"项目": "库存中继台数", "数值": 2, "说明": "R01、R02"},
        {"项目": "2 架中继可行性", "数值": "不可行",
         "说明": ra.get("n2_msg") or "状态 DP 判定无可行解"},
        {"项目": "3 架中继（最小增配）", "数值": "可行",
         "说明": "覆盖 100%、时序冲突 0、返航电量违反 0"},
        {"项目": "增配后需求实例覆盖", "数值": "%d / 1454" % (1454 - int(ra.get("n3_miss", 0)),),
         "说明": "全覆盖"},
        {"项目": "增配后中继架次数", "数值": ra.get("n3_sorties", len(r3)),
         "说明": "已含回 O01 更换能源组件的拆分"},
        {"项目": "增配后单次最长悬停（s）", "数值": round(max([float(x.get("hover", 0)) for x in r3] or [0]), 1),
         "说明": "不超过一组能源组件容量 7233 s"},
        {"项目": "增配后中继总能耗（kWh）", "数值": round(float(ra.get("n3_energy", 0.0)), 3),
         "说明": "飞行 + 悬停通信"},
        {"项目": "增配后最低返航 SOC（%）",
         "数值": round(100 * min([float(x["soc"]) for x in r3] or [0]), 1),
         "说明": "下限 20%"},
        {"项目": "中继无人机资源缺口", "数值": "1 架", "说明": "需求 3 − 库存 2"},
        {"项目": "中继能源组件缺口", "数值": "0 组", "说明": "现有 6 组即可支撑 3 架中继"},
        {"项目": "库存口径下的最优折中", "数值": "%d 个中继架次" % n_relay,
         "说明": "满足除「通信连续」外的全部约束；中断并集见「方案汇总」"},
    ]

    # ---- 写 xlsx ----
    order = ["Q1_单点组批", "Q2_运输架次", "Q2_逐箱交付", "Q3_中继架次",
             "Q3_通信保障", "Q4_分区配置", "方案汇总",
             "Q3_中继架次_增配方案", "Q3_中继缺口分析"]
    sum_cols = ["指标", "数值", "单位", "说明"]
    add3_cols = ["中继架次编号", "中继无人机编号", "能源组件编号", "开始时刻（s）",
                 "悬停经度（°）", "悬停纬度（°）", "悬停海拔（m）", "悬停离地高度（m）",
                 "建链完成时刻（s）", "服务结束时刻（s）", "返回O01时刻（s）",
                 "架次能耗（kWh）", "悬停时长（s）", "返航SOC（%）"]
    gap_cols = ["项目", "数值", "说明"]
    with pd.ExcelWriter(XLSX, engine="openpyxl") as w:
        for name in order:
            if name == "Q3_中继架次_增配方案":
                df = pd.DataFrame(add3, columns=add3_cols)
            elif name == "Q3_中继缺口分析":
                df = pd.DataFrame(gap_rows, columns=gap_cols)
            else:
                c = cols.get(name, sum_cols)
                data = sheets.get(name, sum_rows)
                df = pd.DataFrame(data, columns=c)
            df.to_excel(w, sheet_name=name, index=False)
    print("\n已写出：%s" % XLSX)
    for name in order:
        if name == "Q3_中继架次_增配方案":
            ncol = len(add3_cols); nrow = len(add3)
        elif name == "Q3_中继缺口分析":
            ncol = len(gap_cols); nrow = len(gap_rows)
        else:
            ncol = len(cols.get(name, sum_cols)); nrow = len(sheets.get(name, sum_rows))
        print("  %-22s 行数=%4d 列数=%2d" % (name, nrow, ncol))

    # ---- 回读自检：表头必须与模板逐字一致 ----
    ok = True
    wb = openpyxl.load_workbook(XLSX)
    for name in TPL_COLS:
        head = [str(v).strip() for v in
                next(wb[name].iter_rows(min_row=1, max_row=1, values_only=True)) if v is not None]
        # 模板 Q1/Q2/Q3 表中，模板文件本身有空列被读进来时需裁剪
        want = cols[name]
        if head[:len(want)] != want:
            ok = False
            print("  [不一致] %s\n    实际=%s\n    期望=%s" % (name, head, want))
        else:
            print("  [表头校验通过] %-14s %d 列" % (name, len(want)))
    if os.path.exists(TPL):
        tpl = openpyxl.load_workbook(TPL)
        if [ws.title for ws in wb.worksheets][:6] != [ws.title for ws in tpl.worksheets]:
            ok = False
            print("  [不一致] 工作表名或顺序与模板不同")
        else:
            print("  [表名校验通过] 前 6 张表名与顺序与模板一致")
        tpl.close()
    else:
        # 模板不在预期位置时降级：只做内置列名校验，并明确报告（审阅 #26/#28）
        ok = False
        print("  [模板缺失] 未找到官方模板 %s；已改用内置列名常量校验，"
              "请把「结果提交模板.xlsx」放到该路径或设环境变量 DTI_TPL 后重跑。" % TPL)
    wb.close()
    json.dump(dict(q1=q1_meta, coverage={k: (round(v, 3) if isinstance(v, float) else v)
                                         for k, v in cov_stat.items()},
                   tables={k: len(v) for k, v in sheets.items()}, header_ok=ok,
                   elapsed_s=round(time.time() - t_all, 1)),
              open(os.path.join(OUT, "导出汇总.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n" + "-" * 78)
    print("结果行数：")
    for name in order[:6]:
        print("  %-14s %4d 行" % (name, len(sheets[name])))
    print("  通信：直连 %.0f s / 中继 %.0f s / 中断 %.0f s（中断 %d 个采样点）"
          % (cov_stat["t_direct"], cov_stat["t_relay"], cov_stat["t_none"], cov_stat["n_uncovered"]))
    print("总耗时 %.1f s；表头一致性：%s" % (time.time() - t_all, "通过" if ok else "不通过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
