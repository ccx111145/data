# -*- coding: utf-8 -*-
"""_fix_facts.py —— 修正事实性错误（#10 网关参数、#15 B 型载荷、#16 ρ=40%、#23 第四问继承口径）。"""
import io, os

PT = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"
s = open(PT, encoding="utf-8").read()
reps = [
    # #10a 网关天线离地高度
    (r"另有固定网关 G01 部署于 O01，天线离地 \TypeAN\,m 量级高度（详见符号表）。",
     r"另有固定网关 G01 部署于 O01，其天线离地高度为附件给定值 \GwAntH\,m。"),
    # #10b 直连门限对应的自由空间距离（40 km -> 12.5 km）
    (r"值得注意的是，门限换算后直连允许损耗 $L_{\max}^{\mathrm{dir}}$ 对应约 40\,km 自由空间距离，",
     r"值得注意的是，门限换算后直连允许损耗 $L_{\max}^{\mathrm{dir}}$ 对应的\textbf{无遮挡}自由空间距离约 "
     r"\DirectRange\,km（远大于本场址 $8$\,km 量级的服务半径），而一旦发生地形遮挡，"
     r"附加损耗后允许距离迅速收缩到 $4$\,km 量级，"),
    # #15 摘要中的 B 型载荷结论
    ("据此用二分法精确求解三种机型在 15 个服务区的最大安全载荷：A、B 型在全部服务区均可满载\n"
     "（\\TypeAQmax\\,kg / \\TypeBQmax\\,kg），仅 C 型在 \\QoneLimitedC 个服务区受返航能量限制，\n"
     "最低为 \\QoneMinPayC\\,kg（\\QoneMinPayCArea）。",
     "据此用二分法精确求解三种机型在 15 个服务区的最大安全载荷：A 型在全部 15 个服务区均可满载\n"
     "（\\TypeAQmax\\,kg）；B 型仅 \\QoneLimitedB{} 个服务区受返航能量限制，最低为 \\QoneMinPayB\\,kg\n"
     "（\\QoneMinPayBArea）；C 型有 \\QoneLimitedC{} 个服务区受限，最低为 \\QoneMinPayC\\,kg（\\QoneMinPayCArea）。"),
]
for a, b in reps:
    if a in s:
        s = s.replace(a, b); print("[OK]", a[:26])
    else:
        print("[MISS]", a[:26])
open(PT, "w", encoding="utf-8").write(s)

# ---- 第四问：在论文的第四问章节补一段"继承哪套方案" ----
anchor = r"\subsection{资源区间着色核算}"
add = r"""\subsection{本文第四问所继承的问题三方案（口径声明）}\label{sec:q4inherit}
原题要求"以问题三得到的联合调度方案为基础"。问题三产生了\textbf{两套}方案，
本文第四问\textbf{明确继承库存口径（2 架中继）下的最优折中方案}，理由是它满足除"通信连续"
之外的全部约束、且不动用库存外的装备；因此：
\begin{itemize}[leftmargin=2.2em,itemsep=2pt]
\item 第四问的分区与资源核算\textbf{基于该折中方案}，其通信保障关系即该方案的
"直连 $+$ 中继 $+$ 中断"分段结果（中断时段如实保留，不因分区而消失）；
\item 若改用\textbf{增配方案}（\QthreeNeedN{} 架中继，全程连续通信），
则中继无人机需求为 \QthreeNeedN{} 架、缺口为 $\QthreeNeedN-\RelayN=\QthreeGapN$ 架；
\textbf{两组口径下的中继缺口不同，引用时必须注明}；
\item 本文在 \S\ref{sec:q4gap} 的缺口表中同时列出两种口径，避免"一边按库存方案分区、
一边引用增配方案的连续通信结论"这种口径混用。
\end{itemize}

"""
if anchor in s and "sec:q4inherit" not in s:
    s = s.replace(anchor, add + anchor, 1)
    open(PT, "w", encoding="utf-8").write(s)
    print("[OK] 已插入 §第四问继承口径声明")
else:
    print("[MISS] 第四问锚点")
print("done")
