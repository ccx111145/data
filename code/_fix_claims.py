# -*- coding: utf-8 -*-
"""_fix_claims.py —— 降级两处过强的 Pareto 表述，并追加"程序与结果文件清单"附录。"""
PT = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"
s = open(PT, encoding="utf-8").read()

reps = [
    # Q2：五组权重得到的只是非支配解，不构成全局前沿的证明
    (r"在 \QtwoConfigN 种权重配置下得到四目标（及时性、完工时间、能耗、架次数）的 Pareto 前沿 \QtwoFrontN 个非支配点。",
     "在 \\QtwoConfigN 种权重配置下得到四目标（及时性、完工时间、能耗、架次数）的 "
     "\\QtwoFrontN{} 个\\textbf{非支配解}。\\emph{需要说明}：加权标量化只能给出非支配解，"
     "\\textbf{不足以证明这是完整的全局 Pareto 前沿}（权重和法会遗漏非凸部分的前沿点）；"
     "本文因此只主张「非支配解集」，并以 ALNS 相对纯构造解的改进幅度说明搜索质量。"),
    # Q1：权重单纯形扫描是前沿的近似枚举
    (r"加权最小的方案，再对权重单纯形扫描（26 格）即得全场景 Pareto 前沿，",
     r"加权最小的方案；由于各服务区相互解耦，全场景可行集是各服务区 Pareto 集的 Minkowski 和，"
     r"再对权重单纯形做 26 格扫描即得\textbf{全场景 Pareto 前沿的近似枚举}，"),
]
for a, b in reps:
    if a in s:
        s = s.replace(a, b)
        print("[OK]", a[:30])
    else:
        print("[MISS]", a[:30])

# ---- 追加"程序与结果文件清单"附录 ----
manifest = r"""

% ===========================================================================
\section*{附录：程序与结果文件清单}
\addcontentsline{toc}{section}{附录：程序与结果文件清单}
% ===========================================================================
本文全部结果均由 \texttt{code/} 下脚本从附件原始数据自动生成，无手工填表。
一键复现：\texttt{python run\_all.py}（须先设置环境变量 \texttt{PYTHONHASHSEED=0}）。

\begin{center}
\small
\begin{tabular}{p{0.30\linewidth}p{0.62\linewidth}}
\toprule
文件 & 作用 \\
\midrule
\texttt{dcore.py} & 统一物理口径核心库：DEM 采样、航段三阶段时间与能耗、等效航程、两阶段充电、FSPL 与双向链路预算、视线遮挡、中继飞行与空中转场 \\
\texttt{comm.py} & 通信层：航迹抽样、直连/接入/回传判定、影子模型 \\
\texttt{cover\_model.py} & 通信兼容性快速评估（航段级缓存，Q3 联合优化用） \\
\texttt{solution\_io.py} & 四问标准数据接口 \texttt{results/solution.json} \\
\midrule
\texttt{q1.py} / \texttt{vq1.py} & 问题一精确求解 / CP-SAT 集合划分交叉验证 \\
\texttt{q2.py} & 问题二 ALNS + CP-SAT 排程打磨 \\
\texttt{q3.py} & 问题三运输—通信联合优化与中继部署 \\
\texttt{q3dpN.py} & \textbf{N 架中继状态 DP（判定性核心，含 Mode 1/2）} \\
\texttt{q3final.py} / \texttt{q3resplit.py} & 不可行性判定与最小增配方案 / 换组件再拆分 \\
\texttt{mode\_compare.py} & 换位模式对比实验（防线 1） \\
\texttt{greedy\_relay.py} & 构造性判定器（排除 DP 候选集截断风险） \\
\texttt{fail\_diag.py} & 阻塞机理诊断（逐条件拒绝计数） \\
\texttt{span\_blackout.py} / \texttt{struct\_diag.py} & 跨度—黑障不等式 / 结构诊断 \\
\texttt{q4.py} & 问题四分区枚举与资源区间着色核算 \\
\texttt{export\_results.py} & 生成提交表（表头与官方模板逐字自检） \\
\texttt{verify\_sim.py} & 独立逐时刻仿真校验（9 项） \\
\texttt{make\_figs.py} / \texttt{make\_numbers.py} & 插图与论文全部数字宏/表格 \\
\texttt{sensitivity.py} & 灵敏度与算法对比实验 \\
\bottomrule
\end{tabular}
\end{center}

\noindent 主要结果文件：\texttt{results/结果提交.xlsx}（6 张模板表 + 方案汇总 +
中继增配方案 + 中继缺口分析）、\texttt{results/检查说明.md}（9 项校验）、
\texttt{results/Q4\_分区配置.xlsx}、\texttt{results/灵敏度分析.xlsx}、
\texttt{results/solution.json}（标准解，含 \texttt{relay} 与 \texttt{relay3}）、
\texttt{results/防线1\_换位模式对比.md}、以及故障诊断/稳健性检验的 JSON 明细。
"""
if "附录：程序与结果文件清单" not in s:
    s = s.replace(r"\end{document}", manifest + "\n\\end{document}")
    print("[OK] 已追加附录")
open(PT, "w", encoding="utf-8").write(s)
print("done")
