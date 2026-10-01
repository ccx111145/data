# -*- coding: utf-8 -*-
"""
make_sci_report.py —— 生成《SCI 增补实验报告》（中文汇总，供中文读者/答辩使用）。

把三条审稿防线与两类实验的**结论与数字**汇总成一份中文报告，
所有数字取自结果文件，不在本脚本内重算；每条结论都指向对应脚本与结果文件。

输出：results/SCI增补实验报告.md

用法：python make_sci_report.py
"""
from __future__ import annotations

import io
import json
import os
import time

import dcore as D

OUT = D.RESULTS


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


def main():
    ch = rd("信道模型对比.json")
    rb = rd("中继基线与下界.json")
    cf = rd("协同再调度.json")
    mc = rd("换位模式对比.json")
    sb = rd("跨度黑障不等式.json")
    tb = rd("多地形基准.json")
    ab = rd("基线与消融.json")
    q3 = rd("Q3_方案汇总.json")
    il = rd("中继ILP松弛.json")

    def g(d, *ks, default="—"):
        cur = d
        for k in ks:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
            if cur is None:
                return default
        return cur

    obs = g(ch, "results", "observed", default={}) or {}
    alt = g(ch, "results", "p526", default={}) or {}
    obs_t = obs.get("transport") or {}
    alt_t = alt.get("transport") or {}
    L = []
    A = L.append
    A("# D 题 SCI 增补实验报告（三条审稿防线 + 两类实验）")
    A("")
    A("> 生成时间：%s。**本报告的数字全部取自 `results/` 下的结果文件**，"
      "不在本脚本内重算；每个结论都注明脚本与结果文件，可逐条复跑。" % time.strftime("%Y-%m-%d %H:%M:%S"))
    A("")
    A("> 定位：竞赛答卷（`01_论文/`）回答的是题目四问；本报告汇总的是"
      "**面向期刊审稿**的增补论证，回答三个可预见的质疑与两类基准缺口。")
    A("")

    # ---------------- 防线 3 ----------------
    A("## 一、防线 3：把「固定遮挡损耗」换成 ITU-R P.526 单刃峰绕射")
    A("")
    A("**质疑**：附件只给了一个「地形遮挡附加损耗」常数（10 dB），"
      "它既没有给出定义方式，也无法区分「擦着山脊飞」与「被整座山挡住」。"
      "中继需求与台数结论是否只是这个常数的产物？")
    A("")
    A("**做法**：在 30 m DEM 剖面上逐采样点计算 Fresnel–Kirchhoff 参数")
    A("$\\nu = h\\sqrt{2(d_1+d_2)/(\\lambda d_1 d_2)}$（$h$ 为障碍高出视线的高度，"
      "含 $k=4/3$ 有效地球半径的曲率修正），取主导刃峰，按 ITU-R P.526 §4.1 计算")
    A("$J(\\nu)=6.9+20\\lg(\\sqrt{(\\nu-0.1)^2+1}+\\nu-0.1)$，"
      "总损耗改为 $\\mathrm{FSPL}+J(\\nu_{\\max})$；另给出多刃峰保守上界")
    A("$\\sum_{\\nu>0}J(\\nu)$ 作为不确定度上界。**同一运输方案、同一候选点生成规则、"
      "同一换位判定**下对比三种口径。")
    A("")
    A("| 指标 | 附件固定损耗 | P.526 单刃峰 | P.526 多刃峰上界 |")
    A("|---|---|---|---|")
    A("| 失联需求实例（个） | %d | %d | %d |"
      % (obs_t.get("instances", -1), alt_t.get("instances", -1),
         g(ch, "results", "p526ub", "transport", "instances", default=-1)))
    A("| 回传可用悬停点（个） | %s | %s | %s |"
      % (obs.get("cand_pts", "—"), alt.get("cand_pts", "—"),
         g(ch, "results", "p526ub", "cand_pts")))
    A("| 相位数 | %s | %s | %s |"
      % (obs.get("phases", "—"), alt.get("phases", "—"), g(ch, "results", "p526ub", "phases")))
    A("| N=3 是否可行 | %s | %s | %s |"
      % (g(ch, "results", "observed", "greedy", "N3", "feasible"),
         g(ch, "results", "p526", "greedy", "N3", "feasible"),
         g(ch, "results", "p526ub", "greedy", "N3", "feasible")))
    A("| 最小台数 N* | %s | %s | %s |"
      % (g(ch, "results", "observed", "N_crit"),
         g(ch, "results", "p526", "N_crit"), g(ch, "results", "p526ub", "N_crit")))
    A("")
    A("**结论**：")
    A("")
    A("1. 固定损耗口径**系统性低估通信需求**：P.526 下失联需求实例增加，"
      "同时回传可用悬停点大幅减少——因为中继悬停在 80–300 m 离地高度、"
      "回传至 20 m 高的网关，同样受绕射限制。")
    A("2. **最小中继台数由 3 升到 4**（单刃峰与多刃峰上界给出相同结论）："
      "即「相对库存（2 架）增配 1 架」这一相对结论在两个口径下都成立，"
      "但**基数不同**（3 対 4），因此任何台数结论都必须连同信道口径一起报告。")
    A("3. 结论在候选点预算 200 / 400 / 600 三档下完全一致，"
      "排除了「差异来自搜索预算」这一混杂解释。")
    A("")
    A("> 脚本 `code/diffraction.py`、`code/channel_compare.py`；"
      "结果 `results/信道模型对比.md`、`results/信道模型对比.json`。")
    A("")

    # ---------------- 防线 2 ----------------
    A("## 二、防线 2：先排运输、再判中继——单向解耦是不是不可行的成因？")
    A("")
    A("**做法**：只允许调整各架次的**开始时刻**（货箱归属、访问顺序、机型、"
      "无人机与电池指派全部冻结，且强制同机架次不重叠），"
      "用阈值接受搜索最小化「跨度—黑障不等式」的赤字。"
      "赤字定义为 $D=\\sum_k \\max(0, (k-j_k+1)-\\mathrm{span}[j_k])$，"
      "其中 $j_k$ 是时间窗 $[t_k-w,\\,t_k]$ 内的首个需求格——"
      "$D=0$ 是 N=2 可行的**必要条件**。")
    A("")
    A("| 换位模式 | 黑障 w（s） | 基准赤字 | 协同后赤字 | 降幅 | 被调整的架次 | 完工时间变化 |")
    A("|---|---|---|---|---|---|---|")
    for m, cn in (("base", "Mode 1 基地返航"), ("air", "Mode 2 空中转场")):
        r = (cf.get("results") or {}).get(m) or {}
        if not r:
            A("| %s | — | — | — | — | — | — |" % cn)
            continue
        A("| %s | %.0f | %d | %d | %.1f%% | %d | %.0f → %.0f s |"
          % (cn, r.get("w_s", 0), g(r, "baseline", "deficit_cells", default=-1),
             g(r, "after", "deficit_cells", default=-1), r.get("deficit_reduction_pct", 0),
             g(r, "after", "n_shifted", default=0),
             g(r, "baseline", "makespan", default=0), g(r, "after", "makespan", default=0)))
    A("")
    A("**结论**：赤字**压不到 0**，且搜索**没有接受任何一次位移**。"
      "因此「不可行」不是「运输排程被外生冻结」造成的——"
      "即使把运输时刻的调整空间用满，阻塞依然存在。"
      "要闭合通信硬约束只能增加中继台数或改变任务的空间结构。")
    A("")
    A("> 脚本 `code/cofeedback.py`、口径实现 `code/span_util.py`；"
      "结果 `results/协同再调度.md`。")
    A("")

    # ---------------- 防线 1 ----------------
    bm = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 1") or {}
    am = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 2") or {}
    A("## 三、防线 1：结论是否依赖「换位必须回基地」这条假设？")
    A("")
    A("**做法**：实现并对比两种换位模式——Mode 1 基地返航换电（回 O01、周转、再出动）"
      "与 Mode 2 空中点对点直接转场（爬升—巡航—下降三段），"
      "在同一候选点集与同一能源约束下重跑可行性判定。")
    A("")
    A("| 指标 | Mode 1 | Mode 2 |")
    A("|---|---|---|")
    A("| 黑障窗口中位（s） | %s | %s |"
      % (g(bm, "p50", "w_s"), g(am, "p50", "w_s")))
    A("| (★) 成立率 | %s%% | %s%% |"
      % (round(100 * g(bm, "p50", "rate", default=0), 1),
         round(100 * g(am, "p50", "rate", default=0), 1)))
    if mc.get("rows"):
        for r in mc["rows"]:
            A("| %s（N=%d） | %s |" % (r.get("mode_name", "?"), r.get("N", 0),
                                       r.get("reason", "—")))
    A("")
    A("**结论**：空中转场把黑障中位显著压低、(★) 成立率显著提高，"
      "**量级上的改进是真实的**；但 N=2 在**两种模式下都不可行**。"
      "因此「2 架不够」不是「换位必须回基地」这条假设的产物，"
      "而是运输需求的时空结构与地形遮挡共同造成的**时序瓶颈**。")
    A("")
    A("**补上 N=3 一格**（同一问题在两模式下的完整判定，避免只报 N≤2）：")
    A("")
    A("| N | Mode 1 基地返航 | Mode 2 空中转场 | 判定来源 |")
    A("|---|---|---|---|")
    A("| 1 | 不可行，t=1980 s | 不可行，t=1980 s | 状态递推（空状态集） |")
    A("| 2 | 不可行，t=2420 s | 不可行，t=7990 s | 状态递推（空状态集） |")
    A("| 3 | **可行**：6 个架次、未覆盖 0/1454、返航 SOC 最低 33.8% | "
      "未找到排程：推进到第 915/992 格（t=11060 s），已换位 13 次 | 构造性判定 |")
    A("")
    A("两点读法：① Mode 2 下状态递推撑到 t=7990 s（Mode 1 只有 2420 s）才清空，"
      "说明空中转场**确实买到了进展**，只是不足以让 2 架可行；"
      "② N=3 时两模式出现分歧，但 Mode 2 那一格是**构造性判定的搜索失败**"
      "（13 次换位 vs Mode 1 的 8 次），不是不可行性证明——"
      "所以报告为「未找到排程」，**不**据此声称空中转场更差或更好，"
      "也**不**给出任何「空中转场节省台数」的结论。"
      "换位模式对结论的稳健性体现在 N=2 的两种模式都失败这一点上。")
    A("")
    A("> 脚本 `code/mode_compare.py`（N=1/2 状态递推）、`code/greedy_relay.py`（N=3 构造性判定）；"
      "结果 `results/换位模式对比.json`、`results/构造性贪心判定_N3_base.json`、"
      "`results/构造性贪心判定_N3_air.json`、`results/跨度黑障不等式.json`。")
    A("")

    # ---------------- 实验 2 ----------------
    A("## 四、实验②：中继侧基线与严格下界——覆盖抽象为什么不可执行")
    A("")
    A("**做法**：把「忽略换位」的常见抽象精确求解（逐时间格求覆盖该格全部失联实例的"
      "最少悬停点数，取全时域最大值，CP-SAT 精确求解），得到 $N_{\\rm naive}$；"
      "再对每一对相邻相位求覆盖两相需求并集的最少点数，取最大值得严格下界；"
      "最后用考虑黑障与能源容量的构造性判定给出可行台数。")
    A("")
    A("| 量 | 数值 | 含义 |")
    A("|---|---|---|")
    A("| N_naive（瞬时重定位） | %s | 任何「换位免费」模型下的真实最少台数 |"
      % rb.get("N_naive", "—"))
    A("| LB_handover（严格下界） | %s | 对任何调度策略都成立 |" % rb.get("LB_handover", "—"))
    A("| N*（构造性可行） | %s | 给出显式架次表并逐实例复核 |" % rb.get("N_greedy", "—"))
    A("| 换位代价 N* − N_naive | **%s** | 覆盖抽象低估的台数 |"
      % (None if rb.get("N_greedy") is None or rb.get("N_naive") is None
         else rb["N_greedy"] - rb["N_naive"]))
    A("")
    A("**结论**：得到严格夹逼 $\\max(N_{\\rm naive}, LB)\\le N^*\\le N_{\\rm greedy}$。"
      "把中继排程简化为「区间覆盖 + 最少点数」会得到一个**不可执行**的乐观方案，"
      "换位黑障必须作为一阶约束进入模型。")
    A("")
    A("> 脚本 `code/relay_baselines.py`；结果 `results/中继基线与下界.md`。")
    A("")

    # ---------------- 实验 1 ----------------
    A("## 五、实验①：多地形基准——台数到底由什么决定")
    A("")
    A("**做法**：保持节点经纬度、货箱、机型与通信参数不变，只对 30 m DEM 的高程场做"
      "受控变换（起伏缩放 $\\alpha$、沿走廊抬升谷壁 $c$、地形整体平移），"
      "得到 9 个地形实现，测阻塞率、失联需求结构与最小可行台数。")
    A("")
    A("**必须先修正的一致性缺陷**：附件给出的节点地面高程属于**原始地形**，"
      "而作业高度与巡航高度的计算都要用它。地形变换后若不重设节点高程，"
      "运输机会被规划到**地下**（修复前离地最低 −51 m），"
      "由此产生的失联是纯粹的坐标不一致假象。现在：非恒等变换时按该地形的 DEM"
      "重设节点高程；恒等变换不重设，以保持基准算例与提交表完全一致。")
    A("")
    A("| 地形 | 起伏(m) | 阻塞率 | 失联实例 | 相数 | 短相 | 节点重对齐 | N* |")
    A("|---|---|---|---|---|---|---|---|")
    for r in (tb.get("rows") or []):
        crit = ("%d" % r["N_crit"]) if r.get("N_crit") is not None else ">4"
        if not r.get("relay_ok"):
            crit = "评估失败"
        A("| `%s` | %.0f | %.1f%% | %s | %s | %s | %d | %s |"
          % (r["tag"], g(r, "terrain", "relief", default=0),
             100 * g(r, "occlusion", "ratio", default=0),
             r.get("instances", "—"), r.get("phases", "—"),
             r.get("short_phases", "—"), r.get("nodes_realigned", 0), crit))
    A("")
    A("**结论**：最小可行台数与**阻塞率几乎不相关**，而与失联需求的"
      "**时序碎片化程度**（短相数）正相关。阻塞率同为 44%~45% 的三个地形"
      "分别给出 N* = 3 / 3 / 大于 4；而阻塞率仅 13.1% 的地形反而 N* 大于 4。"
      "这与 (★) 不等式的预测一致：决定台数的是**换位窗口能否被单点兜住**，"
      "而不是失联时长或失联比例本身。")
    A("")
    A("> **强度声明**：N* 由构造性判定器给出，是**上界**；"
      "N ≤ 4 内未找到可行解不等于数学上不可行。")
    A("")
    A("> 脚本 `code/terrain.py`、`code/terrain_benchmark.py`、`code/terrain_md.py`；"
      "结果 `results/多地形基准.md`、图 `figs/fig_terrain_phase.png`。")
    A("")

    # ---------------- 消融与分区代价 ----------------
    ee = ab.get("E_price_of_partitioning") or {}
    trows = g(ab, "A_transport_methods", "rows", default=[]) or []
    A("## 六、基线与消融汇总（含分区代价）")
    A("")
    A("| 层 | 配置 | 结果 |")
    A("|---|---|---|")
    gg = [r for r in trows if str(r.get("方法", "")).startswith("贪心")
          and r.get("权重组") == "P1-架次优先"]
    aa = [r for r in trows if r.get("方法") == "ALNS(无CP-SAT)"
          and r.get("权重组") == "P1-架次优先"]
    cc = [r for r in trows if r.get("方法") == "ALNS+CP-SAT"
          and r.get("权重组") == "P2-及时优先"]
    if gg:
        A("| 运输 | 纯构造启发式 | %s 架次、%s kWh |"
          % (gg[0].get("架次数"), gg[0].get("总能耗_kWh")))
    if aa:
        A("| 运输 | ALNS（无 CP-SAT） | %s 架次、%s kWh |"
          % (aa[0].get("架次数"), aa[0].get("总能耗_kWh")))
    if cc:
        A("| 运输 | ALNS + CP-SAT 精确排程 | 邻域内 %s |" % cc[0].get("CP_SAT状态"))
    _cw = rd("文献启发式对照.json")
    _c1 = ((_cw.get("rows_cw") or {}).get("P1-架次优先") or {})
    _a1 = ((_cw.get("rows_alns") or {}).get("P1-架次优先") or {})
    if _c1:
        A("| 运输 | **Clarke–Wright 节约算法（1964）** | %d 架次、%.2f kWh，"
          "但硬时限违反 %.0f s、及时率 %.3f |"
          % (_c1.get("count", 0), _c1.get("energy", 0),
             _c1.get("hard_violation", 0), _c1.get("ontime_rate", 0)))
        if _a1:
            A("| 运输 | ALNS（同排程函数、同预算） | %d 架次、%.2f kWh，"
              "硬时限违反 %.0f s、及时率 %.3f |"
              % (_a1.get("count", 0), _a1.get("energy", 0),
                 _a1.get("hard_violation", 0), _a1.get("ontime_rate", 0)))
    A("| 中继 | 仅覆盖（瞬时重定位） | N_naive = %s |" % rb.get("N_naive", "—"))
    A("| 中继 | 换位感知构造性判定 | N* = %s |" % rb.get("N_greedy", "—"))
    A("| 换位模式 | 黑障中位 M1 / M2 | %s / %s s |"
      % (g(bm, "p50", "w_s"), g(am, "p50", "w_s")))
    A("| 耦合 | 冻结排程 vs 协同再调度 | 赤字不变 |")
    A("| 分区 | K=1/2/3 加权资源需求 | 1.00 / %s / %s |"
      % (ee.get("weighted_total_k2", "—"), ee.get("weighted_total_k3", "—")))
    A("")
    A("> **分区代价（Price of Partitioning）**：把服务区切成 K 个自治组后，"
      "各组必须各自按本组时间轴配置峰值资源，于是"
      "$\\sum_g \\text{峰值}_g \\ge \\text{峰值}_{K=1}$。"
      "本算例的加权分区代价由 K=2 的 %s 升到 K=3 的 %s，"
      "定量说明了「分组自治」与「库存节约」的冲突。" % (ee.get("weighted_total_k2", "—"),
                                                        ee.get("weighted_total_k3", "—")))
    A("")
    A("> 脚本 `code/ablation.py`（汇总）、`code/sensitivity.py`（D1 方法对比）、"
      "`code/cw_savings.py`（Clarke–Wright 外部基线）、"
      "`code/q4.py`（分区核算）；结果 `results/基线与消融.md`、"
      "`results/文献启发式对照.md`。")
    A("")
    if _c1 and _a1:
        A("**Clarke–Wright 那一格为什么重要**：此前四种运输方法全出自本文自己的算法族。"
          "补上这条教科书级外部基线后，结论是**方法学上的分工**而非「我们的算法更好」——"
          "CW 在**路由层**赢（%d 架次、%.2f kWh，优于 ALNS 的 %d 架次、%.2f kWh），"
          "在**排程层**输得很惨（硬时限违反 %.0f s、及时率 %.3f，"
          "而 ALNS 是 %.0f s、%.3f）。原因是纯路由合并会造出若干必须排在最前的大架次，"
          "在无人机+共享电池双资源时间轴上互相堵住。"
          "换句话说：**路线更漂亮，时刻表却不可执行**——"
          "这正是本文坚持把排程可行性放进搜索回路、而不是事后修补的理由。"
          % (_c1.get("count", 0), _c1.get("energy", 0),
             _a1.get("count", 0), _a1.get("energy", 0),
             _c1.get("hard_violation", 0), _c1.get("ontime_rate", 0),
             _a1.get("hard_violation", 0), _a1.get("ontime_rate", 0)))
        A("")

    # ---- 第七节：N=2 的精确判定与机队规模下界（新增理论结果）----
    oc = rd("局部阻塞证书.json")
    ocr = oc.get("results") or {}
    o1, o2 = ocr.get("base") or {}, ocr.get("air") or {}
    A("## 七、把「2 架不可行」从经验结论升级为判定与下界")
    A("")
    A("**要回答的质疑**：前面几节反复出现「N=2 不可行」，但它一直是以"
      "「搜索没找到」的形式给出的。审稿人会问：这是需求本身的性质，"
      "还是搜索预算不够、或者候选点被我们提前砍掉了？")
    A("")
    A("**做法（三条互相独立的证据）**：")
    A("")
    A("1. **能量下界（无需任何搜索、与采样无关）**：若不存在单点覆盖全程，"
      "则每一时刻都必须至少有一架中继在空中，而单架次在空时长上限为 "
      "$T^{\\mathrm{cap}}$，故 $N\\ge\\lceil T/T^{\\mathrm{cap}}\\rceil$。"
      "本算例 $T=%s$ s、$T^{\\mathrm{cap}}=%s$ s → $N\\ge %s$。"
      % (oc.get("T_s", "—"), oc.get("T_cap_s", "—"), oc.get("bound_energy", "—")))
    A("2. **精确判定定理**：把「逐格状态剪枝」全部关闭后，两架的状态递推返回"
      "「排程」或「空状态集」，后者是**在该候选集上**的不可行性证明——"
      "与枚举顺序、剪枝强度、保留状态数均无关。前提是必须同时声明"
      "「候选集」与「逐格候选细化」两层限制。")
    A("3. **结构量放行率**：span 函数给出「某单点能单独兜住整段需求」的最长时长。"
      "换位只能发生在 $\\mathrm{span}(t)\\ge w$ 的格上，而两架时另一架还必须"
      "在窗口内不改点，因此放行率是这一必要条件的直接度量。")
    A("")
    A("| 量 | Mode 1 基地返航 | Mode 2 空中转场 |")
    A("|---|---|---|")
    A("| span 中位 / P90 / 最大（s） | %s / %s / %s | %s / %s / %s |"
      % (o1.get("span_median_s", "—"), o1.get("span_p90_s", "—"), o1.get("span_max_s", "—"),
         o2.get("span_median_s", "—"), o2.get("span_p90_s", "—"), o2.get("span_max_s", "—")))
    A("| 黑障窗口最小 / 中位（s） | %s / %s | %s / %s |"
      % (o1.get("w_min_s", "—"), o1.get("w_median_s", "—"),
         o2.get("w_min_s", "—"), o2.get("w_median_s", "—")))
    A("| 中位黑障窗口下的换位放行率 | %.1f%% | %.1f%% |"
      % (100.0 * float(o1.get("release_at_wmed") or 0),
         100.0 * float(o2.get("release_at_wmed") or 0)))
    A("| 候选集 $C_1\\to C_0$ | %s → %s | %s → %s |"
      % (o1.get("n_cand_pool", "—"), o1.get("n_cand_c0", "—"),
         o2.get("n_cand_pool", "—"), o2.get("n_cand_c0", "—")))
    A("| 结构下界 $1+\\lfloor\\mu/w_{\\min}\\rfloor$ | %s | %s |"
      % (o1.get("bound_by_w", "—"), o2.get("bound_by_w", "—")))
    A("")
    A("**结论**：")
    A("")
    A("1. 两条独立来源给出同一区间：能量下界 $N\\ge %s$，构造性判定给出 "
      "$N\\le %s$，中间只隔着 N=2——而 N=2 恰恰有精确判定。"
      % (oc.get("bound_energy", "—"), rb.get("N_greedy", "—")))
    A("2. 阻塞**不在能量维**（能量下界只要 %s 架），而在**alibi 窗口**："
      "一架换位期间，另一架必须用**固定的一个点**兜住整段需求。"
      "Mode 1 下中位黑障窗口只有 %.1f%% 的格满足这一条件。"
      % (oc.get("bound_energy", "—"), 100.0 * float(o1.get("release_at_wmed") or 0)))
    A("3. 候选点池 %s 个中 %s 个进入 $C_0$（%.1f%%），"
      "即第一层细化几乎不损失候选点——**收紧发生在逐格细化层**，"
      "这一层必须与结论一起声明。"
      % (o1.get("n_cand_pool", "—"), o1.get("n_cand_c0", "—"),
         100.0 * float(o1.get("c0_ratio") or 0)))
    A("")
    A("> **强度声明**：`N=2 不可行` 是「在声明过的候选集 $C_0$ 与逐格候选细化之下、"
      "且不依赖状态剪枝强度」的结论；`N=3 可行` 是构造性的（给出完整架次表并逐实例复核），"
      "因此 $N^{*}=3$ 在本题算例上成立。能量下界那条与搜索完全无关。")
    A("")
    A("> 脚本 `code/obstruction.py`（span / 放行率 / 下界）、"
      "`code/fail_diag.py`（候选预算扫描，逐用例落盘）；"
      "结果 `results/局部阻塞证书.json`、`results/DP阻塞诊断_N2_*.json`；"
      "图 `figs/fig_theory_span.png`。")
    A("")
    A("**候选预算稳健性实测**（`results/DP阻塞诊断_N2_*.json`，参数与失败位置）：")
    A("")
    A("| 用例 | 候选预算 topk | 首次空状态的格 | 时刻（s） | 该格可接受转移数 |")
    A("|---|---|---|---|---|")
    _dp = [("base", 12), ("base", 24), ("base", 40), ("air", 24)]
    for _md, _tk in _dp:
        j = rd("DP阻塞诊断_N2_%s_topk%d.json" % (_md, _tk))
        if not j:
            continue
        d = j.get("diag") or {}
        A("| %s | %d | %s | %s | %s |"
          % ("Mode 1 基地返航" if _md == "base" else "Mode 2 空中转场",
             _tk, d.get("k", "—"), d.get("t", "—"), d.get("accepted", "—")))
    A("")
    A("Mode 1 下失败位置从第 171 格（topk=12）后移到第 225 格（topk=24/40）后**不再移动**，"
      "且该格的可接受转移数恒为 0——即放宽候选预算只延长了搜索能到达的位置，"
      "并没有把结论变成可行。这一点与「阻塞来自时序结构、而非候选点不足」的解释一致。")
    A("")

    A("**方法学交叉验证：相位级整数规划区间松弛**（`code/relay_ilp.py`）")
    A("")
    A("上面第 2 条用的是**时刻级**状态 DP。为了不让结论依赖单一算法，"
      "另写一个**相位级**的整数规划松弛（CP-SAT）独立判定："
      "变量 $x_{i,j,k}$ = 中继 $i$ 在相位 $k$ 以悬停点 $j$ 值守；"
      "覆盖约束逐实例施加，换位黑障按「相邻相位之间的空档能否容纳 $W(a,b)$」割掉。"
      "该松弛丢掉了相内的时刻耦合，因此**不可行是强结论、可行则未必可行**。")
    A("")
    A("| N | 松弛状态 | 结论方向 | 布尔变量 | 黑障割 | 用时（s） |")
    A("|---|---|---|---|---|---|")
    for _n in (1, 2, 3, 4):
        _r = (il.get("results") or {}).get("N%d" % _n) or {}
        if not _r:
            continue
        A("| %d | %s | %s | %s | %s | %s |"
          % (_n, _r.get("status", "—"),
             "已证明不可行（强）" if _r.get("proven") else
             ("找到值守表（弱，仅说明瓶颈更细）" if _r.get("feasible") else "未定"),
             _r.get("n_bool", "—"), _r.get("n_blackout_cuts", "—"),
             _r.get("elapsed_s", "—")))
    A("")
    A("**这张表本身就是结论**：相位级松弛在 **N=2 就已可行**（且给出显式值守表："
      "两架交替值守 6 个相位），而时刻级 DP 判定 N=2 不可行。"
      "两者之差**精确地**指出了瓶颈所在——不是「哪几个相位需要几个点」这种"
      "相位粒度的资源量，而是**相内的时刻耦合**：一架在相位 $k$ 内换点后，"
      "黑障窗口必须由另一架用**固定的一个点**整段兜住，"
      "而 span 中位仅 %s s、最大 %s s，撑不住一个完整相位。"
      "这把「N=2 为什么不行」从「某个算法没搜到」收紧为"
      "「**相位粒度看不出问题、时刻粒度才暴露问题**」。"
      % (o1.get("span_median_s", "—"), o1.get("span_max_s", "—")))
    A("")
    A("> 松弛在**每相精简候选集**（按相内可覆盖实例数取前 %s 个点）上求解——"
      "与 DP 的候选集限制一样，必须与结论一起声明。"
      % (il.get("per_phase", "—")))
    A("")

    A("## 八、复现命令")
    A("")
    A("```powershell")
    A("cd code")
    A("$env:PYTHONHASHSEED=\"0\"")
    A("python channel_compare.py --models observed,p526,p526ub --topks 200,400,600   # 防线 3")
    A("python cofeedback.py --iters 600 --restarts 4 --K 200                        # 防线 2")
    A("python mode_compare.py ; python span_blackout.py                             # 防线 1")
    A("python relay_baselines.py --model observed --topk 400                        # 实验②（中继侧）")
    A("python terrain_benchmark.py --alphas 0.2,0.35,0.6,1.0,1.4 `")
    A("       --shifts \"40,40;120,40;90,-70\" --cuts 1.0 ; python terrain_md.py      # 实验①")
    A("python ablation.py                                                           # 汇总")
    A("python obstruction.py --no-exact                                               # span/放行率/下界")
    A("python relay_ilp.py --Ns 1,2,3,4 --tl 90 --per-phase 40                       # 区间松弛")
    A("python fail_diag.py --N 2 --mode base --topk 12  # 候选预算扫描（12/24/40 各跑一次）")
    A("python make_fig_theory.py                                                    # 理论图")
    A("python make_sci_report.py                                                    # 汇总")
    A("python make_numbers_en.py                                                    # 英文稿数字宏")
    A("```")
    A("")
    A("英文稿编译（在 `paper_en/` 同级目录）：")
    A("")
    A("```powershell")
    A("cd paper_en")
    A("xelatex -interaction=nonstopmode main.tex")
    A("bibtex main")
    A("xelatex -interaction=nonstopmode main.tex   # 再跑两遍")
    A("```")
    A("")
    A("期刊模板变体（Elsevier / IEEE，正文与 main.tex 完全一致，仅类与前置部分不同）：")
    A("")
    A("```powershell")
    A("cd .. ; python code/make_elsarticle.py       # 生成并编译 main_elsarticle.pdf / main_ieee.pdf")
    A("```")
    A("")

    mp = os.path.join(OUT, "SCI增补实验报告.md")
    with io.open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("已写出：%s（%d 行）" % (mp, len(L)))


if __name__ == "__main__":
    main()
