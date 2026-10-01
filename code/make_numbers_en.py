# -*- coding: utf-8 -*-
"""
make_numbers_en.py —— 英文 SCI 稿件的数字宏生成器。

把全部实验结果文件汇总成 `paper_en/numbers_en.tex`，使正文只引用宏、不硬编码数字。
与中文稿的 `make_numbers.py` 同源同口径，但**独立成文件**，互不干扰。

同时写出 `paper_en/numbers_en_sources.txt`（每个宏的来源审计），
沿用中文稿的审计约定：结果缺失时写 \texttt{TBD} 并告警，绝不静默沿用旧值。

用法：python make_numbers_en.py
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import time
from typing import Dict, Optional

import numpy as np

import dcore as D

PAPER = os.path.join(D.BASE, "paper_en")
TBD = "TBD"


def rd(name: str) -> dict:
    p = os.path.join(D.RESULTS, name)
    if not os.path.exists(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


def fnum(x, nd=2):
    if x is None:
        return None
    return ("%%.%df" % nd) % float(x)


def inum(x):
    if x is None:
        return None
    return "%d" % int(round(float(x)))


def main():
    os.makedirs(PAPER, exist_ok=True)
    M: Dict[str, str] = {}
    SRC: Dict[str, str] = {}

    def put(k, v, src):
        if v is None:
            return
        M[k] = str(v)
        SRC[k] = src

    # ---------------- 实例规模（来自中文稿的标准解与结果表） ----------------
    sol = rd("solution.json")
    meta = sol.get("meta") or {}
    put("ENnTransport", inum(meta.get("n_transport")), "solution.json")
    put("ENnBox", inum(meta.get("nbox")), "solution.json")
    put("ENmakeSpan", fnum(meta.get("makespan"), 0), "solution.json")
    put("ENtransEnergy", fnum(meta.get("energy"), 3), "solution.json")
    put("ENontimeRate", fnum(100.0 * float(meta.get("ontime_rate") or 0), 2), "solution.json")
    try:
        d = D.load_all()
        put("ENnArea", inum(len(d["SIDS"])), "附件")
        put("ENnDrone", inum(sum(len(v) for v in d["fleet"].values())), "附件")
        put("ENnRelayFleet", inum(len(d["rfleet"])), "附件")
        put("ENnRelayBat", inum(d["rbatt"][0]), "附件")
        put("ENfMHz", fnum(d["comm"].f_mhz, 0), "附件")
        put("ENlambda", fnum(299792458.0 / (d["comm"].f_mhz * 1e6), 4), "由载频换算")
        put("ENlObs", fnum(d["comm"].l_obs, 0), "附件")
        put("ENgwAntH", fnum(d["comm"].gw_ant_h, 0), "附件")
    except Exception as e:                                        # noqa: BLE001
        print("! 附件参数读取失败：%r" % (e,))

    # ---------------- 地形与坐标系（研究区图所需） ----------------
    # DEM 规模/高程范围直接从栅格读取（与中文稿 numbers.tex 的 DemNx/DemNy/DemZ* 同源），
    # 研究区跨度由 30 m 分辨率与 GLO-30 的裁剪框换算，避免手抄。
    try:
        dem = D.get_dem()
        put("ENnDemNx", inum(dem.nx), "DEM 栅格")
        put("ENnDemNy", inum(dem.ny), "DEM 栅格")
        put("ENdemMin", fnum(float(np.min(dem.z)), 1), "DEM 栅格")
        put("ENdemMax", fnum(float(np.max(dem.z)), 1), "DEM 栅格")
        put("ENdemRelief", fnum(float(np.max(dem.z)) - float(np.min(dem.z)), 0), "DEM 栅格")
        # 裁剪框（与 make_figs.py 的 DEM_BOX 一致）的东西向跨度，按 30 m 栅格估算
        box_lon_deg = 109.330 - 109.120
        km = box_lon_deg * 111.32 * math.cos(math.radians(23.045))
        put("ENdemSpanKm", fnum(km, 1), "研究区裁剪框换算")
        # 图窗内的高程范围（与画图用同一裁剪框），供图注如实描述"图里看到的高差"
        i0 = np.where((dem.lat <= 23.115) & (dem.lat >= 22.975))[0]
        j0 = np.where((dem.lon >= 109.120) & (dem.lon <= 109.330))[0]
        if len(i0) and len(j0):
            Zc = dem.z[i0[0]:i0[-1] + 1, j0[0]:j0[-1] + 1]
            put("ENdemWinMin", fnum(float(np.min(Zc)), 1), "DEM 栅格（图窗裁剪）")
            put("ENdemWinMax", fnum(float(np.max(Zc)), 1), "DEM 栅格（图窗裁剪）")
    except Exception as e:                                        # noqa: BLE001
        print("! DEM 读取失败：%r" % (e,))

    # ---------------- 问题三：中继可行性 ----------------
    q3 = rd("Q3_方案汇总.json")
    st, n2, n3 = q3.get("struct") or {}, q3.get("n2") or {}, q3.get("n3") or {}
    put("ENqInstances", inum(st.get("instances")), "Q3_方案汇总.json")
    put("ENqCells", inum(st.get("cells")), "Q3_方案汇总.json")
    put("ENqCand", inum(st.get("cand_pts")), "Q3_方案汇总.json")
    put("ENqCoverCells", inum(st.get("single_cover_cells")), "Q3_方案汇总.json")
    put("ENqPeak", inum(st.get("peak_concurrent")), "Q3_方案汇总.json")
    put("ENqPhases", inum(st.get("phases")), "Q3_方案汇总.json")
    put("ENqShortPhases", inum(st.get("short_phases")), "Q3_方案汇总.json")
    put("ENqMinPhase", fnum(st.get("min_phase_s"), 0), "Q3_方案汇总.json")
    put("ENqCap", fnum(st.get("energy_cap_s"), 0), "Q3_方案汇总.json")
    put("ENqTwoSorties", inum(n2.get("sorties")), "Q3_方案汇总.json")
    put("ENqTwoCover", fnum(n2.get("cover_pct"), 1), "Q3_方案汇总.json")
    put("ENqTwoOutage", fnum(n2.get("outage_s"), 0), "Q3_方案汇总.json")
    put("ENqThreeSorties", inum(n3.get("sorties")), "Q3_方案汇总.json")
    put("ENqThreeEnergy", fnum(n3.get("energy"), 3), "Q3_方案汇总.json")
    put("ENqThreeHover", fnum(n3.get("hover"), 0), "Q3_方案汇总.json")
    put("ENqThreeSocMin", fnum(n3.get("soc_min"), 1), "Q3_方案汇总.json")
    put("ENqNStar", inum(n3.get("sorties") is not None and 3 or None), "constructed verifier")

    dg = (rd("Q3_诊断汇总.json").get("values") or {})
    put("ENqBlackoutMedian", inum(dg.get("QthreeDpBlackoutMedianS")), "Q3_诊断汇总.json")
    put("ENqBlackoutMin", inum(dg.get("QthreeDpBlackoutMinS")), "Q3_诊断汇总.json")
    put("ENqBlackoutMax", inum(dg.get("QthreeDpBlackoutMaxS")), "Q3_诊断汇总.json")
    put("ENqBlackoutPairs", inum(dg.get("QthreeDpBlackoutPairs")), "Q3_诊断汇总.json")
    put("ENqStarBase", fnum(dg.get("QthreeSpanBlackoutBasePct"), 1), "Q3_诊断汇总.json")
    put("ENqStarAir", fnum(dg.get("QthreeSpanBlackoutAirPct"), 1), "Q3_诊断汇总.json")
    put("ENqDeficitBase", fnum(dg.get("QthreeSpanDeficitBaseS"), 0), "Q3_诊断汇总.json")
    put("ENqDeficitAir", fnum(dg.get("QthreeSpanDeficitAirS"), 0), "Q3_诊断汇总.json")
    # 赤字 D 以**需求格**为单位报告（与 Corollary 的定义一致）。
    # 上面 ENqDeficitBase/Air 是"最坏单格缺口 × 10 s"的秒数，与 D 不是同一个量；
    # 需求格平均间距约 11.4 s 且不等距，把它折算成秒正是我们声明不会做的换算。
    _sb = rd("跨度黑障不等式.json")
    _bm = ((_sb.get("by_mode") or {}).get("全候选点对") or {})
    for _mode, _tag in (("Mode 1", "Base"), ("Mode 2", "Air")):
        _p50 = ((_bm.get(_mode) or {}).get("p50") or {})
        put("ENqDeficitCells%s" % _tag, inum(_p50.get("deficit_cells")),
            "跨度黑障不等式.json")
    put("ENqFailBaseT", inum(dg.get("QthreeFailBaseT")), "Q3_诊断汇总.json")
    put("ENqFailAirT", inum(dg.get("QthreeFailAirT")), "Q3_诊断汇总.json")

    # ---------------- 审稿修复：P.526 段的"说法分级"所需量 ----------------
    # 审稿意见第 4 项：P.526 下"最小机队为 4"只有"贪心在 N=3 没找到"这一条证据，
    # 没有三架不可行的证明。因此正文改成只主张"可构造验证的最小机队"，
    # 并把这些量暴露成宏，避免再出现硬编码。
    _ch = rd("信道模型对比.json").get("results") or {}
    _p5 = (_ch.get("p526") or {}).get("greedy") or {}
    _p5ub = (_ch.get("p526ub") or {}).get("greedy") or {}
    _p5n3 = _p5.get("N3") or {}
    _p5n4 = _p5.get("N4") or {}
    put("ENchAltNReached", inum(_p5n3.get("reached")), "信道模型对比.json")
    put("ENchAltNFailT", fnum((_p5n3.get("fail") or {}).get("t"), 0),
        "信道模型对比.json")
    put("ENchAltNFourSorties", inum(_p5n4.get("sorties")), "信道模型对比.json")
    put("ENchAltNFourSoc", fnum(_p5n4.get("soc_min"), 1), "信道模型对比.json")
    put("ENchAltNFourEnergy", fnum(_p5n4.get("energy"), 3), "信道模型对比.json")
    put("ENchAltUbNFourSoc", fnum(((_p5ub.get("N4") or {}).get("soc_min")), 1),
        "信道模型对比.json")
    # m14 修复：\ENchBudgets 原先声称来自 信道模型对比.json 的 params.topks，
    # 但该文件没有 topks 字段，于是静默回退到生成器里硬编码的字符串——
    # "宏来自结果文件"这句话在这一项上就不成立了。改为从 greedy_by_topk 的键推导。
    _chfull = rd("信道模型对比.json")
    _byk = (_chfull.get("results") or {}).get("observed") or {}
    _tk = sorted((_byk.get("greedy_by_topk") or {}).keys())
    if _tk:
        _budgets = "/".join(k.replace("topk", "") for k in _tk)
        _bsrc = "信道模型对比.json"
    else:
        _budgets = "200/400/600"
        _bsrc = "生成器参数（结果文件中无 greedy_by_topk，未能从文件推导）"
    put("ENchBudgets", _budgets, _bsrc)
    # 只导出**绝对值**版本。原先还导出了带符号的
    # ENchCandDelta = -49.2，结果正文一度写成
    # "reduces ... by \ENchCandDelta\%"，印出 "reduces ... by -49.2%"
    # ，语义恰恰反了。带符号的那个檏子已删除：只要它不存在，
    # 就不可能再被误引。
    _cdv = rd("信道模型对比.json").get("results") or {}
    for _tag, _key in (("ENchCandDeltaAbs", "p526"),):
        _v = ((_cdv.get(_key) or {}).get("cand_delta_pct"))
        if _v is None:
            _o = ((_cdv.get("observed") or {}).get("cand_pts"))
            _a = ((_cdv.get(_key) or {}).get("cand_pts"))
            if _o and _a and float(_o) > 0:
                _v = 100.0 * (float(_a) - float(_o)) / float(_o)
        put(_tag, fnum(abs(float(_v)) if _v is not None else None, 1),
            "信道模型对比.json")

    # ---------------- 审稿修复：参数无关证书检验 ----------------
    # pf_cert.py：把 span 不等式写成不含人为阈值的形式后，它在 880/992（M1）
    # 与 986/992（M2）个格上仍可满足 —— 因此该不等式**不是**不可行性证书。
    _pfr = rd("参数无关证书.json").get("results") or {}
    for _tag, _key in (("Base", "base"), ("Air", "air")):
        _r = _pfr.get(_key) or {}
        put("ENpfCellsOk" + _tag, inum(_r.get("cells_admitting_a_move")),
            "参数无关证书.json")
        put("ENpfSpanMax" + _tag, fnum(_r.get("span_min_max_s"), 0),
            "参数无关证书.json")
        put("ENpfWMin" + _tag, fnum(_r.get("W_min_s"), 0), "参数无关证书.json")
    put("ENpfCells", inum((_pfr.get("base") or {}).get("cells_total")),
        "参数无关证书.json")

    # 信道宏的绝对值版本（原文用负号造成 "overstates by -49.2%"）
    _obs = (((_ch.get("observed") or {}).get("transport")) or {}).get("instances")
    _alt = (((_ch.get("p526") or {}).get("transport")) or {}).get("instances")
    put("ENchObsInst", inum(_obs), "信道模型对比.json")
    put("ENchAltInst", inum(_alt), "信道模型对比.json")
    if _obs and _alt and float(_obs) > 0:
        put("ENchAltDelta", fnum(100.0 * (float(_alt) - float(_obs)) / float(_obs), 1),
            "信道模型对比.json")

    # ---------------- 审稿修复：说法分级所需的量 ----------------
    # ENgrFailNTwoTairPP：**递推（DP）自己的** M2/N=2 失败时刻，来自
    #   换位模式对比.json（mode_compare.py 用 topk=12 + keep_slack 剪枝跑出）。
    #   原先 ENgrFailNTwoTair 是从贪心 verifier 取来的 3950 s，被表 4 标成了
    #   "recursion"，属溯源错误；这里把两个来源分开成两个宏：
    #     ENgrFailNTwoTair   = 构造性贪心 verifier 的失败时刻（保持原义）
    #     ENgrFailNTwoTairPP = 状态递推的失败时刻（表 4 应引用这个）
    _mc = rd("换位模式对比.json")
    for _row in (_mc.get("rows") or []):
        if _row.get("N") == 2 and _row.get("mode") == "air":
            _m = re.search(r"t=(\d+(?:\.\d+)?)\s*s", str(_row.get("reason") or ""))
            if _m:
                put("ENgrFailNTwoTairPP", fnum(float(_m.group(1)), 0),
                    "换位模式对比.json")
            _c = re.search(r"第\s*(\d+)\s*格", str(_row.get("reason") or ""))
            if _c:
                put("ENgrFailNTwoTairPPCell", inum(int(_c.group(1))),
                    "换位模式对比.json")
    # M1 下 N=2 的失败格号（表 4 里标出，便于读者定位）
    for _row in (_mc.get("rows") or []):
        if _row.get("N") == 2 and _row.get("mode") == "base":
            _c = re.search(r"第\s*(\d+)\s*格", str(_row.get("reason") or ""))
            if _c:
                put("ENgrFailNTwoTCell", inum(int(_c.group(1))),
                    "换位模式对比.json")
                _t = re.search(r"t=(\d+(?:\.\d+)?)\s*s", str(_row.get("reason") or ""))
                if _t:
                    put("ENgrFailNTwoT", fnum(float(_t.group(1)), 0),
                        "换位模式对比.json")
    # m13：表 tab:modes 把 N=1/N=2 两行标为 "recursion"，但这两个宏原先取自
    #   中继基线与下界.json 的 greedy（构造性验证器）子对象，溯源标注与表格声明
    #   不一致（数值恰好相同，所以不是数值错误）。这里直接取**递推自己的**失败
    #   时刻（来自 换位模式对比.json 的 reason 文本），让溯源与声明一致。
    for _row in (_mc.get("rows") or []):
        if _row.get("N") == 1 and _row.get("mode") == "base":
            _t = re.search(r"t=(\d+(?:\.\d+)?)\s*s", str(_row.get("reason") or ""))
            if _t:
                put("ENgrFailNOneT", fnum(float(_t.group(1)), 0),
                    "换位模式对比.json（递推自身的首个空状态）")

    # ---------------- 理论量：span / alibi 放行率 / 机队规模下界 ----------------
    oc = rd("局部阻塞证书.json")
    ocr = (oc.get("results") or {})
    o1, o2 = (ocr.get("base") or {}), (ocr.get("air") or {})
    put("ENTs", fnum(oc.get("T_s"), 0), "局部阻塞证书.json")
    put("ENcapS", fnum(oc.get("T_cap_s"), 0), "局部阻塞证书.json")
    put("ENboundEnergy", inum(oc.get("bound_energy")), "局部阻塞证书.json")
    put("ENspanMedian", fnum(o1.get("span_median_s"), 0), "局部阻塞证书.json")
    put("ENspanPNinety", fnum(o1.get("span_p90_s"), 0), "局部阻塞证书.json")
    put("ENspanMax", fnum(o1.get("span_max_s"), 0), "局部阻塞证书.json")
    put("ENwMinMOne", fnum(o1.get("w_min_s"), 0), "局部阻塞证书.json")
    put("ENwMedMOne", fnum(o1.get("w_median_s"), 0), "局部阻塞证书.json")
    put("ENwMinMTwo", fnum(o2.get("w_min_s"), 0), "局部阻塞证书.json")
    put("ENwMedMTwo", fnum(o2.get("w_median_s"), 0), "局部阻塞证书.json")
    put("ENreleaseMOne", fnum(100.0 * float(o1.get("release_at_wmed") or 0), 1),
        "局部阻塞证书.json")
    put("ENreleaseMTwo", fnum(100.0 * float(o2.get("release_at_wmed") or 0), 1),
        "局部阻塞证书.json")
    put("ENmuMax", fnum(o1.get("mu_max_s"), 0), "局部阻塞证书.json")
    # m11：阻塞证书里的 bound_by_w / bound_combined 被写成"结构下界
    # N >= 1 + floor(mu/w_min)"，但论文自己的构造性验证在 N=3 就可行，
    # 于是 N>=10 是**假的**（该式实质是上界方向，与 prop:structural 同源）。
    # 结果文件里这个字段的语义是错的，所以**不再导出成宏**：宁可缺一个宏，
    # 也不能让将来的修订版从宏名"ENboundStructural"误以为它是可引用的下界。
    # 上界仍由 ENboundCounting（1 + floor(T/w_min)）提供，那个方向是对的。
    if o1.get("bound_by_w") is not None:
        print("! 局部阻塞证书.json 的 bound_by_w=%s 语义为上界、却被标为下界，"
              "已拒绝导出为宏" % o1.get("bound_by_w"))
    if oc.get("T_s") and o1.get("w_min_s"):
        put("ENboundCounting",
            inum(1 + int(float(oc["T_s"]) // float(o1["w_min_s"]))),
            "局部阻塞证书.json")
    put("ENcellsSingleProvider", inum(o1.get("cells_single_provider")),
        "局部阻塞证书.json")
    put("ENcellsMultiProvider", inum(o1.get("cells_multi_provider")),
        "局部阻塞证书.json")
    put("ENcellsUncoverable", inum(o1.get("cells_uncoverable")),
        "局部阻塞证书.json")
    put("ENcandCZero", inum(o1.get("n_cand_c0")), "局部阻塞证书.json")
    put("ENcandCZeroPct", fnum(100.0 * float(o1.get("c0_ratio") or 0), 1),
        "局部阻塞证书.json")
    put("ENgrFailNTwoTair", inum(dg.get("QthreeFailAirT")), "Q3_诊断汇总.json")
    rb = rd("中继基线与下界.json")
    put("ENrbNaiveExact", inum(rb.get("N_naive")), "中继基线与下界.json")
    put("ENrbLBHandover", inum(rb.get("LB_handover")), "中继基线与下界.json")
    g = rb.get("greedy") or {}
    put("ENgrFailNOneT", fnum((g.get("N1") or {}).get("fail_t"), 0), "中继基线与下界.json")
    put("ENgrFailNTwoT", fnum((g.get("N2") or {}).get("fail_t"), 0), "中继基线与下界.json")

    # m13：表 tab:modes 把 N=1/N=2 两行标为 "recursion"，但上面这两个宏取自
    #   中继基线与下界.json 的 greedy（构造性验证器）子对象，溯源标注与表格声明
    #   不一致（数值恰好与递推自身相同，所以不是数值错误，只是溯源错）。
    #   这里用**递推自己的**首个空状态时刻覆盖它们，让溯源与表格一致。
    for _row in (rd("换位模式对比.json").get("rows") or []):
        if _row.get("mode") == "base" and _row.get("N") in (1, 2):
            _t = re.search(r"t=(\d+(?:\.\d+)?)\s*s", str(_row.get("reason") or ""))
            if _t:
                put("ENgrFailN%sT" % ("One" if _row["N"] == 1 else "Two"),
                    fnum(float(_t.group(1)), 0),
                    "换位模式对比.json（递推自身的首个空状态）")

    # ---------------- 运输侧文献启发式：Clarke–Wright 节约算法 ----------------
    cw = rd("文献启发式对照.json")
    cwr = cw.get("rows_cw") or {}
    ar = cw.get("rows_alns") or {}
    c1 = cwr.get("P1-架次优先") or {}
    a1 = ar.get("P1-架次优先") or {}
    put("ENcwStart", inum(cw.get("start_sorties")), "文献启发式对照.json")
    put("ENcwMerges", inum(cw.get("n_merges")), "文献启发式对照.json")
    put("ENcwSorties", inum(c1.get("count")), "文献启发式对照.json")
    put("ENcwEnergy", fnum(c1.get("energy"), 2), "文献启发式对照.json")
    put("ENcwTardy", fnum(c1.get("tardiness"), 0), "文献启发式对照.json")
    put("ENcwHard", fnum(c1.get("hard_violation"), 0), "文献启发式对照.json")
    put("ENcwOntime", fnum(100.0 * float(c1.get("ontime_rate") or 0), 1),
        "文献启发式对照.json")
    put("ENcwAlnsSorties", inum(a1.get("count")), "文献启发式对照.json")
    put("ENcwAlnsEnergy", fnum(a1.get("energy"), 2), "文献启发式对照.json")
    put("ENcwAlnsTardy", fnum(a1.get("tardiness"), 0), "文献启发式对照.json")
    put("ENcwAlnsHard", fnum(a1.get("hard_violation"), 0), "文献启发式对照.json")
    put("ENcwAlnsOntime", fnum(100.0 * float(a1.get("ontime_rate") or 0), 1),
        "文献启发式对照.json")

    # ---------------- 相位级整数规划区间松弛（方法学交叉验证） ----------------
    il = rd("中继ILP松弛.json")
    ilr = il.get("results") or {}
    i1, i2, i3 = (ilr.get("N1") or {}), (ilr.get("N2") or {}), (ilr.get("N3") or {})
    put("ENilpPhases", inum(il.get("n_phases")), "中继ILP松弛.json")
    put("ENilpPerPhase", inum(il.get("per_phase")), "中继ILP松弛.json")
    put("ENilpNOneStatus", i1.get("status"), "中继ILP松弛.json")
    put("ENilpNTwoStatus", i2.get("status"), "中继ILP松弛.json")
    put("ENilpNThreeStatus", i3.get("status"), "中继ILP松弛.json")
    put("ENilpNTwoBool", inum(i2.get("n_bool")), "中继ILP松弛.json")
    put("ENilpNTwoCuts", inum(i2.get("n_blackout_cuts")), "中继ILP松弛.json")
    put("ENilpNTwoT", fnum(i2.get("elapsed_s"), 1), "中继ILP松弛.json")
    put("ENilpNOneT", fnum(i1.get("elapsed_s"), 1), "中继ILP松弛.json")
    put("ENilpEntries", inum(len(i2.get("chosen") or [])), "中继ILP松弛.json")

    # ---------------- 防线 1：换位模式（含构造性判定在两种模式下的 N=3 结果） ----------------
    mc = rd("换位模式对比.json")
    sbm = rd("跨度黑障不等式.json")
    put("ENqBlackoutAirMedian", fnum(sbm.get("w_air_median_all_s"), 0), "跨度黑障不等式.json")
    for _N in (1, 2, 3):
        for _md, _tg in (("base", "MOne"), ("air", "MTwo")):
            _row = next((r for r in (mc.get("rows") or [])
                         if r.get("N") == _N and r.get("mode") == _md), None)
            if _row is None:
                continue
            if _row.get("feasible"):
                put("ENmode%sN%sFeas" % (_tg, "One" if _N == 1 else
                                         ("Two" if _N == 2 else "Three")), "yes",
                    "换位模式对比.json")
            else:
                put("ENmode%sN%sFailT" % (_tg, "One" if _N == 1 else
                                          ("Two" if _N == 2 else "Three")),
                    fnum(_row.get("fail_t"), 0), "换位模式对比.json")
    _m1n1 = next((r for r in (mc.get("rows") or [])
                  if r.get("N") == 1 and r.get("mode") == "base"), None)
    _m1n1_t = None
    if _m1n1 and not _m1n1.get("feasible"):
        # 该行只有中文 reason 字符串，没有结构化的 fail_t；改用构造性判定的
        # N=1 首败时刻作为同口径数值（QP 诊断汇总里的 QthreeFailBaseT 是 N=2 的，
        # 不能拿来当 N=1 的值）。
        _m1n1_t = (rb.get("greedy") or {}).get("N1", {}).get("fail_t")
    put("ENqFailBaseNOneT", inum(_m1n1_t), "中继基线与下界.json")
    # 构造性判定给出的 N=3 结果（两种模式各自的结果文件，不再互相覆盖）
    for _md, _tg in (("base", "MOne"), ("air", "MTwo")):
        _g = rd("构造性贪心判定_N3_%s.json" % _md)
        if not _g:
            continue
        put("ENgrNThree%sFeas" % _tg, "yes" if _g.get("feasible") else "no",
            "构造性贪心判定_N3_%s.json" % _md)
        if _g.get("feasible"):
            put("ENgrNThree%sSorties" % _tg, inum(_g.get("sorties")),
                "构造性贪心判定_N3_%s.json" % _md)
            put("ENgrNThree%sMiss" % _tg, inum(_g.get("miss")),
                "构造性贪心判定_N3_%s.json" % _md)
            put("ENgrNThree%sSoc" % _tg, fnum(_g.get("soc_min"), 1),
                "构造性贪心判定_N3_%s.json" % _md)
        else:
            put("ENgrNThree%sFailT" % _tg, fnum(_g.get("fail_t"), 0),
                "构造性贪心判定_N3_%s.json" % _md)
            put("ENgrNThree%sReached" % _tg, inum(_g.get("fail_k")),
                "构造性贪心判定_N3_%s.json" % _md)
            put("ENgrNThree%sActions" % _tg, inum(_g.get("actions")),
                "构造性贪心判定_N3_%s.json" % _md)
    _gb = ((rb.get("greedy") or {}).get("N3") or {})
    if _gb:
        put("ENgrNThreeMOneFeas", "yes" if _gb.get("feasible") else "no",
            "中继基线与下界.json")
        if _gb.get("feasible"):
            put("ENgrNThreeMOneSorties", inum(_gb.get("sorties")), "中继基线与下界.json")

    # ---------------- 防线 3：信道模型 ----------------
    ch = rd("信道模型对比.json")
    for key, tag in (("observed", "Obs"), ("p526", "Alt"), ("p526ub", "AltUb")):
        r = (ch.get("results") or {}).get(key) or {}
        tr = r.get("transport") or {}
        put("ENch%sInstances" % tag, inum(tr.get("instances")), "信道模型对比.json")
        put("ENch%sCells" % tag, inum(tr.get("cells")), "信道模型对比.json")
        put("ENch%sCand" % tag, inum(r.get("cand_pts")), "信道模型对比.json")
        put("ENch%sPhases" % tag, inum(r.get("phases")), "信道模型对比.json")
        g = (r.get("greedy") or {})
        for N in (1, 2, 3, 4):
            e = g.get("N%d" % N) or {}
            put("ENch%sN%s" % (tag, "ABCD"[N - 1]),
                "yes" if e.get("feasible") else ("no" if e else None),
                "信道模型对比.json")
        put("ENch%sNStar" % tag, inum(r.get("N_crit")) if r.get("N_crit") else None,
            "信道模型对比.json")
    if (ch.get("results") or {}).get("observed") and (ch.get("results") or {}).get("p526"):
        o = (ch["results"]["observed"].get("transport") or {}).get("instances")
        p = (ch["results"]["p526"].get("transport") or {}).get("instances")
        if o and p:
            put("ENchReqDelta", "%+.1f" % (100.0 * (p - o) / o), "信道模型对比.json")
        co = ch["results"]["observed"].get("cand_pts")
        cp = ch["results"]["p526"].get("cand_pts")
        if co and cp:
            # 这里**故意不**导出带符号版本：见本文件上方 ENchCandDeltaAbs 处的注释。
            # 只保留绝对值版，杜绝"reduces ... by 负数"这类符号反向的误引。
            put("ENchCandDeltaAbs",
                "%.1f" % abs(100.0 * (cp - co) / co), "信道模型对比.json")

    # ---------------- 多地形基准 ----------------
    tb = rd("多地形基准.json")
    rows = tb.get("rows") or []
    ok = [r for r in rows if r.get("relay_ok")]
    put("ENtbNTerrain", inum(len(rows)), "多地形基准.json")
    put("ENtbNOk", inum(len(ok)), "多地形基准.json")
    if ok:
        okr = sorted(ok, key=lambda r: r["occlusion"]["ratio"])
        put("ENtbOccMin", fnum(100 * okr[0]["occlusion"]["ratio"], 1), "多地形基准.json")
        put("ENtbOccMax", fnum(100 * okr[-1]["occlusion"]["ratio"], 1), "多地形基准.json")
        crits = sorted({(r["N_crit"] if r["N_crit"] is not None else -1) for r in ok})
        put("ENtbNStarSet", ", ".join((">4" if c < 0 else str(c)) for c in crits),
            "多地形基准.json")
        put("ENtbNStarMin", inum(min(c for c in crits if c >= 0)), "多地形基准.json")
        put("ENtbNStarMax", inum(max(c for c in crits if c >= 0)), "多地形基准.json")
        n4 = [r for r in ok if r["N_crit"] is None]
        put("ENtbNGtFour", inum(len(n4)), "多地形基准.json")

    # ---------------- 协同再调度 ----------------
    cf = rd("协同再调度.json")
    # 搜索规模（算法参数，不是结果）：正文的"样本量说明"要如实交代迭代预算
    _p = cf.get("params") or {}
    put("ENcfIters", inum(_p.get("iters")), "协同再调度.json")
    put("ENcfRestarts", inum(_p.get("restarts")), "协同再调度.json")
    for mode, tag in (("base", "Base"), ("air", "Air")):
        r = (cf.get("results") or {}).get(mode) or {}
        if not r:
            continue
        put("ENcf%sDefA" % tag, inum(r["baseline"]["deficit_cells"]), "协同再调度.json")
        put("ENcf%sDefB" % tag, inum(r["after"]["deficit_cells"]), "协同再调度.json")
        put("ENcf%sRed" % tag, fnum(r.get("deficit_reduction_pct"), 1), "协同再调度.json")
        put("ENcf%sZero" % tag, "yes" if r.get("residue_zero") else "no", "协同再调度.json")
        put("ENcf%sShiftN" % tag, inum(r["after"]["n_shifted"]), "协同再调度.json")
        put("ENcf%sShiftMax" % tag, fnum(r["after"]["max_shift_s"], 0), "协同再调度.json")
        put("ENcf%sMkA" % tag, fnum(r["baseline"]["makespan"], 0), "协同再调度.json")
        put("ENcf%sMkB" % tag, fnum(r["after"]["makespan"], 0), "协同再调度.json")

    # ---------------- 中继基线与下界 ----------------
    rb = rd("中继基线与下界.json")
    put("ENrbNaive", inum(rb.get("N_naive")), "中继基线与下界.json")
    put("ENrbLB", inum(rb.get("LB_handover")), "中继基线与下界.json")
    put("ENrbGreedy", inum(rb.get("N_greedy")), "中继基线与下界.json")
    if rb.get("N_naive") is not None and rb.get("N_greedy") is not None:
        put("ENrbPremium", inum(rb["N_greedy"] - rb["N_naive"]), "中继基线与下界.json")

    # ---------------- 问题四：分区代价 ----------------
    q4 = rd("Q4_中继增配情景.json")
    try:
        rA = (q4.get("scenarios") or {}).get("A") or {}
        rB = (q4.get("scenarios") or {}).get("B") or {}
        for tag, r in (("A", rA), ("B", rB)):
            if not r:
                continue
            for K in ("2", "3"):
                d = (r.get("K") or {}).get(K) or {}
                put("ENqfour%sK%sRelayNeed" % (tag, "two" if K == "2" else "three"), inum(d.get("relay_need")),
                    "Q4_中继增配情景.json")
                put("ENqfour%sK%sRelayGap" % (tag, "two" if K == "2" else "three"), inum(d.get("relay_gap")),
                    "Q4_中继增配情景.json")
                put("ENqfour%sK%sCross" % (tag, "two" if K == "2" else "three"), inum(len(d.get("cross") or [])),
                    "Q4_中继增配情景.json")
    except Exception as e:                                        # noqa: BLE001
        print("! Q4 情景读取失败：%r" % (e,))

    # ---------------- 基线与消融（A 运输侧 / E 分区代价） ----------------
    ab = rd("基线与消融.json")
    trows = (ab.get("A_transport_methods") or {}).get("rows") or []
    if trows:
        g = [r for r in trows if str(r.get("方法", "")).startswith("贪心")
             and r.get("权重组") == "P1-架次优先"]
        a_ = [r for r in trows if r.get("方法") == "ALNS(无CP-SAT)"
              and r.get("权重组") == "P1-架次优先"]
        c_ = [r for r in trows if r.get("方法") == "ALNS+CP-SAT"
              and r.get("权重组") == "P2-及时优先"]
        if g:
            put("ENbaseGreedySorties", inum(g[0].get("架次数")), "基线与消融.json")
            put("ENbaseGreedyEnergy", fnum(g[0].get("总能耗_kWh"), 2), "基线与消融.json")
            put("ENbaseGreedyTardy", fnum(g[0].get("加权延误"), 0), "基线与消融.json")
        if a_:
            put("ENbaseAlnsSorties", inum(a_[0].get("架次数")), "基线与消融.json")
            put("ENbaseAlnsEnergy", fnum(a_[0].get("总能耗_kWh"), 2), "基线与消融.json")
            put("ENbaseAlnsTardy", fnum(a_[0].get("加权延误"), 0), "基线与消融.json")
        if c_:
            put("ENbaseCpsatStatus", str(c_[0].get("CP_SAT状态") or "—"), "基线与消融.json")
    ee = ab.get("E_price_of_partitioning") or {}
    put("ENpopKtwo", fnum(ee.get("weighted_total_k2"), 2), "基线与消融.json")
    put("ENpopKthree", fnum(ee.get("weighted_total_k3"), 2), "基线与消融.json")
    for r in (ee.get("rows") or []):
        rn = str(r.get("resource") or "")
        if rn.startswith("C型运输"):
            put("ENpopCTwo", inum(r.get("pop_k2")), "基线与消融.json")
            put("ENpopCThree", inum(r.get("pop_k3")), "基线与消融.json")
        if rn.startswith("B型运输"):
            put("ENpopBThree", inum(r.get("pop_k3")), "基线与消融.json")

    # ---------------- 缺失宏的显式占位（避免 Undefined control sequence） -------
    EXPECTED = [
        "ENbaseGreedySorties", "ENbaseGreedyEnergy", "ENbaseGreedyTardy",
        "ENbaseAlnsSorties", "ENbaseAlnsEnergy", "ENbaseAlnsTardy", "ENbaseCpsatStatus",
        "ENpopKtwo", "ENpopKthree", "ENpopCTwo", "ENpopCThree", "ENpopBThree",
        "ENrbNaive", "ENrbLB", "ENrbGreedy", "ENrbPremium",
        "ENcfBaseDefA", "ENcfBaseDefB", "ENcfBaseRed", "ENcfBaseZero",
        "ENcfBaseShiftN", "ENcfBaseShiftMax", "ENcfBaseMkA", "ENcfBaseMkB",
        "ENcfAirDefA", "ENcfAirDefB", "ENcfAirRed", "ENcfAirZero",
        "ENcfAirShiftN", "ENcfAirShiftMax", "ENcfAirMkA", "ENcfAirMkB",
        "ENchObsInstances", "ENchObsCells", "ENchObsCand", "ENchObsPhases",
        "ENchAltInstances", "ENchAltCells", "ENchAltCand", "ENchAltPhases",
        "ENchAltUbInstances", "ENchAltUbCells", "ENchAltUbCand", "ENchAltUbPhases",
        "ENchObsNStar", "ENchAltNStar", "ENchAltUbNStar",
        "ENchReqDelta", "ENchCandDeltaAbs",
        "ENtbNTerrain", "ENtbNOk", "ENtbOccMin", "ENtbOccMax", "ENtbNStarSet",
        "ENtbNGtFour",
        "ENqInstances", "ENqCells", "ENqCand", "ENqCoverCells", "ENqPeak",
        "ENqPhases", "ENqShortPhases", "ENqMinPhase", "ENqCap",
        "ENqTwoSorties", "ENqTwoCover", "ENqTwoOutage",
        "ENqThreeSorties", "ENqThreeEnergy", "ENqThreeHover", "ENqThreeSocMin",
        "ENqBlackoutMedian", "ENqBlackoutMin", "ENqBlackoutMax",
        "ENqBlackoutPairs", "ENqStarBase", "ENqStarAir",
        "ENqDeficitBase", "ENqDeficitAir", "ENqFailBaseT", "ENqFailAirT",
        "ENqfourAKtwoRelayNeed", "ENqfourBKtwoRelayNeed",
        "ENqfourAKthreeRelayNeed", "ENqfourBKthreeRelayNeed",
        "ENqfourAKtwoRelayGap", "ENqfourBKtwoRelayGap",
        "ENqfourAKthreeRelayGap", "ENqfourBKthreeRelayGap",
        "ENqfourAKtwoCross", "ENqfourBKtwoCross",
        "ENqfourAKthreeCross", "ENqfourBKthreeCross",
        "ENTs", "ENcapS", "ENboundEnergy",
        "ENspanMedian", "ENspanPNinety", "ENspanMax",
        "ENwMinMOne", "ENwMedMOne", "ENwMinMTwo", "ENwMedMTwo",
        "ENreleaseMOne", "ENreleaseMTwo",
        "ENmuMax", "ENboundCounting",
        "ENcellsSingleProvider", "ENcellsMultiProvider", "ENcellsUncoverable",
        "ENcandCZero", "ENcandCZeroPct", "ENgrFailNTwoTair",
        "ENilpPhases", "ENilpPerPhase", "ENilpNOneStatus", "ENilpNTwoStatus",
        "ENilpNThreeStatus", "ENilpNTwoBool", "ENilpNTwoCuts", "ENilpNTwoT",
        "ENilpNOneT", "ENilpEntries",
        "ENgrNThreeMOneFeas", "ENgrNThreeMOneSorties", "ENgrNThreeMOneMiss",
        "ENgrNThreeMOneSoc", "ENgrNThreeMTwoFeas", "ENgrNThreeMTwoFailT",
        "ENgrNThreeMTwoReached", "ENgrNThreeMTwoActions",
        "ENqFailBaseNOneT", "ENqBlackoutAirMedian",
        "ENnDemNx", "ENnDemNy", "ENdemMin", "ENdemMax", "ENdemRelief", "ENdemSpanKm",
        "ENdemWinMin", "ENdemWinMax",
        "ENcwStart", "ENcwMerges", "ENcwSorties", "ENcwEnergy", "ENcwTardy",
        "ENcwHard", "ENcwOntime", "ENcwAlnsSorties", "ENcwAlnsEnergy",
        "ENcwAlnsTardy", "ENcwAlnsHard", "ENcwAlnsOntime",
        "ENrbNaiveExact", "ENrbLBHandover", "ENgrFailNOneT", "ENgrFailNTwoT",
    ]
    miss = [k for k in EXPECTED if k not in M]
    for k in miss:
        M[k] = "\\tbd"
        SRC[k] = "MISSING（对应结果文件尚未生成）"
    if miss:
        print("! %d 个宏因结果文件缺失写为 \\tbd：%s" % (len(miss), "、".join(miss[:10])))

    order = sorted(M.keys())
    # 宏总数本身也要可用：正文的"可复现性"小节用它说明生成规模
    M["ENnMacros"] = str(len(M) + 1)
    SRC["ENnMacros"] = "code/make_numbers_en.py（本脚本自身）"
    order = sorted(M.keys())
    L = ["%% numbers_en.tex —— 英文 SCI 稿件数字宏（由 code/make_numbers_en.py 生成）",
         "%% 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "%% 缺失的结果文件对应宏写为 %s，并在 numbers_en_sources.txt 中标注。" % TBD,
         ""]
    for k in order:
        L.append("\\newcommand{\\%s}{%s}" % (k, M[k]))
    with io.open(os.path.join(PAPER, "numbers_en.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    used_src = sorted({SRC[k] for k in M})
    with io.open(os.path.join(PAPER, "numbers_en_sources.txt"), "w", encoding="utf-8") as f:
        f.write("# numbers_en.tex 宏来源审计\n")
        f.write("# 生成时间：%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("# 共 %d 个宏，来自 %d 个结果文件\n\n" % (len(M), len(used_src)))
        for k in order:
            f.write("%-28s %-28s %s\n" % (k, SRC.get(k, "?"), M[k]))
    print("已写出 paper_en/numbers_en.tex（%d 个宏）" % len(M))
    print("     paper_en/numbers_en_sources.txt（来源：%s）" % "、".join(used_src))


if __name__ == "__main__":
    main()
