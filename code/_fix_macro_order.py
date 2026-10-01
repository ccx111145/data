# -*- coding: utf-8 -*-
"""_fix_macro_order.py —— 把 `Q3GAP_ORDER` 从"手工维护的列表"改为
由 `Q3GAP_GROUPS`（分组的宏清单，也是 q3_gap.tex 的写出顺序）**自动派生**。

原因：手工列表漂移导致新加的宏只出现在 q3_gap.tex / 只出现在 numbers.tex，
前者造成「引用未定义」，后者造成「Command already defined」编译错误。
本脚本顺便把 `\\QthreeDpBlackoutAirMedianS`（论文已引用但两处都没定义）补齐。
"""
import io
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "make_numbers.py")
s = io.open(P, encoding="utf-8").read()

# ---------- 1) 用 Q3GAP_GROUPS 替换手工 Q3GAP_ORDER ----------
m = re.search(r"Q3GAP_ORDER = \[(?:.|\n)*?\n(?:.*\n)*?.*?\]\n", s)
assert m, "未找到 Q3GAP_ORDER"
old_order = m.group(0)
new_order = '''Q3GAP_GROUPS = [
    ("\\u24e0 \\u4e2d\\u7ee7\\u65f6\\u5e8f\\u53c2\\u6570\\uff08\\u9644\\u5f55 2 \\u7ed9\\u5b9a\\u503c\\uff0c\\u4f9b\\u5047\\u8bbe A13 \\u5f15\\u7528\\uff09",
     ["CommLink", "CommTurn"]),
    ("\\u2460 2 \\u67b6\\u4e2d\\u7ee7\\u6298\\u4e2d\\u65b9\\u6848\\uff08\\u5e93\\u5b58\\u7ea6\\u675f\\u4e0b\\u7684\\u6700\\u4f18\\u6298\\u4e2d\\uff0c\\u5373 solution.json \\u7684 relay \\u5b57\\u6bb5\\uff09",
     ["QthreeCompromiseSorties", "QthreeCompromiseCoverPct",
      "QthreeCompromiseUncoveredS", "QthreeCompromiseLongestS",
      "QthreeCompromiseCoverRate", "QthreeCompromiseEnergy",
      "QthreeCompromiseHover", "QthreeRelayHoverLike",
      "QthreeCompromiseOutagePhaseN", "QthreeCompromiseOutagePhaseS"]),
    ("\\u2461 N = 2 \\u7684\\u4e0d\\u53ef\\u884c\\u6027\\uff08\\u72b6\\u6001 DP \\u5224\\u5b9a\\uff1b\\u53ea\\u80fd\\u4e3b\\u5f20\\u300c\\u5728\\u7ed9\\u5b9a\\u5019\\u9009\\u96c6\\u4e0e\\u526a\\u679d\\u4e0b\\u672a\\u627e\\u5230\\u53ef\\u884c\\u89e3\\u300d\\uff09",
     ["QthreeDpCells", "QthreeDpInstances", "QthreeDpSingleCoverCells",
      "QthreeDpCandPts", "QthreeDpCandPairs", "QthreeDpMeanPts",
      "QthreeDpPeakConcurrent", "QthreeDpBlackoutMedianS",
      "QthreeDpBlackoutAirMedianS",
      "QthreeDpBlackoutMeanS", "QthreeDpBlackoutMinS",
      "QthreeDpBlackoutMaxS", "QthreeDpBlackoutGePct", "QthreeDpBlackoutPairs",
      "QthreeDpPhases", "QthreeDpShortPhases", "QthreeDpShortPhaseMinS",
      "QthreeDpInfeasibleCell", "QthreeDpInfeasibleT"]),
    ("\\u2462 \\u6700\\u5c0f\\u589e\\u914d\\u65b9\\u6848\\uff08N = 3\\uff0c\\u5168\\u8986\\u76d6\\u3001\\u96f6\\u65f6\\u5e8f\\u51b2\\u7a81\\uff09",
     ["QthreeNeedN", "QthreeGapN", "QthreeNThreeSorties",
      "QthreeNThreeSortiesSplit", "QthreeNThreeEnergy", "QthreeNThreeHoverS",
      "QthreeNThreeCoverCells", "QthreeNThreeConflicts", "QthreeNThreeMiss",
      "QthreeNThreeMaxHoverS"]),
    ("\\u2463 \\u6362\\u4f4d\\u6a21\\u5f0f\\u5bf9\\u6bd4\\u4e0e\\u5019\\u9009\\u96c6\\u7a33\\u5065\\u6027",
     ["QthreeEnergyCap", "QthreeDpTZero",
      "QthreeWBaseMedS", "QthreeWAirMedS", "QthreeWBaseStrongS", "QthreeWAirStrongS",
      "QthreeStarBasePct", "QthreeStarAirPct",
      "QthreeStarBaseStrongPct", "QthreeStarAirStrongPct",
      "QthreeFailBaseT", "QthreeFailAirT", "QthreeFailCellLow", "QthreeFailCellHigh",
      "QthreeNGreedySorties", "QthreeNGreedyEnergy", "QthreeNGreedySocMin",
      "QthreeRejUnionPct", "QthreeRejArrivalPct"]),
    ("\\u2464 \\u901a\\u4fe1\\u4e2d\\u65ad\\u65f6\\u957f\\u7684\\u4e09\\u79cd\\u7edf\\u8ba1\\u53e3\\u5f84",
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
'''
s = s[:m.start()] + new_order + s[m.end():]

# ---------- 2) 新增 QthreeDpBlackoutAirMedianS 的默认值 ----------
anchor = '    "QthreeDpBlackoutMedianS": "1037",'
assert s.count(anchor) == 1, ("default anchor", s.count(anchor))
s = s.replace(anchor, anchor + '\n    "QthreeDpBlackoutAirMedianS": "471",')

# ---------- 3) append_q3gap 内部改用 Q3GAP_GROUPS ----------
old_g = re.search(r"    groups = \[\("
                  r"(?:.|\n)*?"
                  r'"QthreeNThreeMaxHoverS"\]\)\]\n', s)
assert old_g, "未找到 append_q3gap 内的 groups"
s = s[:old_g.start()] + "    groups = Q3GAP_GROUPS\n" + s[old_g.end():]

io.open(P, "w", encoding="utf-8").write(s)
print("make_numbers.py 已重构：Q3GAP_ORDER 由 Q3GAP_GROUPS 自动派生")
