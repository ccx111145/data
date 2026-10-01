# -*- coding: utf-8 -*-
"""_fix_wmax.py —— 删除论文与宏表里已过期的「换位窗口截断上限 $W_{\\max}$」表述。

背景：`q3dpN.py` 已移除 `Wmax` 截断（换位黑障窗口按精确秒数计算，不再截断），
因此论文 §7.4 中「\QthreeDpBlackoutCapPct\% 的点对甚至超过 DP 中采用的换位窗口
截断上限 $W_{\max}$」与 `\\QthreeDpBlackoutCapPct` 宏都已失效（审阅 #4）。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")
MN = os.path.join(BASE, "code", "make_numbers.py")

# ---------- 1) 论文正文 ----------
s = io.open(TEX, encoding="utf-8").read()
old = (r"""在 \QthreeDpCandPts{} 个候选点上枚举全部点对（\QthreeDpCandPairs{} 对）后，
黑障窗口的分布为：最小 \QthreeDpBlackoutMinS\,s、中位 \QthreeDpBlackoutMedianS\,s、
平均 \QthreeDpBlackoutMeanS\,s、最大 \QthreeDpBlackoutMaxS\,s，
其中 \QthreeDpBlackoutGePct\% 的点对超过 1100\,s、
\QthreeDpBlackoutCapPct\% 的点对甚至超过 DP 中采用的换位窗口截断上限 $W_{\max}$。""")
new = (r"""在 \QthreeDpCandPts{} 个候选点上枚举全部点对（\QthreeDpCandPairs{} 对）后，
按\textbf{精确秒数}（\emph{不使用任何窗口截断}）统计全部 \QthreeDpBlackoutPairs{} 个 Mode 1 点对，
黑障窗口 $W$ 的分布为：最小 \QthreeDpBlackoutMinS\,s、中位 \QthreeDpBlackoutMedianS\,s、
平均 \QthreeDpBlackoutMeanS\,s、最大 \QthreeDpBlackoutMaxS\,s，
其中 \QthreeDpBlackoutGePct\% 的点对超过 1100\,s。
\emph{（口径声明：早期版本曾在 DP 中对 $W$ 施加一个截断上限 $W_{\max}$ 以控制状态规模，
该截断\textbf{已移除}——现在 $w$ 由精确秒数向上取整到格数，故不再引用 $W_{\max}$。）}""")
assert s.count(old) == 1, ("paper", s.count(old))
s = s.replace(old, new)
io.open(TEX, "w", encoding="utf-8").write(s)
print("[OK] paper.tex §7.4 删除 W_max 截断口径")

# ---------- 2) 宏表注释 ----------
m = io.open(MN, encoding="utf-8").read()
old2 = '''    "QthreeDpBlackoutCapPct": "10.7",'''
if old2 in m:
    m = m.replace(old2, '''    "QthreeDpBlackoutPairs": "42230",             # Mode 1 全点对数（精确秒数，无截断）''')
    print("[OK] make_numbers.py：QthreeDpBlackoutCapPct → QthreeDpBlackoutPairs")
old3 = '''    "QthreeDpBlackoutCapPct": "② N=2 不可行性：超过换位窗口截断上限 Wmax 的点对占比 / %",'''
if old3 in m:
    m = m.replace(old3, '''    "QthreeDpBlackoutPairs": "② N=2 不可行性：Mode 1 全候选点对数（精确黑障，无截断）",''')
    print("[OK] make_numbers.py：注释同步")
old4 = '''                "QthreeDpBlackoutMaxS", "QthreeDpBlackoutGePct",
                "QthreeDpBlackoutCapPct", "QthreeDpPhases", "QthreeDpShortPhases",'''
if old4 in m:
    m = m.replace(old4, '''                "QthreeDpBlackoutMaxS", "QthreeDpBlackoutGePct",
                "QthreeDpBlackoutPairs", "QthreeDpPhases", "QthreeDpShortPhases",''')
    print("[OK] make_numbers.py：Q3GAP_ORDER 同步")
io.open(MN, "w", encoding="utf-8").write(m)
print("完成")
