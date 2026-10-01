# -*- coding: utf-8 -*-
"""_fix_paper5.py —— 让 §7.7（换位模式对比）的**文字**与刷新后的宏值一致。

旧文字里的「压缩到原来的约 1/5.6」「成立率从 58% 提到 97%」是按旧物理算的，
重算后（Mode 1 黑障中位 1116 s、强点对 1263 s；Mode 2 471 s / 190 s）需要改为按行陈述，
不再给一个含糊的"约 1/5.6"，而是分别给出全点对与强点对的比值。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")
s = io.open(TEX, encoding="utf-8").read()

old = r"""\noindent 空中转场把黑障压缩到原来的约 $1/5.6$，把 $(\star)$ 的成立率从
\QthreeStarBaseStrongPct\,\% 提升到 \QthreeStarAirStrongPct\,\%，\textbf{量级上的改进是真实的}。
然而，用\S\ref{sec:q3robust}所述的构造性判定器（候选点上限放宽到 400 个）求解 $N=2$："""
new = r"""\noindent 空中转场的效果是\textbf{真实但不足}的：全候选点对的黑障中位由 \QthreeWBaseMedS\,s
降到 \QthreeWAirMedS\,s（约 $1/2.4$），强点对由 \QthreeWBaseStrongS\,s 降到 \QthreeWAirStrongS\,s
（约 $1/6.6$）；对应的 $(\star)$ 成立率由 \QthreeStarBasePct\,\% / \QthreeStarBaseStrongPct\,\%
提升到 \QthreeStarAirPct\,\% / \QthreeStarAirStrongPct\,\%。\textbf{量级上的改进是真实的}，
但仍未达到 $100\%$——即仍有相当一部分时刻无法在换位窗口内找到"另一架单独兜底"的安排。
用\S\ref{sec:q3robust}所述的构造性判定器（候选点上限放宽到 400 个）求解 $N=2$ 的结果如下："""
assert s.count(old) == 1, ("mode prose", s.count(old))
s = s.replace(old, new)

old2 = r"""\noindent\textbf{结论}：空中转场把 $N=2$ 的首个失败时刻推后约 $1530$\,s，
但\textbf{仍未找到可行解}。因此在本文的判定口径下，"""
new2 = r"""\noindent\textbf{结论}：空中转场把 $N=2$ 的首个失败时刻由 $t=\QthreeFailBaseT$\,s
推后到 $t=\QthreeFailAirT$\,s（约 $1530$\,s），但\textbf{仍未找到可行解}。因此在本文的判定口径下，"""
assert s.count(old2) == 1, ("mode conclusion", s.count(old2))
s = s.replace(old2, new2)

io.open(TEX, "w", encoding="utf-8").write(s)
print("paper.tex §7.7 文字已与刷新后的宏值对齐")
