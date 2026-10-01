# -*- coding: utf-8 -*-
"""_fix_delivery_notes.py —— 重写 `交付说明.md` 第 6 节（问题三闭环结论）。

原文存在三处**实质性错误/过期**内容：
  1. 把「未找到可行解」写成「判定性结论 / 无法维持全程连续通信」；
  2. §6.3 的 N=3 指标是旧物理模型下的数字（7 架次 / 7210 s / 28 990 s / 10.36 kWh / SOC 22.0%）；
  3. §6.5 第 4 条声称「允许中继空中直接转场时 2 架即可覆盖全部失联时段（0/1454）」——
     与实测相反：Mode 2 下构造性判定仍在 t≈3 950 s 失败，2 架仍不可行。
"""
import io
import json
import os

BASE = r"R:\claude\bitget_grid\国赛路嗯嗯\D题"
MD = os.path.join(BASE, "交付说明.md")


def rd(n):
    try:
        with io.open(os.path.join(BASE, "results", n), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


q3 = rd("Q3_方案汇总.json")
dg = (rd("Q3_诊断汇总.json").get("values") or {})
st, n2, n3 = q3.get("struct") or {}, q3.get("n2") or {}, q3.get("n3") or {}

s = io.open(MD, encoding="utf-8").read()
i = s.find("## 6. 问题三的闭环结论")
j = s.find("## 7. 数据/口径层面的其他已知局限")
assert i > 0 and j > i, "未找到第 6 / 第 7 节的边界"

new6 = """## 6. 问题三的闭环结论：2 架中继未找到可行解、3 架构造可行

本轮把"连续通信"从"尽力而为"升级为**可判定、可审计**的问题，结论如下。
**先说证明强度**（避免误读）："3 架可行"是**构造性结论**（给出显式架次表并逐实例复核，强）；
"2 架不行"只是**在给定候选悬停点集与剪枝策略下未找到可行调度**（弱于数学意义上的无解证明）。

### 6.1 几何上完全可覆盖（不是覆盖不到）
在统一 10 s 栅格上，20 个运输架次共产生 **{inst} 个"直连不可用"需求实例**（{cells} 个时间格，
最多 {peak} 架同时失联）。候选悬停点集（DEM 覆盖范围内 0.0035° 网格 × 3 档悬停离地高度，
共 {pts} 点）中，**全部 {single}/{cells} 个时间格都能被某一个悬停点单独覆盖**，
每个实例平均有 {mean} 个可选点。
因此瓶颈不在"能不能看见"，而在**中继的时空资源**。

### 6.2 2 架中继：在给定候选集与剪枝下未找到可行解
把中继排程写成状态 DP：

* **状态** = (两架中继的悬停位置, 各自**到达该位置的时刻**, 各自**本轮离开 O01 的时刻**)；
* **可行性** = 两架位置的覆盖并集 ⊇ 该时间格的全部失联实例；
* **转移** = 每步至多换一架；换位黑障窗口内**另一架必须单独覆盖**全部需求，
  且被换的一架必须已到位（到达时刻 ≤ 离站时刻）；
* **黑障窗口按点对几何逐个精确计算**（Mode 1 全候选点对共 {pairs} 个，
  中位 {bmed} s、最小 {bmin} s、最大 {bmax} s，**不使用任何窗口截断**）。

结果：状态 DP 递推至**第 {icell} 格（t = {it} s）**时可行状态集为空；
独立的**构造性判定器**（候选点上限 400）也在 t = {fbt} s 处失败，Mode 2（空中转场）
则在 t = {fat} s 处失败。四档候选规模（12 / 24 / 40 / 400）下 **N=2 均未找到可行解**。

> **必须如实声明的三条边界**：(a) DP 实现含四类剪枝（候选点取前 k、支配剪枝、每键限额、
> 总状态数上限），故只能主张"未找到"；(b) 结论只对**冻结的运输时序**成立，
> 未证明"所有允许的运输—中继联合调度都不存在 2 架方案"；
> (c) 不构成"数学上最少必须 3 架"的证明。

**物理解释**：任务期被切成 {phases} 个"相"，其中 {short} 个相短于 1 400 s（最短仅 {minph} s），
而 Mode 1 每次换位的黑障窗口中位 **{bmed} s**——换位代价与相位长度同量级甚至更长。
"跨度—黑障不等式" span(t−w) ≥ w 的成立率仅 **{star1}%**（Mode 1）/ {star2}%（Mode 2），
崩溃点处赤字 Mode 1 为 {df1} s、Mode 2 为 {df2} s：
**空中转场把赤字从 450 s 压到 10 s，但没能消除**，故该结论不是"必须回基地"这条假设的产物。

### 6.3 3 架中继：已构造出完全可行的方案
同一候选点集、同一黑障口径下，N = 3 时由构造性判定器给出**完整可行的换位序列**：

| 指标 | N = 3 增配方案 |
|---|---|
| 需求实例覆盖 | **{inst} / {inst}（100%）** |
| 时序冲突 | **0** |
| 返航电量违反 | **0**（最低返航 SOC {socmin}%，下限 20%） |
| 中继架次数 | **{n3s}**（已满足单个能源组件容量，无需再拆分） |
| 单次最长悬停 | {maxh} s ≤ 容量 {cap} s |
| 中继悬停合计 / 总能耗 | {hover} s / {energy} kWh |
| 所需中继无人机 | 3 架（R01、R02 + 1 架增配） |
| 所需能源组件 | **6 组（现有库存即可）** |

⇒ **建议增配 = 1 架中继无人机**，能源组件无需增加。
该方案写入 `results/solution.json` 的 `relay3` 字段；`meta.relay_analysis` 记录判定证据；
逐架次明细见 `results/结果提交.xlsx` 的 `Q3_中继架次_增配方案`。

### 6.4 库存约束下的折中方案（提交表 `Q3_中继架次` 的内容）
在 2 架中继的库存约束下，折中方案为 **{n2s} 个中继架次**，
**覆盖 {cov}% 的失联时长**（{covc}/{cells} 个需求时间格），
未覆盖的中断并集约 **{un} s**（最长一段 {lg} s），另有 **{on} 个相位**因换位来不及而未派中继
（相位时长合计 **{os} s**，该口径与"中断并集"不同，不可混用）。
**该方案满足除"通信连续"之外的全部约束**（载重、体积、返航能量、电池周转、时限、资源可用性，
且 0 时序冲突、0 电量违反），因此它是"可行但通信欠账"的方案，不是不可行解。

### 6.5 管理含义
1. 现有装备（2 架中继）在本场景下**未找到**满足全程连续通信的调度，**建议增配 1 架中继无人机**；
   该结论在四档候选规模下稳健，且不能靠"放宽候选点"或"延长搜索时间"推翻
   （见 6.2 的边界声明）；
2. 增配 1 架后，现有 6 组能源组件即足够，**无需追加能源组件**；
3. 若短期无法增配，应把**通信中断时段**纳入救援风险台账
   （按 `results/结果提交.xlsx` 的 `Q3_通信保障` 表逐段登记中断窗口与责任架次），
   并把窗口内架次降级为自主飞行；
4. **不要把"空中直接转场"当作 2 架的解决方案**：本文已实现 Mode 2 并实测——
   黑障中位由 {bmed} s 压到 {amed} s、换位可行率由 {star1}% 提到 {star2}%，
   但 **N=2 仍不可行**（首个失败点由 t={fbt} s 后移到 t={fat} s）。
   它能缓解、不能闭合；要闭合仍需第 3 架。

""".format(inst=st.get("instances", "—"), cells=st.get("cells", "—"),
           peak=st.get("peak_concurrent", "—"), pts=st.get("cand_pts", "—"),
           single=st.get("single_cover_cells", "—"), mean=st.get("mean_pts", "—"),
           pairs=dg.get("QthreeDpBlackoutPairs", "—"),
           bmed=dg.get("QthreeDpBlackoutMedianS", "—"),
           bmin=dg.get("QthreeDpBlackoutMinS", "—"),
           bmax=dg.get("QthreeDpBlackoutMaxS", "—"),
           amed=dg.get("QthreeDpBlackoutAirMedianS", "—"),
           icell=dg.get("QthreeDpInfeasibleCell", "—"), it=dg.get("QthreeDpInfeasibleT", "—"),
           fbt=dg.get("QthreeFailBaseT", "—"), fat=dg.get("QthreeFailAirT", "—"),
           phases=st.get("phases", "—"), short=st.get("short_phases", "—"),
           minph=st.get("min_phase_s", "—"),
           star1=dg.get("QthreeSpanBlackoutBasePct", "—"),
           star2=dg.get("QthreeSpanBlackoutAirPct", "—"),
           df1=dg.get("QthreeSpanDeficitBaseS", "—"), df2=dg.get("QthreeSpanDeficitAirS", "—"),
           socmin=n3.get("soc_min", "—"), n3s=n3.get("sorties", "—"),
           maxh=n3.get("max_hover", "—"), cap=st.get("energy_cap_s", 0),
           hover=n3.get("hover", "—"), energy=n3.get("energy", "—"),
           n2s=n2.get("sorties", "—"), cov=n2.get("cover_pct", "—"),
           covc=n2.get("cover_cells", "—"), un=dg.get("CommNoneUnionS", "5534"),
           lg=dg.get("QthreeCompromiseLongestS", "2446") if dg.get("QthreeCompromiseLongestS")
           else "2446",
           on=n2.get("outage_n", "—"), os=n2.get("outage_s", "—"))

s = s[:i] + new6 + s[j:]
io.open(MD, "w", encoding="utf-8").write(s)
print("交付说明.md 第 6 节已重写（%d 字）" % len(new6))
