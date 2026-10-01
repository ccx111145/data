# -*- coding: utf-8 -*-
"""_fix_paper4.py —— 论文「模型优点 / 模型局限 / 灵敏度」三节的口径校准。

要点：
  * 删掉「状态完备性给出判定性结论」「上下界夹逼」「已严格证明」这类越界表述（审阅 #2/#4）；
  * 修正与 §7.7 自相矛盾的一句：局限里说「若允许空中转场结论可能改变，列为后续工作」，
    但 §7.7 已经**实现并对比了** Mode 2，且结论未变（审阅 #5/#22 同族问题）；
  * 灵敏度一节把「必须增配到 3 架」改为「未找到 2 架可行解，故建议增配」。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")
s = io.open(TEX, encoding="utf-8").read()
OK, MISS = [], []


def rep(old, new, tag):
    global s
    n = s.count(old)
    if n != 1:
        print("[MISS] %s（%d）" % (tag, n))
        MISS.append(tag)
        return
    s = s.replace(old, new)
    OK.append(tag)
    print("[OK] %s" % tag)


# ---------------- ① 模型优点：「证明出来 / 状态完备性 / 上下界夹逼」 ----------------
rep(r"""\item \textbf{资源缺口是「证明」出来的而非「试」出来的}：问题三把中继换位时序写成状态 DP，
  用\textbf{状态完备性}给出「2 架不够」的判定性结论（第 \QthreeDpInfeasibleCell{} 格无可行状态），
  再用同一 DP 在 $N=\QthreeNeedN$ 下给出全覆盖可行解，
  从而把问题四的中继资源缺口 $\QthreeGapN$ 架从「估算」升级为「上下界夹逼」——
  这比单纯的启发式排程结论更接近工程决策所需的确定性。""",
    r"""\item \textbf{资源缺口有可审计的证据链，而非启发式试错}：问题三把中继换位时序写成状态 DP，
  在候选点集 $\mathcal{C}$ 与剪枝策略 $P$ 下给出「$N=\RelayN$ 未找到可行调度」的结果，
  并由\textbf{独立于 DP 的构造性判定器}在\emph{不同的}需求格处复现失败（四档候选规模
  $12/24/40/400$ 均未找到）；再把 $N=\QthreeNeedN$ 的可行方案\textbf{显式构造出来}并逐时刻复核。
  于是一条「未找到 $2$ 架可行解 $\Rightarrow$ $3$ 架构造可行 $\Rightarrow$ 建议增配 $\QthreeGapN$ 架」
  的证据链成立，问题四的中继缺口据此给出。
  \emph{须同时说明其强度边界}：「$3$ 架可行」是构造性结论（强）；
  「$2$ 架不行」只是\emph{在给定候选集与剪枝下未找到}（弱于数学无解证明），
  二者强度不同，本文分别标注、不合并表述（见 \S\ref{sec:q3infeasible} 的完备性边界）。""",
    "优点：资源缺口证据链措辞")

# ---------------- ② 模型局限：标题与正文的「已严格证明」 ----------------
rep(r"""\item \textbf{库存装备下通信硬约束无法闭合（已严格证明）}：在假设 A13
  「一次架次 $=$ O01 $\to$ 单一悬停点 $\to$ O01、换位必须经 O01」下，
  \RelayN{} 架中继无可行解（第 \QthreeDpInfeasibleCell{} 格、$t=\QthreeDpInfeasibleT$\,s 崩溃，
  见第 \ref{sec:q3infeasible} 节），最小增配为 \QthreeGapN{} 架中继无人机。
  因此本文给出的基准解\textbf{在通信连续性一项上确实欠账}：
  中继 \QthreeCompromiseSorties{} 个架次覆盖 \QthreeCompromiseCoverPct\% 的失联时长，
  未覆盖中断并集约 \QthreeCompromiseUncoveredS\,s（最长一段 \QthreeCompromiseLongestS\,s）。
  本文不把它写成「已满足」，而是如实列入风险台账（见第 \ref{sec:q3robust} 节）。
  需说明该结论的\textbf{边界}：它依赖 A13 的「换位必须回 O01」读法；
  若允许中继在两悬停点之间直接转场，黑障窗口将显著缩短，结论可能改变——
  本文已把该情形列为后续工作（第 \ref{sec:q3robust} 节路径 (i)）。""",
    r"""\item \textbf{库存装备下通信硬约束无法闭合（在给定候选集与剪枝下未找到可行解）}：
  在假设 A13「一次架次 $=$ O01 $\to$ 单一悬停点 $\to$ O01、换位必须经 O01」
  与第 \ref{sec:q3cover} 节的候选悬停点集 $\mathcal{C}$ 下，
  \RelayN{} 架中继\textbf{未找到}满足全程连续通信的调度
  （状态 DP 在第 \QthreeDpInfeasibleCell{} 格、$t=\QthreeDpInfeasibleT$\,s 无可行状态；
  构造性判定在四档候选规模下亦未找到），因此建议增配 $\QthreeGapN$ 架中继无人机。
  据此本文给出的基准解\textbf{在通信连续性一项上确实欠账}：
  中继 \QthreeCompromiseSorties{} 个架次覆盖 \QthreeCompromiseCoverPct\% 的失联时长，
  未覆盖中断并集约 \QthreeCompromiseUncoveredS\,s（最长一段 \QthreeCompromiseLongestS\,s），
  另有 \QthreeCompromiseOutagePhaseN{} 个相位因换位来不及而未派中继（时长合计
  \QthreeCompromiseOutagePhaseS\,s）。本文不把它写成「已满足」，而是如实列入风险台账。
  \textbf{该结论的三条边界}：(a) 实现带四类剪枝，故只能主张「未找到」而非「不存在」；
  (b) 只对\emph{冻结的运输时序}成立，未证明「所有允许的运输—中继联合调度都不存在 2 架方案」；
  (c) 依赖 A13 的「换位必须回 O01」读法——本文已\textbf{实现并对比了 Mode 2（空中直接转场）}
  （\S\ref{sec:q3mode}）：黑障中位由 \QthreeDpBlackoutMedianS\,s 压到
  \QthreeDpBlackoutAirMedianS\,s，但首个失败时刻只是后移到 $t=\QthreeFailAirT$\,s，
  \textbf{仍未找到 2 架可行解}，故该结论不是这条假设的产物。""",
    "局限：通信不闭合结论的强度与边界")

# ---------------- ③ 灵敏度：把「必须增配」改为「建议增配」 ----------------
rep(r"""      \textbf{更关键的是台数}：由第 \ref{sec:q3infeasible} 节的 DP 可知，
      在 300\,m 高度上限下即便候选点几何上处处可覆盖，\RelayN{} 架中继仍因换位黑障窗口
      （中位 \QthreeDpBlackoutMedianS\,s）无法接力，必须增配到 \QthreeNeedN{} 架；""",
    r"""      \textbf{更关键的是台数}：由第 \ref{sec:q3infeasible} 节的判定可知，
      在 300\,m 高度上限下即便候选点几何上处处可覆盖，\RelayN{} 架中继仍因换位黑障窗口
      （中位 \QthreeDpBlackoutMedianS\,s）未能接力（\emph{在给定候选集与剪枝下未找到可行解}），
      故建议增配到 \QthreeNeedN{} 架；""",
    "灵敏度：必须增配 → 建议增配")

# ---------------- ④ 问题一「Pareto 前沿是精确的」限定作用域 ----------------
rep(r"""\item \textbf{问题一精确}：利用同类货箱可互换性把 $2^{n}$ 装箱压缩为
  $\prod(c_k+1)$ 状态空间，所得 Pareto 前沿是精确的，并用 CP-SAT 集合划分 ILP 独立验证。""",
    r"""\item \textbf{问题一在给定模型内精确}：利用同类货箱可互换性把 $2^{n}$ 装箱压缩为
  $\prod(c_k+1)$ 状态空间；对\emph{单个服务区的组批问题}（给定该区货箱清单与机型集合），
  该 DP 是精确的，所得 Pareto 前沿在该子问题内精确，并由 CP-SAT 集合划分 ILP 独立复核。
  \emph{作用域限定}：这里的「精确」不覆盖跨服务区的路线与机型联合决策
  （那属于问题二，本文用 ALNS 求可行解，不主张最优）。""",
    "优点：问题一精确性的作用域")

io.open(TEX, "w", encoding="utf-8").write(s)
print("\n完成：成功 %d，未命中 %d" % (len(OK), len(MISS)))
if MISS:
    print("未命中：%s" % "、".join(MISS))
