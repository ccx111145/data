# -*- coding: utf-8 -*-
"""_fix_scope.py —— 按审读意见收缩问题三的结论口径（#5 / #8 / #9）。

核心修正：
  * "2 架不可行" 是**在给定运输时序 + 给定候选悬停点集 + 给定状态剪枝设置下"未找到可行解"**，
    不是"所有允许的运输—中继联合调度都不存在方案"；
  * 已完成**构造性验证**的是"3 架可行"（存在性证明）；
  * 主提交方案**不满足**连续通信硬约束，是"库存约束下的最优折中"，
    必须写明其放宽模型与目标，并给出采样核验的误差边界说明。
"""
PT = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"
s = open(PT, encoding="utf-8").read()

# ---------- ① 摘要方框 ----------
old = r"""\textbf{2 架不可行 $\Rightarrow$ 3 架可达 $\Rightarrow$ 缺口 1 架}\\[3pt]"""
new = r"""\textbf{给定运输时序下 2 架无可行解 $\Rightarrow$ 3 架构造可行 $\Rightarrow$ 建议增配 1 架}\\[3pt]"""
if old in s:
    s = s.replace(old, new); print("[OK] 摘要标题")
else:
    print("[MISS] 摘要标题")

old = r"""但在假设 A13 的模型下，库存 \RelayN{} 架中继的 DP 递推至
\textbf{第 \QthreeDpInfeasibleCell{} 格（$t=\QthreeDpInfeasibleT$\,s）即无可行状态}——
这是\textbf{判定性结论而非搜索失败}；把规模取为 $N=\QthreeNeedN$ 时
\textbf{存在可行解，\QthreeDpInstances{} 个实例全覆盖、零时序冲突}。
故\textbf{最小增配 $=\QthreeGapN$ 架中继无人机，能源组件无需增加}"""
new = r"""在\textbf{冻结的运输时序}与\textbf{给定的候选悬停点集}（$0.0035^\circ$ 网格 $\times$ 3 档离地高度，
共 \QthreeDpCandPts{} 点）下，状态 DP 与构造性判定在 $N=\RelayN$ 时\textbf{均未找到可行解}，
递推在较早的需求格处即无可行状态；把规模取为 $N=\QthreeNeedN$ 时\textbf{可构造出可行解：}
\QthreeDpInstances{} 个需求实例\textbf{全覆盖、零时序冲突}，并已通过独立逐时刻仿真复核。
故\textbf{建议增配 $=\QthreeGapN$ 架中继无人机，能源组件无需增加}"""
if old in s:
    s = s.replace(old, new); print("[OK] 摘要正文")
else:
    print("[MISS] 摘要正文")

# ---------- ② §7.6 标题与结论 ----------
old = r"""\subsubsection{结论：$N=2$ 不可行，首个崩溃格为第 \QthreeDpInfeasibleCell{} 格}"""
new = r"""\subsubsection{结论：$N=2$ 未找到可行解（在给定运输时序与候选点集下）}"""
if old in s:
    s = s.replace(old, new); print("[OK] §7.6 标题")
else:
    print("[MISS] §7.6 标题")

old = r"""\begin{center}
\fbox{\parbox{0.94\linewidth}{\centering
\textbf{结论（判定性，非搜索失败）}\\[2pt]
2 架中继在「一次架次 $=$ O01 $\to$ 单一悬停点 $\to$ O01」模型下\textbf{无可行解}；
不可行性由状态 DP 在第 \QthreeDpInfeasibleCell{} 格（$t=\QthreeDpInfeasibleT$\,s）给出，
且该结论与前文「几何上处处可覆盖」相互独立——\textbf{瓶颈是时序，不是几何}。}}
\end{center}"""
new = r"""\begin{center}
\fbox{\parbox{0.94\linewidth}{\centering
\textbf{结论（受限口径，须如实理解）}\\[2pt]
在\textbf{冻结的运输时序}与\textbf{给定候选点集}下，2 架中继\textbf{未找到}满足全程连续通信的
调度方案：状态 DP 与构造性判定分别在不同需求格处无可行状态。
该结论与前文「几何上处处可覆盖」相互独立——\textbf{瓶颈是时序，不是几何}。\\[2pt]
\textbf{必须同时声明三点}：(i) DP 的候选点集按每格前 $k$ 个截断、状态按代价与数量剪枝，
故其输出\textbf{不构成"完整状态空间无解"的证明}（见 \S\ref{sec:q3robust}）；
(ii) 该结论\textbf{只对冻结的运输时序成立}，原题允许重新决定组批、路线与运输开始时刻，
本文\textbf{未}证明"所有允许的运输—中继联合调度都不存在 2 架可行方案"；
(iii) 已完成\textbf{构造性验证}的是 $N=\QthreeNeedN$ 时的可行性（给出具体方案并逐时刻复核）。}}
\end{center}"""
if old in s:
    s = s.replace(old, new); print("[OK] §7.6 方框")
else:
    print("[MISS] §7.6 方框")

# ---------- ③ §7.6 最小增配段 ----------
old = r"""\item 因此\textbf{最小增配为 \QthreeGapN{} 架中继无人机，且无需增加能源组件}：
$\text{需求}\ \QthreeNeedN\ -\ \text{库存}\ \RelayN=\QthreeGapN$ 架。"""
new = r"""\item 因此在\textbf{已完整验证的配置}中，最小可行规模为 $N=\QthreeNeedN$，
相对库存需\textbf{增配 \QthreeGapN{} 架中继无人机}（能源组件无需增加）。
\emph{这不等于"数学上最少必须 3 架"}——2 架在更强的候选集/无剪枝搜索下是否仍不可行，
以及通过重新优化运输时序能否降到 2 架，均列为后续工作（见 \S\ref{sec:q3manage} 与
\S\ref{sec:limits}）。"""
if old in s:
    s = s.replace(old, new); print("[OK] §7.6 增配段")
else:
    print("[MISS] §7.6 增配段")

# ---------- ④ §7.7 模式对比结论 ----------
old = r"""\noindent\textbf{结论}：空中转场把 $N=2$ 的首个失败时刻推后约 $1530$\,s，
但\textbf{并未使其可行}。因此「2 架不够」\textbf{不是假设 A13 的产物}，
而是运输需求的时空结构与地形遮挡共同决定的\textbf{结构性结论}。"""
new = r"""\noindent\textbf{结论}：空中转场把 $N=2$ 的首个失败时刻推后约 $1530$\,s，
但\textbf{仍未找到可行解}。因此在本文的判定口径下，
「$N=2$ 排不出连续覆盖」\textbf{不能归因于"换位必须回基地"这一条假设}；
它更像是运输需求的时空结构与地形遮挡共同造成的\textbf{时序瓶颈}
（而非"已证明在任何换位模式下 2 架都不可能"——见前述受限口径声明）。"""
if old in s:
    s = s.replace(old, new); print("[OK] §7.7 结论")
else:
    print("[MISS] §7.7 结论")

# ---------- ⑤ §7.8 稳健性表下的说明 ----------
old = r"""因此\textbf{不应把某一具体格号当作基本常数}；可以主张的是
「在 12 / 24 / 40 / 400 四档候选规模下 $N=2$ 均不可行」——
\emph{不可行性对候选集稳健，而首个阻塞点会随候选自由度后移}。"""
new = r"""因此\textbf{不应把某一具体格号当作基本常数}；可以主张的是
「在 12 / 24 / 40 / 400 四档候选规模下，$N=2$ \textbf{均未找到可行解}」——
\emph{"找不到"对候选集稳健，而首个阻塞点会随候选自由度后移}。
同时必须承认：本文使用的 DP 带候选截断（每格前 $k$ 个点）与状态剪枝
（代价松弛 $+$ 每位置组合限 2 条 $+$ 状态总数上限），
\textbf{这些操作可能删除"事后才显出价值"的状态}，
因此 DP 的"状态集为空"\textbf{不能等同于"完整状态空间无解"}。
为此本文另设无剪枝的精确模式（完备候选集 $=$ 至少能单独覆盖某格的点集，见 \S\ref{sec:q3dp}），
其结果一并报告于 \texttt{results/重算\_物理修正后.json}。"""
if old in s:
    s = s.replace(old, new); print("[OK] §7.8 说明")
else:
    print("[MISS] §7.8 说明")

open(PT, "w", encoding="utf-8").write(s)
print("done")
