# -*- coding: utf-8 -*-
"""_fix_paper6.py —— 论文 §7.7 补充「(★) 不等式的窗口口径」说明，并加一条结论。

背景：`span(t-w) >= w` 里 t、w 都是**时间**，但需求时间格只包含"存在失联"的时刻
（平均间隔约 11 s 且不等距），因此按 `span[k - w/10]` 这种**索引**取窗口是错的。
本轮把该式改为时间窗实现（code/span_util.py），成立率随之由 55.3%/85.7% 变为
72.0%/93.1%。论文必须说明这个口径，否则读者无法复现该数字。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")
s = io.open(TEX, encoding="utf-8").read()

OLD = r"""\noindent 空中转场的效果是\textbf{真实但不足}的：全候选点对的黑障中位由 \QthreeWBaseMedS\,s"""
NEW = r"""\noindent\textbf{窗口口径（可复现性的关键）}：$(\star)$ 中的 $t$ 与 $w$ 都是\emph{时间}，
而需求时间格只包含"存在失联"的时刻（本算例平均间隔约 $11$\,s 且\emph{不等距}），
因此\textbf{不能}按 $w/\Delta$ 折算成格数后用 $\mathrm{span}[k-w/\Delta]$ 取窗口——
那样会把窗口实际长度算成 $1.1w$ 左右。本文的实现按时间取窗：
对第 $k$ 格令 $j_k=\min\{j:\ t_j\ge t_k-w\}$（即 $[t_k-w,\,t_k]$ 内的首个需求格），
要求\textbf{同一个}悬停点单独覆盖 $j_k,\dots,k$ 这一段，即
$\mathrm{span}[j_k]\ \ge\ k-j_k+1$；
赤字定义为
$D=\sum_k\max\bigl(0,\,(k-j_k+1)-\mathrm{span}[j_k]\bigr)$。
其中 $\mathrm{span}[j]$ 必须由\emph{同一个点}的连续可独保格数给出——
若先对各点取并集再找连续段（等价于允许逐格免费换点），$(\star)$ 会退化为恒真，
这也正是把该式写成"不等式"而不是"覆盖计数"的意义所在。
实现见 \texttt{code/span\_util.py}（被黑障统计与协同再调度实验共用）。

\noindent 空中转场的效果是\textbf{真实但不足}的：全候选点对的黑障中位由 \QthreeWBaseMedS\,s"""
assert s.count(OLD) == 1, ("anchor", s.count(OLD))
s = s.replace(OLD, NEW)
io.open(TEX, "w", encoding="utf-8").write(s)
print("[OK] §7.7 已补窗口口径说明")
