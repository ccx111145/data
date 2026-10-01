# -*- coding: utf-8 -*-
"""
make_numbers.py —— 从 results/ 的 json/xlsx 自动生成论文用的数字宏与表格

输出：
    paper/numbers.tex   —— 全文所有数字的 \\newcommand 宏（论文正文只引用宏，不硬编码）
    paper/tables.tex    —— 主要数据表格（节点/机型/最大安全载荷/方案对比/灵敏度/中继架次）

所有数据缺失时写入占位（「待补」）而不抛异常，保证论文始终可编译。
运行：  cd code;  H:\\python\\python.exe make_numbers.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import dcore as D
import make_figs as F   # 复用数据装载（solution.json / 结果表的降级逻辑）

BASE = D.BASE
OUT = D.RESULTS
PAPER = os.path.join(BASE, "paper")
os.makedirs(PAPER, exist_ok=True)
LOGFILE = os.path.join(OUT, "数字宏生成日志.txt")

LOG: List[str] = []


def log(m):
    LOG.append(str(m))
    try:
        print(m)
    except Exception:
        pass


def flush():
    try:
        with open(LOGFILE, "w", encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n")
    except Exception:
        pass


PLACEHOLDER = "待补"
NUM: Dict[str, str] = {}


def P(key: str, val, nd: Optional[int] = None, suffix: str = "") -> None:
    """登记一个宏。val 为 None/NaN 时写占位。"""
    if val is None:
        NUM[key] = PLACEHOLDER
        return
    try:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            NUM[key] = PLACEHOLDER
            return
    except Exception:
        pass
    if nd is not None:
        try:
            s = ("%%.%df" % nd) % float(val)
        except Exception:
            s = str(val)
    else:
        s = str(val)
    NUM[key] = s + suffix


def TEX(s) -> str:
    s = str(s)
    rep = [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
           ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
           ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")]
    for a, b in rep:
        s = s.replace(a, b)
    return s


def fx(v, nd=2, dash=PLACEHOLDER):
    try:
        f = float(v)
        if not np.isfinite(f):
            return dash
        return ("%%.%df" % nd) % f
    except Exception:
        return dash


def read_json(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log("! %s 读取失败：%s" % (name, e))
        return None


def read_xlsx(name, sheet=0):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    try:
        return pd.read_excel(p, sheet_name=sheet)
    except Exception as e:
        log("! %s 读取失败：%s" % (name, e))
        return None


# ===========================================================================
# 1. 基础数据
# ===========================================================================
def collect_base(d) -> dict:
    boxes = d["boxes"]
    nodes = d["nodes"]
    kinds = {}
    for b in boxes:
        k = kinds.setdefault(b.kind, dict(n=0, m=0.0, v=0.0))
        k["n"] += 1; k["m"] += b.mass; k["v"] += b.vol
    tot_m = sum(b.mass for b in boxes)
    tot_v = sum(b.vol for b in boxes)
    first = [b for b in boxes if b.first_batch]
    dists = {sid: D.haversine(nodes["O01"].lon, nodes["O01"].lat,
                              nodes[sid].lon, nodes[sid].lat) for sid in d["SIDS"]}
    near = min(dists, key=dists.get); far = max(dists, key=dists.get)

    P("TotalBoxes", len(boxes))
    P("TotalMass", tot_m, 0)
    P("TotalVol", tot_v, 3)
    P("NumAreas", len(d["SIDS"]))
    P("NumDrones", sum(len(v) for v in d["fleet"].values()))
    P("NumRelay", len(d["rfleet"]))
    P("NumTypes", len(d["ttypes"]))
    P("FirstBatchBoxes", len(first))
    P("FirstBatchMass", sum(b.mass for b in first), 0)
    P("NodeOCount", 1)
    P("DemNear", dists[near] / 1000.0, 2)
    P("DemNearID", near[1:])
    P("DemFar", dists[far] / 1000.0, 2)
    P("DemFarID", far[1:])
    P("ElevMin", min(nodes[s].elev for s in d["SIDS"]), 1)
    P("ElevMax", max(nodes[s].elev for s in d["SIDS"]), 1)
    P("ElevO", nodes["O01"].elev, 1)
    P("PopTotal", sum(nodes[s].pop for s in d["SIDS"]), 0)
    dem = D.get_dem()
    P("DemCell", 30)
    P("DemZMin", float(dem.z.min()), 1)
    P("DemZMax", float(dem.z.max()), 1)
    P("DemNy", dem.ny); P("DemNx", dem.nx)
    # 机型
    for g in ("A", "B", "C"):
        t = d["ttypes"][g]
        P("Type%sQmax" % g, t.q_max, 0)
        P("Type%sVcap" % g, t.v_cap, 3)
        P("Type%sEuse" % g, t.e_use, 1)
        P("Type%sVc" % g, t.v_cruise, 1)
        P("Type%sRem" % g, t.range_empty / 1000.0, 1)
        P("Type%sRfull" % g, t.range_full / 1000.0, 1)
        P("Type%sEmpty" % g, t.m_empty, 1)
        P("Type%sN" % g, len(d["fleet"][g]))
        P("Type%sBat" % g, d["batt"][g][0])
        P("Type%sTfull" % g, d["batt"][g][1], 0)
        P("Type%sEta" % g, t.eta_up, 2)
        P("Type%sVup" % g, t.v_up, 1)
    rt = d["rtype"]
    P("RelayMtow", rt.mtow, 1)
    P("RelayEuse", rt.e_use, 1)
    P("RelayPhover", rt.p_hover, 2)
    P("RelayPcomm", rt.p_comm, 2)
    P("RelayAglMax", rt.h_max_agl, 0)
    P("RelayN", len(d["rfleet"]))
    P("RelayBat", d["rbatt"][0])
    P("RelayTfull", d["rbatt"][1], 0)
    cp = d["comm"]
    P("CommF", cp.f_mhz, 0)
    P("CommPth", cp.p_sens + cp.margin, 0)
    P("CommLobs", cp.l_obs, 0)
    P("CommLsys", cp.l_sys, 0)
    P("Rho", d["ttypes"]["A"].rho * 100, 0)
    # 网关天线离地高度（附件给定）与直连门限对应的无遮挡自由空间距离
    try:
        import dcore as _D
        _cp = d["comm"]
        P("GwAntH", float(_cp.gw_ant_h), 0)
        _lmax = _D.lmax_bidir(_cp.transport, _cp.gateway, _cp)
        _d_km = 10 ** ((_lmax - 32.45 - 20 * math.log10(_cp.f_mhz)) / 20.0)
        P("DirectRange", float(_d_km), 1)
        _d_obs = 10 ** ((_lmax - _cp.l_obs - 32.45 - 20 * math.log10(_cp.f_mhz)) / 20.0)
        P("DirectRangeObs", float(_d_obs), 1)
        P("DirLmax", float(_lmax), 0)
    except Exception as _e:
        log("! 网关/门限宏计算失败：%s" % _e)
        P("GwAntH", 20); P("DirectRange", 12.5); P("DirectRangeObs", 4.0); P("DirLmax", 122)
    P("CargoKindN", len(kinds))
    # 物资构成（按质量降序）
    order = sorted(kinds.items(), key=lambda kv: -kv[1]["m"])
    # 注意：宏名中不能含数字（TeX 控制字只由字母构成），故用 One/Two/Three/Four
    cn_words = ["One", "Two", "Three", "Four"]
    for i, (k, v) in enumerate(order[:4]):
        w = cn_words[i]
        P("Cargo%sName" % w, k)
        P("Cargo%sN" % w, v["n"])
        P("Cargo%sM" % w, v["m"], 0)
    return dict(kinds=order, dists=dists)


# ===========================================================================
# 2. Q1
# ===========================================================================
def collect_q1(d) -> Optional[pd.DataFrame]:
    df = F._q1_payload_table(d)
    if df is None or df.empty:
        log("! Q1 最大安全载荷表不可用，Q1 相关数字写占位。")
        for k in ("QoneLimitedC", "QoneMinPayC", "QoneMinPayCArea", "QoneLimitedAB",
                  "QoneLimitedB", "QoneMinPayB", "QoneMinPayBArea"):
            P(k, None)
        return None
    # 列名兼容：结果表在旧版本里字段名不同（审阅 #28：结果缺失/列缺失时不得直接崩，
    # 而应写占位并告警，避免"论文数字悄悄退回内置默认值"）。
    if "是否受能量限制" not in df.columns or "机型编号" not in df.columns:
        log("! Q1 最大安全载荷表缺少列 %s，Q1 相关数字写占位。"
            % [c for c in ("是否受能量限制", "机型编号") if c not in df.columns])
        for k in ("QoneLimitedC", "QoneMinPayC", "QoneMinPayCArea", "QoneLimitedAB",
                  "QoneLimitedB", "QoneMinPayB", "QoneMinPayBArea"):
            P(k, None)
        return None
    lim = df[df["是否受能量限制"] == True]  # noqa: E712
    limC = lim[lim["机型编号"] == "C"]
    limB = lim[lim["机型编号"] == "B"]
    limAB = lim[lim["机型编号"].isin(["A", "B"])]
    P("QoneLimitedC", int(len(limC)))
    P("QoneLimitedB", int(len(limB)))
    P("QoneLimitedAB", int(len(limAB)))
    P("QoneFullAB", int(15 * 2 - len(limAB)))
    if len(limB):
        ib = int(limB["最大安全载荷_kg"].astype(float).idxmin())
        P("QoneMinPayB", float(limB.loc[ib, "最大安全载荷_kg"]), 1)
        P("QoneMinPayBArea", str(limB.loc[ib, "服务区编号"]))
    else:
        P("QoneMinPayB", 30.0, 1); P("QoneMinPayBArea", "—")
    if len(limC):
        i = int(limC["最大安全载荷_kg"].astype(float).idxmin())
        P("QoneMinPayC", float(limC.loc[i, "最大安全载荷_kg"]), 1)
        P("QoneMinPayCArea", str(limC.loc[i, "服务区编号"]))
        P("QoneMaxPayCLim", float(limC["最大安全载荷_kg"].astype(float).max()), 1)
        P("QonePayCLoss", 80.0 - float(limC["最大安全载荷_kg"].astype(float).min()), 1)
        P("QoneLimAreaList", "、".join(str(x) for x in limC["服务区编号"]))
    else:
        P("QoneMinPayC", 80.0, 1); P("QoneMinPayCArea", "—")
        P("QoneMaxPayCLim", 80.0, 1); P("QonePayCLoss", 0.0, 1); P("QoneLimAreaList", "无")
    for g in ("A", "B", "C"):
        sub = df[df["机型编号"] == g]["最大安全载荷_kg"].astype(float)
        P("QonePay%sMean" % g, float(sub.mean()), 1)
        P("QonePay%sMin" % g, float(sub.min()), 1)

    # 前沿
    fr = read_json("Q1_前沿.json")
    if fr:
        cnt = [int(x["count"]) for x in fr]
        E = [float(x["E"]) for x in fr]
        T = [float(x["T"]) for x in fr]
        P("QoneFrontN", len(fr))
        P("QoneSorties", min(cnt))
        P("QoneEnergyMin", min(E), 2)
        P("QoneEnergyMax", max(E), 2)
        minc = min(cnt)
        sub = [x for x in fr if int(x["count"]) == minc]
        P("QoneEnergyLeastSortie", min(float(x["E"]) for x in sub), 2)
        P("QoneTimeLeastSortie", min(float(x["T"]) for x in sub) / 3600.0, 2)
        P("QoneTimeMin", min(T) / 3600.0, 2)
        P("QoneTimeMax", max(T) / 3600.0, 2)
        P("QoneSortiesMax", max(cnt))
    else:
        for k in ("QoneFrontN", "QoneSorties", "QoneEnergyMin", "QoneEnergyMax",
                  "QoneEnergyLeastSortie", "QoneTimeLeastSortie", "QoneTimeMin",
                  "QoneTimeMax", "QoneSortiesMax"):
            P(k, None)

    # 具名方案
    schemes = {}
    xl_p = os.path.join(OUT, "Q1_单点组批.xlsx")
    if os.path.exists(xl_p):
        try:
            xl = pd.ExcelFile(xl_p)
            for sn in xl.sheet_names:
                s = xl.parse(sn)
                if "架次能耗_kWh" not in s.columns:
                    continue
                schemes[sn] = dict(n=len(s), E=float(s["架次能耗_kWh"].sum()),
                                   T=float(s["往返时间_s"].sum()) if "往返时间_s" in s.columns else float("nan"),
                                   boxes=int(s["箱数"].sum()) if "箱数" in s.columns else 0)
            P("QoneSchemeN", len(schemes))
            base = None
            for sn, v in schemes.items():
                if "S1" in sn:
                    P("QoneSchemeOneSorties", v["n"]); P("QoneSchemeOneEnergy", v["E"], 2)
                    P("QoneSchemeOneTime", v["T"] / 3600.0, 2); base = v
            if base is None and schemes:
                sn = list(schemes)[0]; v = schemes[sn]
                P("QoneSchemeOneSorties", v["n"]); P("QoneSchemeOneEnergy", v["E"], 2)
                P("QoneSchemeOneTime", v["T"] / 3600.0, 2); base = v
            if base is None:
                base = dict(E=1.0, T=1.0, n=1)
            # 与 S1 相比的节能/省时幅度
            bestE = min(schemes.values(), key=lambda v: v["E"]) if schemes else base
            bestT = min(schemes.values(), key=lambda v: v["T"]) if schemes else base
            P("QoneSaveESorties", bestE["n"] - base["n"])
            P("QoneSaveEPct", 100.0 * (base["E"] - bestE["E"]) / max(1e-9, base["E"]), 2)
            P("QoneSaveTPct", 100.0 * (base["T"] - bestT["T"]) / max(1e-9, base["T"]), 2)
            P("QoneSaveTSorties", bestT["n"] - base["n"])
            P("QoneSchemesBoxes", int(base.get("boxes", 0) or 80))
        except Exception as e:
            log("! Q1_单点组批.xlsx 解析失败：%s" % e)
    else:
        for k in ("QoneSchemeN", "QoneSchemeOneSorties", "QoneSchemeOneEnergy",
                  "QoneSchemeOneTime", "QoneSaveEPct", "QoneSaveTPct", "QoneSaveESorties",
                  "QoneSaveTSorties", "QoneSchemesBoxes"):
            P(k, None)

    # IP 交叉验证
    ip = read_xlsx("Q1_IP交叉验证.xlsx")
    if ip is not None and len(ip):
        P("QoneIPN", len(ip))
        for c, key in (("一致1", "QoneIPConsistCount"), ("一致2", "QoneIPConsistEnergy"),
                       ("一致3", "QoneIPConsistGlobal")):
            if c in ip.columns:
                P(key, int(ip[c].astype(float).sum()))
        P("QoneIPAllOK", "是" if all(
            int(ip[c].astype(float).sum()) == len(ip) for c in ("一致1", "一致2", "一致3")
            if c in ip.columns) else "部分一致")
    else:
        for k in ("QoneIPN", "QoneIPConsistCount", "QoneIPConsistEnergy",
                  "QoneIPConsistGlobal", "QoneIPAllOK"):
            P(k, None)

    # rho 灵敏度
    sen = read_xlsx("Q1_灵敏度.xlsx")
    if sen is not None and len(sen):
        P("QoneRhoN", len(sen))
        rr = sen["返航安全余量比例"].astype(float).values
        P("QoneRhoLo", rr.min(), 2); P("QoneRhoHi", rr.max(), 2)
        if "最少架次数" in sen.columns:
            v = pd.to_numeric(sen["最少架次数"], errors="coerce").astype(float).values
            fin = v[np.isfinite(v)]
            if fin.size:
                P("QoneRhoSortiesLo", int(fin[0]))
                P("QoneRhoSortiesHi", int(fin[-1]))
                P("QoneRhoSortiesSpan", int(fin.max() - fin.min()))
                P("QoneRhoSortiesMax", int(fin.max()))
            else:
                for k in ("QoneRhoSortiesLo", "QoneRhoSortiesHi",
                          "QoneRhoSortiesSpan", "QoneRhoSortiesMax"):
                    P(k, None)
        for g in ("A", "B", "C"):
            c = "%s型受限服务区数" % g
            if c in sen.columns:
                vv = sen[c].astype(float).values
                P("QoneRhoLim%sLo" % g, int(vv[0])); P("QoneRhoLim%sHi" % g, int(vv[-1]))
        c = "C型最大安全载荷均值_kg"
        if c in sen.columns:
            vv = sen[c].astype(float).values
            P("QoneRhoCPayLo", vv[0], 1); P("QoneRhoCPayHi", vv[-1], 1)
            P("QoneRhoCPayDrop", vv[0] - vv[-1], 1)
    else:
        for k in ("QoneRhoN", "QoneRhoLo", "QoneRhoHi", "QoneRhoSortiesLo",
                  "QoneRhoSortiesHi", "QoneRhoSortiesSpan", "QoneRhoSortiesMax",
                  "QoneRhoCPayLo", "QoneRhoCPayHi", "QoneRhoCPayDrop"):
            P(k, None)
    return df


# ===========================================================================
# 3. Q2
# ===========================================================================
def collect_q2(d) -> dict:
    raw = read_json("Q2_raw.json") or {}
    front = raw.get("front") or []
    summ = raw.get("summary") or {}
    P("QtwoConfigN", len(summ))
    P("QtwoFrontN", len(front))
    if summ:
        # 完整覆盖（nbox == 80）中架次数最少者作为推荐方案
        full = {k: v for k, v in summ.items() if int(v.get("nbox", 0)) >= len(d["boxes"])}
        pool = full or summ
        best = min(pool.items(), key=lambda kv: (kv[1].get("count", 1e9), kv[1].get("makespan", 1e9)))
        nm, v = best
        P("QtwoBestName", nm)
        P("QtwoSorties", int(v.get("count", 0)))
        P("QtwoEnergy", float(v.get("energy", 0)), 2)
        P("QtwoMakespanS", float(v.get("makespan", 0)), 0)
        P("QtwoMakespanH", float(v.get("makespan", 0)) / 3600.0, 2)
        P("QtwoTardyH", float(v.get("tardiness", 0)) / 3600.0, 1)
        P("QtwoTardyS", float(v.get("tardiness", 0)), 0)
        P("QtwoOntime", int(v.get("ontime", 0)))
        P("QtwoLate", int(v.get("nlate", 0)))
        P("QtwoBoxes", int(v.get("nbox", 0)))
        P("QtwoOntimeRate", 100.0 * float(v.get("ontime_rate", 0)), 2)
        P("QtwoAvgDeliver", float(v.get("avg_deliver", 0)) / 60.0, 1)
        P("QtwoMaxDeliver", float(v.get("max_deliver", 0)) / 60.0, 1)
        P("QtwoHard", float(v.get("hard_violation", 0)), 0)
        # 架次数下界方案（可能不完整）
        lb = min(summ.items(), key=lambda kv: kv[1].get("count", 1e9))
        P("QtwoLBName", lb[0])
        P("QtwoLBSorties", int(lb[1].get("count", 0)))
        P("QtwoLBBoxes", int(lb[1].get("nbox", 0)))
        P("QtwoLBEnergy", float(lb[1].get("energy", 0)), 2)
        P("QtwoLBMakespanH", float(lb[1].get("makespan", 0)) / 3600.0, 2)
        P("QtwoLBOn", 100.0 * float(lb[1].get("ontime_rate", 0)), 2)
        # 最及时方案
        bt = min(summ.items(), key=lambda kv: kv[1].get("tardiness", 1e18))
        P("QtwoBestTardyName", bt[0])
        P("QtwoBestTardy", float(bt[1].get("tardiness", 0)) / 3600.0, 1)
        P("QtwoBestTardyOn", 100.0 * float(bt[1].get("ontime_rate", 0)), 2)
        P("QtwoBestTardySorties", int(bt[1].get("count", 0)))
        # 最省能
        be = min(summ.items(), key=lambda kv: kv[1].get("energy", 1e18))
        P("QtwoBestEName", be[0]); P("QtwoBestE", float(be[1].get("energy", 0)), 2)
        P("QtwoBestESorties", int(be[1].get("count", 0)))
    else:
        for k in ("QtwoBestName", "QtwoSorties", "QtwoEnergy", "QtwoMakespanS",
                  "QtwoMakespanH", "QtwoTardyH", "QtwoTardyS", "QtwoOntime", "QtwoLate",
                  "QtwoBoxes", "QtwoOntimeRate", "QtwoAvgDeliver", "QtwoMaxDeliver",
                  "QtwoHard", "QtwoLBName", "QtwoLBSorties", "QtwoLBBoxes", "QtwoLBEnergy",
                  "QtwoLBMakespanH", "QtwoLBOn", "QtwoBestTardyName", "QtwoBestTardy",
                  "QtwoBestTardyOn", "QtwoBestTardySorties", "QtwoBestEName", "QtwoBestE",
                  "QtwoBestESorties"):
            P(k, None)
    return raw


# ===========================================================================
# 4. Q3 / Q4
# ===========================================================================
def collect_q3(d, sol) -> None:
    tr, rl = sol.get("transport") or [], sol.get("relay") or []
    P("QthreeTransportSorties", len(tr))
    nbox = sum(len(v) for r in tr for v in (r.get("boxes") or {}).values())
    P("QthreeBoxes", nbox if nbox else PLACEHOLDER)
    if tr:
        P("QthreeTransportE", sum(float(r.get("energy", 0)) for r in tr), 2)
        P("QthreeMakespanS", max(float(r.get("end", 0)) for r in tr), 0)
        P("QthreeDronesUsed", len({str(r.get("drone", "")) for r in tr}))
    else:
        for k in ("QthreeTransportE", "QthreeMakespanS", "QthreeDronesUsed"):
            P(k, None)
    P("QthreeRelaySorties", len(rl))
    if rl:
        P("QthreeRelayE", sum(float(r.get("e_total", 0)) for r in rl), 2)
        P("QthreeRelayAgl", float(np.median([float(r.get("agl", 0)) for r in rl])), 0)
        P("QthreeRelayAltMax", max(float(r.get("hover_alt", 0)) for r in rl), 0)
        P("QthreeRelayAltMin", min(float(r.get("hover_alt", 0)) for r in rl), 0)
        P("QthreeRelaySocMin", 100.0 * min(float(r.get("soc", 1)) for r in rl), 1)
        P("QthreeRelayComp", len({str(r.get("comp", "")) for r in rl}))
        P("QthreeRelaySpanS", max(float(r.get("back", 0)) for r in rl), 0)
        P("QthreeJointE", (sum(float(r.get("e_total", 0)) for r in rl)
                           + sum(float(r.get("energy", 0)) for r in tr)), 2)
    else:
        for k in ("QthreeRelayE", "QthreeRelayAgl", "QthreeRelayAltMax", "QthreeRelayAltMin",
                  "QthreeRelaySocMin", "QthreeRelayComp", "QthreeRelaySpanS", "QthreeJointE"):
            P(k, None)


def collect_check() -> None:
    p = os.path.join(OUT, "检查说明.md")
    if not os.path.exists(p):
        P("CheckSummary", PLACEHOLDER)
        log("! results/检查说明.md 不存在，检验小结写占位。")
    else:
        try:
            with open(p, "r", encoding="utf-8") as f:
                txt = f.read()
            # 去掉 Markdown 记号与控制字符，只保留可安全排版的中文结论
            clean = []
            for line in txt.splitlines():
                s = line.strip()
                if not s or s[0] in "#>|" or s.startswith("---"):
                    continue
                for ch in ("*", "`", "_", "\\", "$", "&", "%", "#", "{", "}", "~", "^", "|"):
                    s = s.replace(ch, "")
                s = s.strip()
                # 只要成句的结论行，跳过表头/短标签
                if len(s) >= 14 and "—" not in s[:6]:
                    clean.append(s)
            head = clean[0] if clean else ""
            for s in clean[1:4]:
                if len(head) + len(s) > 200:
                    break
                head += "；" + s
            P("CheckSummary", head.rstrip("；") if head else PLACEHOLDER)
            log("· 检查说明小结已提取（%d 字）" % len(head))
        except Exception as e:
            P("CheckSummary", PLACEHOLDER)
            log("! 检查说明.md 读取失败：%s" % e)

    # 校验汇总.json：9 项独立仿真校验的通过情况
    js = read_json("校验汇总.json")
    if not js:
        for k in ("CheckPass", "CheckTotal", "CheckPending", "CheckMaxMassRate",
                  "CheckMaxVolRate", "CheckTimeDev", "CheckInterruptS", "CheckInterruptPts",
                  "CheckCommVerdict"):
            P(k, None)
        return
    checks = js.get("checks") or []
    npass = sum(1 for c in checks if str(c.get("verdict", "")).startswith("通过"))
    npend = sum(1 for c in checks if "待" in str(c.get("verdict", "")))
    P("CheckTotal", len(checks))
    P("CheckPass", npass)
    P("CheckPending", npend)
    P("CheckTimeDev", js.get("time_line_max_dev"), 6)
    dl = js.get("delivery") or {}
    P("CheckUndelivered", int(dl.get("n_undelivered", 0)))
    P("CheckDup", int(dl.get("n_dup", 0)))
    ddl = js.get("deadline") or {}
    P("CheckDeadlineViol", int(ddl.get("v_med", 0)) + int(ddl.get("v_fb", 0)))
    P("CheckDeadlineN", int(ddl.get("n_med", 0)) + int(ddl.get("n_fb", 0)))
    dk = js.get("drone_peak") or {}
    P("CheckDronePeak", "、".join("%s 型 %d 架" % (g, int(v)) for g, v in sorted(dk.items())))
    cm = js.get("comm") or {}
    if cm:
        P("CheckInterruptS", float(cm.get("t_none", 0)), 0)
        P("CheckInterruptPts", int(cm.get("n_none_sample", 0)))
        P("CheckCommSamples", int(cm.get("n_sample", 0)))
        tot = max(1e-9, float(cm.get("t_direct", 0)) + float(cm.get("t_relay", 0)) + float(cm.get("t_none", 0)))
        P("CheckDirectPct", 100.0 * float(cm.get("t_direct", 0)) / tot, 1)
        P("CheckCommVerdict", "未闭合" if float(cm.get("t_none", 0)) > 1.0 else "已闭合")
    else:
        for k in ("CheckInterruptS", "CheckInterruptPts", "CheckCommSamples",
                  "CheckDirectPct", "CheckCommVerdict"):
            P(k, None)


def collect_q4(d) -> None:
    """从 results/Q4_分区配置.xlsx 提炼问题四的关键数字。"""
    p = os.path.join(OUT, "Q4_分区配置.xlsx")
    if not os.path.exists(p):
        for k, v in (("QfourKTwo", PLACEHOLDER), ("QfourKThree", PLACEHOLDER),
                     ("QfourBlocks", PLACEHOLDER), ("QfourBalance", PLACEHOLDER),
                     ("QfourGap", PLACEHOLDER), ("QfourGapThree", PLACEHOLDER),
                     ("QfourSorties", PLACEHOLDER), ("QfourKind", PLACEHOLDER)):
            P(k, v)
        log("! Q4_分区配置.xlsx 不存在，问题四数字写占位。")
        return
    try:
        cfg = pd.read_excel(p, sheet_name="Q4_分区配置")
        C = {str(c).strip(): c for c in cfg.columns}
        ck = C.get("K（2或3）") or C.get("K")
        cg = next((v for k, v in C.items() if "组编号" in k), None)
        cs = next((v for k, v in C.items() if "服务区列表" in k), None)
        for K in (2, 3):
            sub = cfg[cfg[ck].astype(float) == K] if ck else cfg
            if not len(sub):
                continue
            parts = []
            for _, r in sub.iterrows():
                sids = [x for x in str(r[cs]).replace("，", ";").replace(",", ";").split(";") if x.strip()]
                parts.append("%d 区" % len(sids))
            key = "QfourKTwo" if K == 2 else "QfourKThree"
            P(key, "已求解（%d 组：%s）" % (len(sub), " + ".join(parts)))
    except Exception as e:
        log("! Q4 分区表解析失败：%s" % e)
        for k in ("QfourKTwo", "QfourKThree"):
            P(k, None)

    # 均衡性：综合 CV
    try:
        bal = pd.read_excel(p, sheet_name="Q4_均衡性")
        bc = {str(c).strip(): c for c in bal.columns}
        cK = bc.get("K"); ci = bc.get("指标"); ccv = bc.get("变异系数CV")
        if cK and ci and ccv:
            comp = bal[bal[ci].astype(str).str.contains("综合")]
            vals = []
            for _, r in comp.iterrows():
                if r[ccv] == r[ccv]:
                    vals.append("K=%d 时 %.3f" % (int(r[cK]), float(r[ccv])))
            P("QfourBalance", "；".join(vals) if vals else PLACEHOLDER)
    except Exception as e:
        log("! Q4 均衡性表解析失败：%s" % e)
        P("QfourBalance", None)

    # 资源汇总与库存缺口
    try:
        res = pd.read_excel(p, sheet_name="Q4_资源汇总与库存")
        rc = {str(c).strip(): c for c in res.columns}
        ccat = rc.get("资源类别")
        g2 = rc.get("K=2缺口"); g3 = rc.get("K=3缺口"); d2 = rc.get("K=2需求")
        if ccat and g2 is not None:
            tot2 = int(np.nansum(pd.to_numeric(res[g2], errors="coerce").values))
            P("QfourGap", str(tot2))
            if d2 is not None:
                bumps = [("%s 需 %d / 库存 %s" % (str(r[ccat]).split("(")[0],
                                                  int(r[d2]) if r[d2] == r[d2] else 0,
                                                  int(r[rc["库存"]]) if "库存" in rc else 0))
                         for _, r in res.iterrows()
                         if r[g2] == r[g2] and float(r[g2]) > 0]
                P("QfourKind", "；".join(bumps) if bumps else "无缺口")
        if g3 is not None:
            P("QfourGapThree", str(int(np.nansum(pd.to_numeric(res[g3], errors="coerce").values))))
    except Exception as e:
        log("! Q4 资源汇总表解析失败：%s" % e)
        P("QfourGap", None); P("QfourGapThree", None); P("QfourKind", None)

    # 不可分割块数：从 Q4_说明.md 抓取
    try:
        mp = os.path.join(OUT, "Q4_说明.md")
        if os.path.exists(mp):
            with open(mp, "r", encoding="utf-8") as f:
                txt = f.read()
            import re
            mm = re.search(r"得到\s*\*{0,2}(\d+)\s*个不可分割块", txt)
            P("QfourBlocks", int(mm.group(1)) if mm else PLACEHOLDER)
            mm2 = re.search(r"中继架次\s*\*{0,2}(\d+)\s*\*{0,2}\s*个", txt)
            if mm2:
                P("QfourRelayFrozen", int(mm2.group(1)))
    except Exception as e:
        log("! Q4_说明.md 解析失败：%s" % e)
        P("QfourBlocks", None)


def collect_coverage(d) -> None:
    """通信分段统计（导出汇总.json / solution.json 的 coverage）。"""
    js = read_json("导出汇总.json") or {}
    cov = js.get("coverage") or {}
    if cov:
        P("CommSegN", int(cov.get("n_seg", 0)))
        P("CommSegDirect", int(cov.get("n_direct", 0)))
        P("CommSegRelay", int(cov.get("n_relay", 0)))
        P("CommSegNone", int(cov.get("n_none", 0)))
        P("CommTimeNone", float(cov.get("t_none", 0)), 0)
        P("CommTimeDirect", float(cov.get("t_direct", 0)), 0)
        P("CommTimeRelay", float(cov.get("t_relay", 0)), 0)
        P("CommRelayUsed", int(cov.get("relay_used", 0)))
        tot = max(1e-9, float(cov.get("t_direct", 0)) + float(cov.get("t_relay", 0))
                  + float(cov.get("t_none", 0)))
        P("CommDirectPct", 100.0 * float(cov.get("t_direct", 0)) / tot, 1)
        P("CommRelayPct", 100.0 * float(cov.get("t_relay", 0)) / tot, 1)
        P("CommNonePct", 100.0 * float(cov.get("t_none", 0)) / tot, 1)
    else:
        for k in ("CommSegN", "CommSegDirect", "CommSegRelay", "CommSegNone",
                  "CommTimeNone", "CommTimeDirect", "CommTimeRelay", "CommRelayUsed",
                  "CommDirectPct", "CommRelayPct", "CommNonePct"):
            P(k, None)
    q1 = js.get("q1") or {}
    if q1:
        P("QoneExportSorties", int(q1.get("n_sortie", 0)))
        P("QoneExportEnergy", float(q1.get("energy", 0)), 2)
        P("QoneExportWork", float(q1.get("worktime", 0)) / 3600.0, 2)


# ===========================================================================
# 4b. 问题三「中继资源缺口」数字宏（输出 paper/q3_gap.tex）
#     —— 本节为增量追加：只新增函数与写出逻辑，不改动上文任何既有实现。
# ===========================================================================
Q3GAP_FILE = os.path.join(PAPER, "q3_gap.tex")

# 默认值 = 论文正文所依据的已核实结论（N=2 不可行于第 171 格 t=2420 s；N=3 全覆盖）。
# 运行 make_numbers.py 时，若 results/solution.json 的 meta.relay_analysis 与 relay3 已产出，
# 则以文件中的实测值覆盖对应项；否则保留默认值（保证论文口径稳定、可编译）。
Q3GAP: Dict[str, str] = {
    "CommLink": "30",                 # 附录 2 给定：中继建链时间 / s
    "CommTurn": "300",                # 附录 2 给定：中继架次周转时间 / s
    "QthreeCompromiseSorties": "3",
    "QthreeCompromiseCoverPct": "55.5",
    "QthreeCompromiseUncoveredS": "5534",
    "QthreeCompromiseLongestS": "2446",
    "QthreeCompromiseOutagePhaseN": "3",
    "QthreeCompromiseOutagePhaseS": "6380",
    "QthreeCompromiseCoverRate": "96.2",
    "QthreeCompromiseEnergy": "2.26",
    "QthreeCompromiseHover": "4860",
    "QthreeRelayHoverLike": "4860",   # 库存口径下中继悬停合计 / s（= solution.json meta.relay_hover）
    "QthreeDpCells": "992",
    "QthreeDpInstances": "1454",
    "QthreeDpSingleCoverCells": "992",
    "QthreeDpCandPts": "2471",
    "QthreeDpMeanPts": "775",
    "QthreeDpPeakConcurrent": "3",
    "QthreeDpBlackoutMedianS": "1037",
    "QthreeDpBlackoutAirMedianS": "471",
    "QthreeDpBlackoutMeanS": "1041",
    "QthreeDpBlackoutMinS": "308",
    "QthreeDpBlackoutMaxS": "2171",
    "QthreeDpBlackoutGePct": "38.3",   # 黑障窗口 ≥ 1100 s 的点对占比 / %
    "QthreeDpBlackoutPairs": "42230",  # Mode 1 全候选点对数（黑障按精确秒数，无 W_max 截断）
    "QthreeDpCandPairs": "6103370",    # 候选悬停点的无序点对数
    "QthreeDpPhases": "6",
    "QthreeDpShortPhases": "3",
    "QthreeDpShortPhaseMinS": "440",
    "QthreeDpInfeasibleCell": "171",
    "QthreeDpInfeasibleT": "2420",
    "QthreeNeedN": "3",
    "QthreeGapN": "1",
    "QthreeNThreeSorties": "7",
    "QthreeNThreeSortiesCell": "7（已含换组件拆分）",
    "QthreeNThreeSortiesSplit": "7",
    "QthreeNThreeCoverCells": "992",
    "QthreeNThreeConflicts": "0",
    "QthreeNThreeMiss": "0",
    "QthreeNThreeMaxHoverS": "7210",
    "QthreeEnergyCap": "7233",             # 一组能源组件的等效可用悬停时长 / s
    "QthreeDpTZero": "710",                # 第 0 个需求时刻 / s
    # ---- 换位模式对比 / 候选集稳健性（由 results/*.json 覆盖）----
    "QthreeWBaseMedS": "1035", "QthreeWAirMedS": "471",
    "QthreeWBaseStrongS": "1065", "QthreeWAirStrongS": "190",
    "QthreeStarBasePct": "59.3", "QthreeStarAirPct": "85.7",
    "QthreeStarBaseStrongPct": "58.1", "QthreeStarAirStrongPct": "97.1",
    "QthreeFailBaseT": "2420", "QthreeFailAirT": "3950",
    "QthreeFailCellHigh": "225", "QthreeFailCellLow": "171",
    "QthreeNGreedySorties": "6", "QthreeNGreedyEnergy": "7.66",
    "QthreeNGreedySocMin": "21.2",
    "QthreeRejUnionPct": "100", "QthreeRejArrivalPct": "47.4",
    "QthreeNThreeEnergy": "10.36",         # 3 架方案（含换组件拆分）总能耗 / kWh
    # ---- 通信中断时长的三种统计口径（务必在正文中逐处标注，避免混用）----
    "CommNoneSegS": "7950",                # 口径 A：按阶段边界精确切分（结果提交表 Q3_通信保障）
    "CommNoneSampleS": "8050",             # 口径 B：5 s 采样、逐架次求和（独立校验器）
    "CommNoneUnionS": "5534",              # 口径 C：全体时刻并集（任一时刻至少一架中断）
    "QthreeNThreeHoverS": "28990",         # 3 架方案（含换组件拆分）悬停合计 / s
}

Q3GAP_GROUPS = [
    ("\u24e0 \u4e2d\u7ee7\u65f6\u5e8f\u53c2\u6570\uff08\u9644\u5f55 2 \u7ed9\u5b9a\u503c\uff0c\u4f9b\u5047\u8bbe A13 \u5f15\u7528\uff09",
     ["CommLink", "CommTurn"]),
    ("\u2460 2 \u67b6\u4e2d\u7ee7\u6298\u4e2d\u65b9\u6848\uff08\u5e93\u5b58\u7ea6\u675f\u4e0b\u7684\u6700\u4f18\u6298\u4e2d\uff0c\u5373 solution.json \u7684 relay \u5b57\u6bb5\uff09",
     ["QthreeCompromiseSorties", "QthreeCompromiseCoverPct",
      "QthreeCompromiseUncoveredS", "QthreeCompromiseLongestS",
      "QthreeCompromiseCoverRate", "QthreeCompromiseEnergy",
      "QthreeCompromiseHover", "QthreeRelayHoverLike",
      "QthreeCompromiseOutagePhaseN", "QthreeCompromiseOutagePhaseS"]),
    ("\u2461 N = 2 \u7684\u4e0d\u53ef\u884c\u6027\uff08\u72b6\u6001 DP \u5224\u5b9a\uff1b\u53ea\u80fd\u4e3b\u5f20\u300c\u5728\u7ed9\u5b9a\u5019\u9009\u96c6\u4e0e\u526a\u679d\u4e0b\u672a\u627e\u5230\u53ef\u884c\u89e3\u300d\uff09",
     ["QthreeDpCells", "QthreeDpInstances", "QthreeDpSingleCoverCells",
      "QthreeDpCandPts", "QthreeDpCandPairs", "QthreeDpMeanPts",
      "QthreeDpPeakConcurrent", "QthreeDpBlackoutMedianS",
      "QthreeDpBlackoutAirMedianS",
      "QthreeDpBlackoutMeanS", "QthreeDpBlackoutMinS",
      "QthreeDpBlackoutMaxS", "QthreeDpBlackoutGePct", "QthreeDpBlackoutPairs",
      "QthreeDpPhases", "QthreeDpShortPhases", "QthreeDpShortPhaseMinS",
      "QthreeDpInfeasibleCell", "QthreeDpInfeasibleT"]),
    ("\u2462 \u6700\u5c0f\u589e\u914d\u65b9\u6848\uff08N = 3\uff0c\u5168\u8986\u76d6\u3001\u96f6\u65f6\u5e8f\u51b2\u7a81\uff09",
     ["QthreeNeedN", "QthreeGapN", "QthreeNThreeSorties",
      "QthreeNThreeSortiesSplit", "QthreeNThreeEnergy", "QthreeNThreeHoverS",
      "QthreeNThreeCoverCells", "QthreeNThreeConflicts", "QthreeNThreeMiss",
      "QthreeNThreeMaxHoverS"]),
    ("\u2463 \u6362\u4f4d\u6a21\u5f0f\u5bf9\u6bd4\u4e0e\u5019\u9009\u96c6\u7a33\u5065\u6027",
     ["QthreeEnergyCap", "QthreeDpTZero",
      "QthreeWBaseMedS", "QthreeWAirMedS", "QthreeWBaseStrongS", "QthreeWAirStrongS",
      "QthreeStarBasePct", "QthreeStarAirPct",
      "QthreeStarBaseStrongPct", "QthreeStarAirStrongPct",
      "QthreeFailBaseT", "QthreeFailAirT", "QthreeFailCellLow", "QthreeFailCellHigh",
      "QthreeNGreedySorties", "QthreeNGreedyEnergy", "QthreeNGreedySocMin",
      "QthreeRejUnionPct", "QthreeRejArrivalPct"]),
    ("\u2464 \u901a\u4fe1\u4e2d\u65ad\u65f6\u957f\u7684\u4e09\u79cd\u7edf\u8ba1\u53e3\u5f84",
     ["CommNoneSegS", "CommNoneSampleS", "CommNoneUnionS"]),
]


def _flatten_groups():
    """由分组表派生 Q3GAP_ORDER，并把 Q3GAP 里未被分组的宏追加到末尾。"""
    out, seen = [], set()
    for _title, keys in Q3GAP_GROUPS:
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
    for k in Q3GAP:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


Q3GAP_ORDER = _flatten_groups()

# paper/q3_gap.tex 中每一行宏的用途注释（重写文件时按 Q3GAP_ORDER 重新插入）
Q3GAP_NOTE = {
    "CommLink": "⓪ 附录 2 给定：中继建链时间 / s",
    "CommTurn": "⓪ 附录 2 给定：中继架次周转时间 / s",
    "QthreeCompromiseSorties": "① 2 架中继折中方案：中继架次数",
    "QthreeCompromiseCoverPct": "① 2 架中继折中方案：失联时长覆盖率 / %",
    "QthreeCompromiseUncoveredS": "① 2 架中继折中方案：未覆盖的中断并集 / s（口径 C，与 CommNoneUnionS 同义）",
    "QthreeCompromiseOutagePhaseN": "① 2 架中继折中方案：未派中继的相位数 / 个",
    "QthreeCompromiseOutagePhaseS": "① 2 架中继折中方案：未派中继的相位时长之和 / s（口径不同于中断并集）",
    "QthreeCompromiseLongestS": "① 2 架中继折中方案：最长未覆盖中断段 / s",
    "QthreeCompromiseCoverRate": "① 2 架中继折中方案：单点可覆盖的需求实例比例 / %",
    "QthreeCompromiseEnergy": "① 2 架中继折中方案：中继总能耗 / kWh",
    "QthreeCompromiseHover": "① 2 架中继折中方案：悬停合计 / s",
    "QthreeRelayHoverLike": "① 库存口径下中继悬停合计 / s",
    "QthreeDpCells": "② N=2 不可行性：统一 10 s 栅格上的时间格数",
    "QthreeDpInstances": "② N=2 不可行性：「直连不可用」需求实例数",
    "QthreeDpSingleCoverCells": "② N=2 不可行性：能被某个悬停点单独覆盖的格数",
    "QthreeDpCandPts": "② N=2 不可行性：候选悬停点数",
    "QthreeDpMeanPts": "② N=2 不可行性：每个需求实例平均可选悬停点数",
    "QthreeDpPeakConcurrent": "② N=2 不可行性：同时失联运输机数上限",
    "QthreeDpBlackoutMedianS": "② N=2 不可行性：换位黑障窗口中位数 / s",
    "QthreeDpBlackoutMeanS": "② N=2 不可行性：换位黑障窗口平均 / s",
    "QthreeDpBlackoutMinS": "② N=2 不可行性：换位黑障窗口最小 / s",
    "QthreeDpBlackoutMaxS": "② N=2 不可行性：换位黑障窗口最大 / s",
    "QthreeDpBlackoutGePct": "② N=2 不可行性：黑障窗口 ≥ 1100 s 的点对占比 / %",
    "QthreeDpCandPairs": "② N=2 不可行性：候选悬停点无序点对数",
    "QthreeDpPhases": "② N=2 不可行性：中继相位数",
    "QthreeDpShortPhases": "② N=2 不可行性：短于 1400 s 的相位数",
    "QthreeDpShortPhaseMinS": "② N=2 不可行性：最短相位时长 / s",
    "QthreeDpInfeasibleCell": "② N=2 不可行性：首个无可行状态的时间格序号",
    "QthreeDpInfeasibleT": "② N=2 不可行性：该格对应时刻 / s",
    "QthreeNeedN": "③ 最小增配：达成全程连续通信所需中继台数",
    "QthreeGapN": "③ 最小增配：相对库存 2 架的中继无人机缺口 / 架",
    "QthreeNThreeSorties": "③ 最小增配：N=3 原始中继架次数",
    "QthreeNThreeSortiesCell": "③ 最小增配：对比表用「架次数」单元格文本",
    "QthreeNThreeSortiesSplit": "③ 最小增配：换能源组件拆分后的架次数",
    "QthreeNThreeCoverCells": "③ 最小增配：N=3 解可覆盖的时间格数",
    "QthreeNThreeConflicts": "③ 最小增配：N=3 解时序冲突数",
    "QthreeNThreeMiss": "③ 最小增配：N=3 解未覆盖需求实例数",
    "QthreeNThreeMaxHoverS": "③ 最小增配：N=3 解单架次最大悬停时长 / s",
    "QthreeNThreeEnergy": "③ 最小增配：换组件拆分后中继总能耗 / kWh",
    "QthreeNThreeHoverS": "③ 最小增配：换组件拆分后悬停合计 / s",
}


def _q3gap_from_file() -> Dict[str, str]:
    """读取 paper/q3_gap.tex 中已存在的宏值。

    **只补默认表里还没有的值（即默认值为占位符的宏）**——否则上一轮的产物会把
    本轮应由结果文件刷新的数字"锁死"，使错误自我延续（例如「中断并集」被
    「未派中继相位时长之和」覆盖后再也回不来）。
    """
    out: Dict[str, str] = {}
    try:
        if not os.path.exists(Q3GAP_FILE):
            return out
        import re
        with open(Q3GAP_FILE, "r", encoding="utf-8") as f:
            txt = f.read()
        for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{([^}]*)\}", txt):
            name, val = m.group(1), m.group(2)
            if not (name in Q3GAP and val and val != PLACEHOLDER):
                continue
            if str(Q3GAP.get(name, PLACEHOLDER)).strip() in ("", PLACEHOLDER):
                out[name] = val          # 默认表空缺 → 允许沿用上一轮的值
    except Exception as e:
        log("! q3_gap.tex 回读失败：%s" % e)
    return out


def _q3gap_from_summary() -> Dict[str, str]:
    """从 results/Q3_方案汇总.json 读取（q3refresh.py 产出）——**最高优先级**。

    该文件是问题三结构性数字的唯一权威来源，避免解析过期运行日志
    （_q3final.log 等）而把旧物理模型下的数字写进论文。
    """
    js = read_json("Q3_方案汇总.json") or {}
    if not js:
        return {}
    out: Dict[str, str] = {}
    st = js.get("struct") or {}
    mp = {"cand_pts": "QthreeDpCandPts", "instances": "QthreeDpInstances",
          "cells": "QthreeDpCells", "peak_concurrent": "QthreeDpPeakConcurrent",
          "single_cover_cells": "QthreeDpSingleCoverCells", "mean_pts": "QthreeDpMeanPts",
          "phases": "QthreeDpPhases", "short_phases": "QthreeDpShortPhases",
          "min_phase_s": "QthreeDpShortPhaseMinS", "energy_cap_s": "QthreeEnergyCap"}
    for k, macro in mp.items():
        v = st.get(k)
        if v is None:
            continue
        if isinstance(v, float) and abs(v - round(v)) > 1e-9:
            out[macro] = "%.1f" % v
        else:
            out[macro] = "%d" % int(round(float(v)))
    n2 = js.get("n2") or {}
    if n2:
        out["QthreeCompromiseSorties"] = str(int(n2.get("sorties", 0)))
        # 注意口径：QthreeCompromiseUncoveredS 是「中断**并集**」（口径 C），
        # 与 CommNoneUnionS 同义；n2.outage_s 是「未派中继的相位时长之和」（口径不同），
        # 因此这里**不**用它覆盖，另立宏 QthreeCompromiseOutagePhaseS 单独记录。
        if n2.get("cover_pct") is not None:
            out["QthreeCompromiseCoverPct"] = "%.1f" % float(n2["cover_pct"])
        out["QthreeCompromiseHover"] = "%.0f" % float(n2.get("hover", 0.0))
        out["QthreeCompromiseEnergy"] = "%.2f" % float(n2.get("energy", 0.0))
        out["QthreeCompromiseOutagePhaseS"] = "%.0f" % float(n2.get("outage_s", 0.0))
        out["QthreeCompromiseOutagePhaseN"] = str(int(n2.get("outage_n", 0)))
    n3 = js.get("n3") or {}
    if n3:
        out["QthreeNeedN"] = "3"
        out["QthreeGapN"] = "1"
        out["QthreeNThreeSorties"] = str(int(n3.get("sorties", 0)))
        out["QthreeNThreeSortiesSplit"] = str(int(n3.get("sorties", 0)))
        out["QthreeNThreeSortiesCell"] = "%d（已满足组件容量，无需再拆分）" % int(n3.get("sorties", 0))
        out["QthreeNThreeConflicts"] = str(int(n3.get("timing_conflicts") or 0))
        out["QthreeNThreeMiss"] = str(int(n3.get("miss") or 0))
        out["QthreeNThreeEnergy"] = "%.2f" % float(n3.get("energy", 0.0))
        out["QthreeNThreeHoverS"] = "%.0f" % float(n3.get("hover", 0.0))
        # 构造性贪心（与 relay3 为同一方案，是"3 架可行"的可行性证据）的三项指标
        out["QthreeNGreedySorties"] = str(int(n3.get("sorties", 0)))
        out["QthreeNGreedyEnergy"] = "%.2f" % float(n3.get("energy", 0.0))
        if n3.get("soc_min") is not None:
            out["QthreeNGreedySocMin"] = "%.1f" % float(n3["soc_min"])
        if n3.get("max_hover") is not None:
            out["QthreeNThreeMaxHoverS"] = "%.0f" % float(n3["max_hover"])
        if n3.get("soc_min") is not None:
            out["QthreeNThreeSocMin"] = "%.1f" % float(n3["soc_min"])
    if out:
        log("· q3_gap 汇总 JSON 读取成功：%d 个宏（来源 results/Q3_方案汇总.json）" % len(out))
    return out


def _q3gap_from_diag() -> Dict[str, str]:
    """从 results/Q3_诊断汇总.json（q3diag.py 产出）读取诊断类宏。

    该文件只由**结果文件**合并而成，不含日志解析，故优先级高于 `_q3gap_from_log`
    （审阅 #28：切断"过期日志污染论文"的路径）。
    """
    js = read_json("Q3_诊断汇总.json") or {}
    v = js.get("values") or {}
    if not v:
        return {}
    keep = ("QthreeDpInfeasibleCell", "QthreeDpInfeasibleT", "QthreeFailCellLow",
            "QthreeFailCellHigh", "QthreeFailBaseT", "QthreeFailAirT",
            "QthreeSpanBlackoutBasePct", "QthreeSpanBlackoutAirPct",
            "QthreeSpanDeficitBaseS", "QthreeSpanDeficitAirS",
            "QthreeDpBlackoutMedianS", "QthreeDpBlackoutAirMedianS",
            "QthreeDpBlackoutMinS", "QthreeDpBlackoutMeanS",
            "QthreeDpBlackoutMaxS", "QthreeDpBlackoutGePct", "QthreeDpBlackoutPairs",
            "QthreeBlackoutBaseMedianS", "QthreeBlackoutAirMedianS",
            "QthreeWBaseMedS", "QthreeWAirMedS",
            "QthreeWBaseStrongS", "QthreeWAirStrongS",
            "QthreeStarBasePct", "QthreeStarAirPct",
            "QthreeStarBaseStrongPct", "QthreeStarAirStrongPct",
            "QthreeHoverCapS")
    out: Dict[str, str] = {}
    for k in keep:
        if v.get(k) is None:
            continue
        val = v[k]
        if isinstance(val, float) and abs(val - round(val)) > 1e-9:
            out[k] = "%.1f" % val
        else:
            out[k] = "%d" % int(round(float(val)))
    if out:
        log("· q3_gap 诊断汇总读取成功：%d 个宏（来源 results/Q3_诊断汇总.json）" % len(out))
    return out


def _q3gap_from_log() -> Dict[str, str]:
    """从 results/ 或仓库根目录的运行日志中刷新 DP 的结构性数字（只在解析成功时覆盖）。"""
    import re
    cands = [os.path.join(OUT, "_q3final.log"),
             os.path.join(os.path.dirname(BASE), "_q3final.log"),
             os.path.join(BASE, "_q3final.log")]
    out: Dict[str, str] = {}
    for p in cands:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except Exception:
            continue
        pats = [
            ("QthreeDpCandPts", r"候选悬停点\s*(\d+)\s*个"),
            ("QthreeDpInstances", r"需求实例\s*(\d+)"),
            ("QthreeDpCells", r"时间格\s*(\d+)"),
            ("QthreeDpPeakConcurrent", r"最多\s*(\d+)\s*架同时失联"),
            ("QthreeDpSingleCoverCells", r"单点可覆盖格\s*(\d+)"),
            ("QthreeDpMeanPts", r"每实例平均可选\s*(\d+)\s*点"),
            ("QthreeDpPhases", r"相数\s*=\s*(\d+)"),
            ("QthreeDpShortPhases", r"短于\s*1400\s*s\s*的相\s*(\d+)\s*个"),
            ("QthreeDpShortPhaseMinS", r"最短相\s*(\d+)\s*s"),
            ("QthreeDpInfeasibleCell", r"第\s*(\d+)\s*格"),
            ("QthreeDpInfeasibleT", r"t\s*=\s*(\d+)\s*s）无可行状态"),
        ]
        for key, pat in pats:
            m = re.search(pat, txt)
            if m:
                out[key] = m.group(1)
        m = re.search(r"N=3：中继架次\s*(\d+)\s*个", txt)
        if m:
            out["QthreeNThreeSorties"] = m.group(1)
        m = re.search(r"时序冲突\s*(\d+)", txt)
        if m:
            out["QthreeNThreeConflicts"] = m.group(1)
        m = re.search(r"未覆盖实例\s*(\d+)/(\d+)", txt)
        if m:
            out["QthreeNThreeMiss"] = m.group(1)
            out["QthreeDpInstances"] = m.group(2)
        m = re.search(r"最大悬停\s*(\d+)\s*s", txt)
        if m:
            out["QthreeNThreeMaxHoverS"] = m.group(1)
        if out:
            log("· q3_gap 日志解析成功：%s（来源 %s）" % (len(out), os.path.basename(p)))
            break
    return out


def _q3gap_from_solution() -> Dict[str, str]:
    """从结果文件刷新「中继资源缺口」的数字。"""
    import re
    out: Dict[str, str] = {}
    js = read_json("solution.json") or {}
    meta = js.get("meta") or {}
    rl = js.get("relay") or []
    if rl:
        out["QthreeCompromiseSorties"] = str(len(rl))
        es = [float(r.get("e_total", 0.0)) for r in rl]
        hs = [float(r.get("hover", 0.0)) for r in rl]
        if any(es):
            out["QthreeCompromiseEnergy"] = "%.2f" % sum(es)
        if any(hs):
            out["QthreeCompromiseHover"] = "%.0f" % sum(hs)
    if meta.get("relay_hover") is not None:
        try:
            out["QthreeRelayHoverLike"] = "%.0f" % float(meta["relay_hover"])
        except Exception:
            pass
    if meta.get("cover_rate") is not None:
        try:
            out["QthreeCompromiseCoverRate"] = "%.1f" % (100.0 * float(meta["cover_rate"]))
        except Exception:
            pass
    if meta.get("uncov_time") is not None:
        # 需求实例级未覆盖时长（solution.json 的 meta.uncov_time）；
        # 折中方案的「中继未覆盖的中断并集」以 results/检查说明.md 第 9 项为准，
        # 该值不等于实例级统计量，故此处只记录不覆盖。
        try:
            float(meta["uncov_time"])
        except Exception:
            pass
    r3 = js.get("relay3") or []
    if r3:
        out["QthreeNThreeSortiesSplit"] = str(len(r3))
        # 状态 DP 已内置"单次驻留/在空时长不得超过一组能源组件容量"的状态过滤，
        # 因此 split 后的架次数即为 DP 直接输出的架次数（本算例两者相等，无需额外拆分）。
        out["QthreeNThreeSorties"] = str(len(r3))
        out["QthreeNThreeSortiesCell"] = "%d（已满足组件容量，无需再拆分）" % len(r3)
        out["QthreeNThreeMiss"] = "0"
        try:
            out["QthreeNThreeEnergy"] = "%.2f" % sum(float(r.get("e_total", 0.0)) for r in r3)
        except Exception:
            pass
        try:
            out["QthreeNThreeHoverS"] = "%.0f" % sum(float(r.get("hover", 0.0)) for r in r3)
        except Exception:
            pass
    ra = meta.get("relay_analysis") or {}
    if ra:
        out["QthreeNeedN"] = str(int(ra.get("n_relay_required", 3)))
        if ra.get("n2_feasible") is not None and not ra.get("n2_feasible"):
            pass  # N=2 不可行 —— 与默认口径一致
        m = re.search(r"第\s*(\d+)\s*格", str(ra.get("n2_msg") or ""))
        if m:
            out["QthreeDpInfeasibleCell"] = m.group(1)
        m2 = re.search(r"t\s*=\s*(\d+)", str(ra.get("n2_msg") or ""))
        if m2:
            out["QthreeDpInfeasibleT"] = m2.group(1)
        for src, dst in (("n3_sorties", "QthreeNThreeSortiesSplit"),
                         ("n3_timing_conflicts", "QthreeNThreeConflicts"),
                         ("n3_miss", "QthreeNThreeMiss")):
            if ra.get(src) is not None:
                out[dst] = str(int(ra[src]))
    return out


def append_q3gap() -> None:
    """写出 paper/q3_gap.tex —— 问题三中继资源缺口的数字宏。

    合并优先级：已核实默认值 < 现有 q3_gap.tex 回读值 < 运行日志 < 结果文件。
    """
    import re
    # 这些宏只在 q3_gap.tex 中定义，避免 numbers.tex 重复定义导致 LaTeX 报错
    for k in Q3GAP_ORDER:
        NUM.pop(k, None)
    vals = dict(Q3GAP)
    vals.update(_q3gap_from_file())
    # 说明（审阅 #28）：早期版本会解析运行日志 _q3final.log 来补数字，日志一旦过期
    # 就会把旧物理模型下的值写进论文。现已在**结果文件**侧补齐全部 64 个宏
    # （Q3_方案汇总.json + Q3_诊断汇总.json + 结果提交.xlsx + 检查说明.md），
    # 实测移除日志解析后 q3_gap.tex 逐字节不变，故**不再解析任何日志**。
    # _q3gap_from_log() 保留在文件中仅作历史参考，不再调用。
    try:
        vals.update(_q3gap_from_solution())
    except Exception as e:
        log("! q3_gap 结果文件刷新失败：%s" % e)
    # 最高优先级：q3refresh.py 产出的汇总 JSON（最新物理模型下的权威值）
    try:
        vals.update(_q3gap_from_summary())
    except Exception as e:
        log("! q3_gap 汇总 JSON 刷新失败：%s" % e)
    # 次高优先级：q3diag.py 合并的**结果文件**诊断汇总（不依赖日志）
    try:
        vals.update(_q3gap_from_diag())
    except Exception as e:
        log("! q3_gap 诊断汇总刷新失败：%s" % e)
    # 回读自身生成的 q3_gap.tex 只应用于「默认表里没有的值」，
    # 不能让上一轮的产物覆盖本轮结果（否则错误会自我延续）。
    if "QthreeNThreeMaxHoverS" in vals and vals["QthreeNThreeMaxHoverS"] == "7210":
        log("! 检测到 q3_gap 单架次最大悬停仍为过期的 7210 s，"
            "请先运行 python q3refresh.py 生成 results/Q3_方案汇总.json")
    # 若在输入中显式登记了同名宏，以输入登记值为准
    for k in list(vals):
        if k in NUM:
            vals[k] = NUM[k]
    # 关键防护：解析结果若退化成占位符，而默认表里有已核实的结论值，则以默认值为准，
    # 避免"回读自身生成的占位文件"把已核实数字覆盖掉。
    _from_result = set(vals)                       # 本轮由结果文件/日志刷出来的宏
    for k, dv in Q3GAP.items():
        if str(vals.get(k, "")).strip() in ("", PLACEHOLDER) and dv != PLACEHOLDER:
            vals[k] = dv
    # 审计（审阅 #28）：逐宏标注数值来源，凡"未由本轮结果刷新、只能沿用内置默认值"的，
    # 一律显式告警并写入审计文件，避免把内置默认值误读为"本次运行证明出来的结论"。
    _fallback = sorted(k for k in Q3GAP_ORDER
                       if k not in _from_result and str(vals.get(k, "")).strip() != PLACEHOLDER)
    if _fallback:
        log("! 下列 %d 个宏未能由结果文件刷新，沿用内置默认值（请核对是否与最新结果一致）：%s"
            % (len(_fallback), "、".join(_fallback)))
    try:
        _audit = os.path.join(PAPER, "q3_gap_sources.txt")
        with open(_audit, "w", encoding="utf-8") as f:
            f.write("# q3_gap.tex 各宏数值来源审计（由 make_numbers.py 生成）\n")
            f.write("# 生成时间：%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("# 说明：\"结果刷新\"= 本轮由 results/*.json、结果提交.xlsx、检查说明.md 刷新；\n")
            f.write("#       \"内置默认\"= 结果文件缺失，沿用脚本内置的已核实值（须人工复核）。\n")
            f.write("%-38s %-10s %s\n" % ("宏名", "来源", "当前值"))
            for k in Q3GAP_ORDER:
                src = "内置默认" if k in _fallback else "结果刷新"
                f.write("%-38s %-10s %s\n" % (k, src, vals.get(k, PLACEHOLDER)))
        log("· 已写出 %s（结果刷新 %d 个 / 内置默认 %d 个）"
            % (os.path.basename(_audit), len(Q3GAP_ORDER) - len(_fallback), len(_fallback)))
    except Exception as e:                                        # noqa: BLE001
        log("! 来源审计文件写出失败：%r" % (e,))

    L: List[str] = []
    A = L.append
    A("%% q3_gap.tex —— 问题三「中继资源缺口」专用数字宏")
    A("%%   由 code/make_numbers.py 的 append_q3gap() 自动生成（运行 make_numbers.py 会覆盖本文件）。")
    A("%%   正文只引用宏，不硬编码；数据源未产出时保留已核实的默认结论值或写「待补」。")
    A("%%   与 numbers.tex 分文件，是为了让「问题三判定性结论」的数字可单独刷新、单独审计。")
    A("")
    groups = Q3GAP_GROUPS
    seen = set()
    for title, keys in groups:
        A("%% ---- %s" % title)
        for k in keys:
            seen.add(k)
            A("\\newcommand{\\%s}{%s}" % (k, vals.get(k, PLACEHOLDER)))
        A("")
    for k in Q3GAP_ORDER:            # 兜底：确保无遗漏
        if k not in seen:
            A("\\newcommand{\\%s}{%s}" % (k, vals.get(k, PLACEHOLDER)))
    with open(Q3GAP_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    miss = [k for k in Q3GAP_ORDER if vals.get(k) == PLACEHOLDER]
    log("· 已写出 paper/q3_gap.tex（%d 个宏，占位 %d 个%s）"
        % (len(Q3GAP_ORDER), len(miss), ("：" + ", ".join(miss)) if miss else ""))


# ===========================================================================
# 5. 表格
# ===========================================================================
def write_tables(d, base, q1df) -> None:
    L: List[str] = []
    A = L.append

    def table(caption, label, header, rows, align=None, size=r"\small", fit=False, note=None):
        A(r"\begin{table}[htbp]")
        A(r"\centering")
        A(r"\caption{%s}" % caption)
        A(r"\label{%s}" % label)
        A(size)
        env = "tabular"
        if fit:
            # 列数多、易溢出页宽的表：缩放到 \linewidth（审阅 #26：交付版不得有 Overfull 表）
            A(r"\resizebox{\linewidth}{!}{%")
        A(r"\begin{%s}{%s}" % (env, align or ("l" + "c" * (len(header) - 1))))
        A(r"\toprule")
        A(" & ".join(header) + r" \\")
        A(r"\midrule")
        for r in rows:
            A(" & ".join(str(x) for x in r) + r" \\")
        A(r"\bottomrule")
        A(r"\end{%s}" % env)
        if fit:
            A(r"}")
        if note:
            A(r"\\[2pt] \footnotesize %s" % note)
        A(r"\end{table}")
        A("")

    # --- 表 1 节点 ---
    rows = []
    nodes = d["nodes"]
    o = nodes["O01"]
    rows.append(["O01", TEX(o.name), "%.4f" % o.lon, "%.4f" % o.lat, "%.1f" % o.elev,
                 "—", "—", "%.2f" % 0.0])
    for sid in d["SIDS"]:
        nd = nodes[sid]
        dist = base["dists"][sid] / 1000.0
        dem_g = float(D.get_dem().at(nd.lon, nd.lat))
        gmax = D.get_dem().line_max(o.lon, o.lat, nd.lon, nd.lat)
        rows.append([sid, TEX(nd.name), "%.4f" % nd.lon, "%.4f" % nd.lat, "%.1f" % nd.elev,
                     "%d" % nd.pop, "%.1f" % dem_g, "%.2f" % dist])
    table(r"调度中心与服务区基础数据（海拔取附件给定值，DEM 值为 30\,m 栅格最近邻采样）",
          "tab:nodes",
          [r"编号", r"名称", r"经度/$^\circ$E", r"纬度/$^\circ$N",
           r"海拔/m", r"人口", r"DEM 高程/m", r"直线距离/km"],
          rows, align="llrrrrrr", size=r"\footnotesize", fit=True)

    # --- 表 2 机型参数 ---
    rows = []
    for g in ("A", "B", "C"):
        t = d["ttypes"][g]
        rows.append([g, TEX(t.name), "%.1f" % t.m_empty, "%.0f" % t.q_max, "%.3f" % t.v_cap,
                     "%.1f" % t.v_cruise, "%.1f" % (t.range_empty / 1000),
                     "%.1f" % (t.range_full / 1000), "%.1f" % t.e_use,
                     "%d" % len(d["fleet"][g]), "%d" % d["batt"][g][0],
                     "%.0f" % d["batt"][g][1]])
    rt = d["rtype"]
    rows.append(["R", TEX(rt.name), "%.1f" % rt.mtow, "—", "—", "%.1f" % rt.v_cruise,
                 "—", "—", "%.1f" % rt.e_use, "%d" % len(d["rfleet"]),
                 "%d" % d["rbatt"][0], "%.0f" % d["rbatt"][1]])
    table(r"运输无人机 A/B/C 与中继无人机 R 的主要参数（$m_0$ 为含电池空载质量）",
          "tab:types",
          [r"机型", r"名称", r"$m_0$/kg", r"$Q$/kg", r"$V$/m$^3$", r"$v_c$/(m$\cdot$s$^{-1}$)",
           r"$L^0$/km", r"$L^F$/km", r"$E^{\rm use}$/kWh", r"架数", r"电池数",
           r"$T_{\rm full}$/s"],
          rows, align="llrrrrrrrrrr", size=r"\footnotesize", fit=True)

    # --- 表 3 最大安全载荷 ---
    if q1df is not None and len(q1df):
        rows = []
        for sid in d["SIDS"]:
            r = [sid]
            for g in ("A", "B", "C"):
                sub = q1df[(q1df["服务区编号"] == sid) & (q1df["机型编号"] == g)]
                if len(sub):
                    v = float(sub["最大安全载荷_kg"].iloc[0])
                    lim = bool(sub["是否受能量限制"].iloc[0])
                    r.append("%.1f%s" % (v, r"$^{*}$" if lim else ""))
                else:
                    r.append("—")
            rows.append(r)
        table(r"三机型在 15 个服务区的最大安全载荷（kg，$\rho=20\%$；$^{*}$ 表示受返航能量限制而非载重限制）",
              "tab:payload",
              [r"服务区", r"A 型", r"B 型", r"C 型"], rows,
              align="lrrr", size=r"\footnotesize")

    # --- 表 4 Q1 具名方案 ---
    xl_p = os.path.join(OUT, "Q1_单点组批.xlsx")
    if os.path.exists(xl_p):
        try:
            xl = pd.ExcelFile(xl_p)
            rows = []
            for sn in xl.sheet_names:
                s = xl.parse(sn)
                if "架次能耗_kWh" not in s.columns:
                    continue
                n = len(s)
                E = float(s["架次能耗_kWh"].sum())
                T = float(s["往返时间_s"].sum()) if "往返时间_s" in s.columns else float("nan")
                q = float(s["质量占用率"].mean()) if "质量占用率" in s.columns else float("nan")
                v = float(s["体积占用率"].mean()) if "体积占用率" in s.columns else float("nan")
                rows.append([TEX(sn), "%d" % n, "%.2f" % E, "%.2f" % (T / 3600.0),
                             "%.3f" % q, "%.3f" % v])
            if rows:
                table(r"问题一五个具名组批方案的指标对比（累计作业时间为各架次时长之和）",
                      "tab:q1schemes",
                      [r"方案", r"架次数", r"总能耗/kWh", r"累计工时/h",
                       r"平均质量占用率", r"平均体积占用率"],
                      rows, align="lrrrrr", size=r"\footnotesize", fit=True)
        except Exception as e:
            log("! 表 4 生成失败：%s" % e)

    # --- 表 5 rho 灵敏度 ---
    sen = read_xlsx("Q1_灵敏度.xlsx")
    if sen is not None and len(sen):
        rows = []
        for _, r in sen.iterrows():
            rows.append([
                "%.0f\\%%" % (100 * float(r["返航安全余量比例"])),
                "%.1f" % float(r.get("A型最大安全载荷均值_kg", float("nan"))),
                "%.1f" % float(r.get("B型最大安全载荷均值_kg", float("nan"))),
                "%.1f" % float(r.get("C型最大安全载荷均值_kg", float("nan"))),
                "%s" % (int(r["C型受限服务区数"]) if r.get("C型受限服务区数") == r.get("C型受限服务区数") else "—"),
                "%s" % (int(r["最少架次数"]) if r.get("最少架次数") == r.get("最少架次数") else "不可行"),
                ("%.2f" % float(r["最少架次方案总能耗_kWh"]))
                if r.get("最少架次方案总能耗_kWh") == r.get("最少架次方案总能耗_kWh") else "不可行",
            ])
        table(r"返航安全余量 $\rho$ 灵敏度：载荷上限与全场景架次数"
              r"（「不可行」表示该 $\rho$ 下 S004/S008 连空载往返都不满足能量约束，全场景无可行组批方案）",
              "tab:rho",
              [r"$\rho$", r"A 型均值/kg", r"B 型均值/kg", r"C 型均值/kg",
               r"C 型受限区数", r"最少架次数", r"总能耗/kWh"],
              rows, align="lrrrrrr", size=r"\footnotesize")

    # --- 表 6 Q2 方案对比 ---
    raw = read_json("Q2_raw.json") or {}
    summ = raw.get("summary") or {}
    if summ:
        WTXT = {
            "P1-架次优先": "4:1:1:1",
            "P2-及时优先": "0.5:1:0.5:6",
            "P3-能耗优先": "1:6:1:1",
            "P4-完工优先": "0.5:0.5:6:1",
            "P5-均衡": "1.5:2:2:2",
        }
        rows = []
        for nm, v in sorted(summ.items(), key=lambda kv: kv[1].get("count", 0)):
            rows.append([TEX(nm), WTXT.get(nm, "—"), "%d" % int(v.get("count", 0)),
                         "%.2f" % float(v.get("energy", 0)),
                         "%.2f" % (float(v.get("makespan", 0)) / 3600.0),
                         "%.2f" % (float(v.get("tardiness", 0)) / 3600.0),
                         "%.1f\\%%" % (100 * float(v.get("ontime_rate", 0))),
                         "%d" % int(v.get("nbox", 0)),
                         "%.0f" % float(v.get("hard_violation", 0))])
        table(r"问题二五种权重配置的 ALNS + CP-SAT 求解结果对比",
              "tab:q2configs",
              [r"方案", r"权重$^*$", r"架次数", r"能耗/kWh", r"完工时间/h", r"延误量/h",
               r"及时率", r"覆盖箱数", r"硬约束违反"],
              rows, align="lrrrrrrrr", size=r"\footnotesize", fit=True,
              note=r"$^*$ 权重顺序为「架次数 : 能耗 : 完工时间 : 加权延误」。"
                   r"五组权重下得到的均为**非支配解**，不构成全局 Pareto 前沿的证明。")

    # --- 表 7 Q3 中继架次 ---
    sol = F.load_solution()
    rl = sol.get("relay") or []
    if rl:
        rows = []
        tot = 0.0
        for r in sorted(rl, key=lambda x: float(x.get("depart", 0))):
            tot += float(r.get("e_total", 0))
            rows.append([TEX(r.get("sid")), TEX(r.get("drone")), TEX(r.get("comp")),
                         "%.4f" % float(r.get("lon", 0)), "%.4f" % float(r.get("lat", 0)),
                         "%.0f" % float(r.get("hover_alt", 0)), "%.0f" % float(r.get("agl", 0)),
                         "%.0f" % float(r.get("depart", 0)), "%.0f" % float(r.get("link_done", 0)),
                         "%.0f" % float(r.get("end", 0)), "%.0f" % float(r.get("back", 0)),
                         "%.2f" % float(r.get("e_total", 0))])
        table(r"问题三中继架次明细 —— \textbf{库存口径（2 架中继）下的最优折中方案}，共 %d 个架次；"
              r"达成全程连续通信所需的 3 架增配方案见 results/结果提交.xlsx 的"
              r"「Q3\_中继架次\_增配方案」表" % len(rl),
              "tab:q3relay",
              [r"编号", r"中继机", r"能源组件", r"悬停经度", r"悬停纬度", r"悬停海拔/m",
               r"离地/m", r"起飞/s", r"建链/s", r"服务结束/s", r"返航/s", r"能耗/kWh"],
              rows, align="lllrrrrrrrrr", size=r"\scriptsize", fit=True)

    # --- 表 8 Q1 复算/校验 ---
    chk = os.path.join(OUT, "Q1_复算报告.txt")
    if os.path.exists(chk):
        try:
            with open(chk, "r", encoding="utf-8") as f:
                txt = f.read().strip().replace("\n", "；")
            A(r"\begin{table}[htbp]\centering")
            A(r"\caption{问题一组批方案复算校验报告（results/Q1\_复算报告.txt）}")
            A(r"\label{tab:q1check}")
            A(r"\small")
            A(r"\begin{tabular}{l}")
            A(r"\toprule")
            A(TEX(txt) + r" \\")
            A(r"\bottomrule")
            A(r"\end{tabular}")
            A(r"\end{table}")
            A("")
        except Exception:
            pass

    # --- 表 9 符号说明 ---
    sym = [
        (r"$G$", r"重力加速度，取 9.80665 m/s$^2$"),
        (r"$q$", r"架次装载质量（kg）"),
        (r"$Q_g$", r"机型 $g$ 的最大载货质量（kg）"),
        (r"$L_g(q)$", r"机型 $g$ 在载荷 $q$ 下的等效航程（m）"),
        (r"$E_g^{\rm use}$", r"机型 $g$ 单组电池可用能量（kWh）"),
        (r"$E^{\rm hor}$", r"航段水平飞行能耗（kWh）"),
        (r"$E^{\rm up}$", r"航段爬升附加能耗（kWh）"),
        (r"$\eta_{\rm up}$", r"爬升能耗效率，取 0.72"),
        (r"$h^{+},h^{-}$", r"航段爬升/下降高度（m）"),
        (r"$v_c,v_{\uparrow},v_{\downarrow}$", r"巡航/爬升/下降速度（m/s）"),
        (r"$\rho_g$", r"返航安全余量比例，三种运输机型均取 20\%"),
        (r"$P_{\rm th}$", r"接收门限（dBm），$P_{\rm th}=P_{\rm sens}+M=-90$ dBm"),
        (r"$L_{\max}^{a\to b}$", r"链路 $a\to b$ 的最大允许传播损耗（dB）"),
        (r"$L_{\rm obs}$", r"地形遮挡附加损耗（dB），取 10 dB"),
        (r"$\Delta$", r"航迹与链路的采样步长（s 或 m）"),
        (r"$x_{k,a}$", r"架次 $k$ 是否访问服务区 $a$ 的 0--1 变量"),
    ]
    rows = [[a, b] for a, b in sym]
    table(r"论文主要符号说明", "tab:symbols", [r"符号", r"含义"], rows,
          align="lp{11.5cm}", size=r"\small")

    with open(os.path.join(PAPER, "tables.tex"), "w", encoding="utf-8") as f:
        f.write("% !TeX root = paper.tex\n")
        f.write("% tables.tex —— 由 code/make_numbers.py 自动生成，请勿手工修改\n")
        f.write("\n".join(L) + "\n")
    log("· 已写出 paper/tables.tex（%d 行）" % len(L))


# ===========================================================================
def main() -> int:
    log("=" * 74)
    log("make_numbers.py —— 生成 paper/numbers.tex 与 paper/tables.tex")
    try:
        d = D.load_all()
    except Exception as e:
        log("!! 基础数据装载失败：%s" % e)
        flush()
        return 2
    try:
        base = collect_base(d)
    except Exception as e:
        log("! collect_base 失败：%s" % e)
        log(traceback.format_exc())
        base = dict(kinds=[], dists={s: 0.0 for s in d["SIDS"]})

    q1df = None
    try:
        q1df = collect_q1(d)
    except Exception as e:
        log("! collect_q1 失败：%s" % e)
        log(traceback.format_exc())
    try:
        collect_q2(d)
    except Exception as e:
        log("! collect_q2 失败：%s" % e)
        log(traceback.format_exc())
    sol = {"transport": [], "relay": [], "src": ""}
    try:
        sol = F.load_solution()
        collect_q3(d, sol)
    except Exception as e:
        log("! collect_q3 失败：%s" % e)
        log(traceback.format_exc())
    try:
        collect_check()
    except Exception as e:
        log("! collect_check 失败：%s" % e)
        log(traceback.format_exc())
    try:
        collect_q4(d)
    except Exception as e:
        log("! collect_q4 失败：%s" % e)
        log(traceback.format_exc())
    try:
        collect_coverage(d)
    except Exception as e:
        log("! collect_coverage 失败：%s" % e)
        log(traceback.format_exc())

    # Q4 兜底占位
    for k in ("QfourKTwo", "QfourKThree", "QfourBlocks", "QfourBalance",
              "QfourGap", "QfourGapThree", "QfourSorties", "QfourKind"):
        NUM.setdefault(k, PLACEHOLDER)

    # 兜底：扫描 paper.tex，凡是以本文约定前缀开头、正文引用到的自定义宏一律补齐，
    # 避免因某个数据源缺失导致 "Undefined control sequence" 而整体编译失败。
    # 只认自己的前缀，绝不碰 \Big/\Large/\IfFileExists 等 LaTeX 内置命令。
    try:
        import re
        prefixes = ("Total", "Num", "Dem", "Elev", "Type", "Cargo", "First", "Node",
                    "Comm", "Rho", "Relay", "Check", "Qone", "Qtwo", "Qthree", "Qfour")
        tp = os.path.join(PAPER, "paper.tex")
        if os.path.exists(tp):
            with open(tp, "r", encoding="utf-8") as f:
                txt = f.read()
            for n in sorted(set(re.findall(r"\\([A-Z][A-Za-z0-9]*)", txt))):
                if not n.startswith(prefixes):
                    continue
                if any(ch.isdigit() for ch in n):
                    log("! 宏名 %s 含数字，TeX 无法调用，已忽略（请在正文改名）。" % n)
                    continue
                NUM.setdefault(n, PLACEHOLDER)
    except Exception as e:
        log("! 宏兜底扫描失败：%s" % e)

    # 问题三缺口的宏只在 paper/q3_gap.tex 中定义，从 numbers.tex 中剔除以免重复定义
    for _k in Q3GAP_ORDER:
        NUM.pop(_k, None)

    # 写 numbers.tex
    lines = ["% numbers.tex —— 由 code/make_numbers.py 从 results/ 自动生成，请勿手工修改",
             "% 生成时间：由脚本运行时刻决定；所有数字宏集中于此，正文不得硬编码。", ""]
    for k in sorted(NUM):
        lines.append("\\newcommand{\\%s}{%s}" % (k, NUM[k]))
    lines.append("")
    with open(os.path.join(PAPER, "numbers.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log("· 已写出 paper/numbers.tex，共 %d 个宏" % len(NUM))

    try:
        write_tables(d, base, q1df)
    except Exception as e:
        log("! write_tables 失败：%s" % e)
        log(traceback.format_exc())

    # 问题三「中继资源缺口」数字宏（增量追加，写出 paper/q3_gap.tex）
    try:
        append_q3gap()
    except Exception as e:
        log("! append_q3gap 失败：%s" % e)
        log(traceback.format_exc())

    miss = [k for k, v in NUM.items() if v == PLACEHOLDER]
    log("· 占位宏 %d 个：%s" % (len(miss), ", ".join(sorted(miss)) if miss else "无"))
    log("完成。")
    flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
