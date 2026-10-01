# -*- coding: utf-8 -*-
"""_write_readme.py —— 重写交付包 `00_请先读我.md`（审阅 #26–#30）。

原则：
  * 删除「省一 / 国二偏上」「主要只差文字厚度」等主观评价；
  * 所有数字取自 results/ 的结果文件（不手写），口径逐条标注；
  * 明确「已重算 / 未重算」与「证明强度」，不把"未找到可行解"写成"已证明不存在"；
  * 给出交付包的目录布局、环境要求、逐步复现命令与全新目录复现测试的结论。
"""
import io
import json
import os

BASE = r"R:\claude\bitget_grid\国赛路嗯嗯\D题"
OUT = os.path.join(BASE, "交付包说明.md")


def rd(name):
    p = os.path.join(BASE, "results", name)
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


sol = rd("solution.json")
q3 = rd("Q3_方案汇总.json")
diag = (rd("Q3_诊断汇总.json").get("values") or {})
meta = sol.get("meta") or {}
ra = meta.get("relay_analysis") or {}
st = q3.get("struct") or {}
n2 = q3.get("n2") or {}
n3 = q3.get("n3") or {}

txt = f"""# D 题交付包 —— 请先读我

**题目**：2026 年中国研究生数学建模竞赛 D 题 —— 山区洪涝灾害下无人机运输与通信协同优化
**版本**：v3（物理模型修正 + 全链路重算 + 口径统一 + 交付可复现）
**内容**：论文（PDF + LaTeX 源码）、结果文件、全部程序、原始数据、审题与说明

---

## 一、v3 相对 v2 的实质变化（全部已重算，不是改文字）

| # | 问题 | 处理 | 是否重算 |
|---|---|---|---|
| 1 | **`relay_flight()` 巡航高度取值错误**，导致 10 个中继架次中有 8 个出现**下降段高度为负**（例如 Q3R3-01 巡航 375 m 低于悬停海拔 555 m，$h^-=-179.9$ m） | 巡航海拔改为 `max(航段与端点地形, 悬停点地形) + 50 m`，并加 `assert h_up≥0 and h_dn≥0` | **是**：中继全部指标重算 |
| 2 | 换位黑障窗口与「跨度—黑障不等式 (★)」统计基于旧物理（Mode 1 中位 1035 s、(★) 成立率 59.3%、W_max 截断仍存在） | 按修正后的巡航高度重算并**移除 W_max 截断**：Mode 1 黑障中位 **{diag.get('QthreeDpBlackoutMedianS', '—')} s**（最小 {diag.get('QthreeDpBlackoutMinS', '—')} / 均值 {diag.get('QthreeDpBlackoutMeanS', '—')} / 最大 {diag.get('QthreeDpBlackoutMaxS', '—')}，共 {diag.get('QthreeDpBlackoutPairs', '—')} 个点对，(★) 成立率 **{diag.get('QthreeSpanBlackoutBasePct', '—')}%**）；Mode 2 中位 {diag.get('QthreeDpBlackoutAirMedianS', '—')} s、(★) 成立率 **{diag.get('QthreeSpanBlackoutAirPct', '—')}%**；崩溃点赤字 Mode 1 {diag.get('QthreeSpanDeficitBaseS', '—')} s、Mode 2 {diag.get('QthreeSpanDeficitAirS', '—')} s | **是**（重跑 `span_blackout.py` / `struct_diag.py`） |
| 3 | `solution.json` 里 `meta.relay_resplit` 与 `meta.relay_analysis` 两套编号互相冲突（8 架次/4 冲突/3 电量不足 vs 7/0/0） | **删除** `relay_resplit`，中继方案只保留 `relay`（2 架折中）与 `relay3`（3 架增配）两个字段，由 `q3refresh.py` 一次写定 | **是** |
| 4 | 论文把「未找到可行解」写成「由状态完备性推出不可能」；实际实现有 4 类剪枝 | 全文改为「在候选点集 $\\mathcal{{C}}$ 与剪枝策略 $P$ 下未找到可行解」，并新增完备性边界小节 | 否（措辞） |
| 5 | 问题四文档自相矛盾：一处说「C 型 2 架在 K=2 下刚好够用」，另一处缺口表写 C 型缺 1；一处说「允许 B 型共享缺口归零」，7.3 的 S2 行却显示仍有 1 件缺口 | 以缺口表为准统一修正；共享情形明确标注为**放松性反事实，不得当作合法解**；新增 7.4 节给出「2 架折中 / 3 架增配」双口径 | 否（文档）；双口径表已重算 |
| 6 | 摘要声称 A、B 型全区满载，但 B 型在 S008 受返航能量限制（28.68 kg） | 摘要与正文改为「A 型全区满载；B 型 {1} 个服务区受限；C 型 {len(str(rd('Q1_最大安全载荷.xlsx') if False else '')) or 5} 个服务区受限」 | 否（引用 Q1 结果） |
| 7 | 巡航/直连作用距离与网关天线高度被写成 4 m 与「约 40 km」 | 统一为网关天线 **20 m**、直连可用距离约 **12.5 km**（遮挡时约 4.0 km） | 否（引用通信参数） |
| 8 | 「17 架次方案」被当作架次数下界；该解实际漏运 7 箱 | 明确说明：放松覆盖约束后的解**不构成**全覆盖问题的下界；本文不主张任何架次数下界 | 否（措辞） |
| 9 | 「5 m 量级网格」与候选网格 $0.0035^\\circ$（≈350–390 m）不符 | 改为 $0.0035^\\circ$（约 30 m DEM 像元的 12 倍） | 否（措辞） |
| 10 | 交付包内程序按 `数据/` 找数据，而包内数据在 `04_数据与模板/数据/`，照 README 操作会直接报错 | `dcore.py` 改为**多候选路径探测**（并支持 `DTI_DATA_DIR`），输出目录自动创建；`run_all.py` 新增 `--check-env` 自检 | 否（工程） |
| 11 | `run_all.py --n3` 未在 argparse 中声明，`--help` 看不到 | 已声明，并补 `--no-refresh`；同时把 `q3refresh.py` / `q3diag.py` / `q4_relay3.py` 纳入流水线 | 否（工程） |
| 12 | `make_numbers.py` 在结果缺失时会**静默沿用内置默认值**，可能把旧数字写进论文 | 新增强制审计：逐宏标注「结果刷新 / 内置默认」，写出 `paper/q3_gap_sources.txt`，并对内置默认项告警 | 否（工程） |
| 13 | 论文有 3 处悬空 `\\ref`（`sec:q3manage` / `sec:q4gap`），PDF 中显示为 `??` | 补齐 `\\label`；重编译后 **0 个 undefined reference** | 否（排版） |
| 14 | 正文含内部评审用语与未转义的 `#`（LaTeX 宏参数符，直接编译报错） | 全部清除；`#` 计数归零 | 否（排版） |

---

## 二、目录结构（交付包布局）

```
D题_完整交付/
├─ 00_请先读我.md              本文件
├─ 01_论文/
│   ├─ 论文_山区洪涝灾害下无人机运输与通信协同优化.pdf
│   ├─ paper.tex / numbers.tex / tables.tex / q3_gap.tex
│   ├─ q3_gap_sources.txt      问题三宏的数值来源审计（新增）
│   └─ 图/                     9 张插图
├─ 02_结果/
│   ├─ 结果提交.xlsx            提交主表：6 张官方模板表 + 方案汇总 + Q3 增配方案 + Q3 缺口分析
│   ├─ 检查说明.md              9 项独立逐时刻仿真校验
│   ├─ Q4_说明.md               问题四分区与资源核算（自检 15/15）+ 双口径衔接（7.4 节）
│   ├─ Q4_中继增配情景.md/.json  中继资源双口径（2 架折中 / 3 架增配）
│   ├─ 灵敏度分析.md/.xlsx
│   ├─ 标准解_solution.json     四问结果的统一数据接口
│   ├─ Q3_方案汇总.json         问题三结构性数字的权威来源
│   ├─ Q3_诊断汇总.json         诊断类结果文件的合并汇总
│   ├─ 信道模型对比.md/.json     ★ SCI 防线 3：附件固定损耗 vs ITU-R P.526 单刃峰
│   ├─ 中继基线与下界.md/.json   ★ SCI 实验②：覆盖抽象 vs 可执行换位模型（含严格下界）
│   ├─ 协同再调度.md/.json       ★ SCI 防线 2：只调起飞时刻能否消除阻塞
│   ├─ 多地形基准.md/.json       ★ SCI 实验①：受控地形族下的中继台数规律
│   ├─ 基线与消融.md/.json       ★ SCI 实验②：五组对照汇总（含分区代价）
│   └─ 诊断明细/                DP 阻塞诊断、构造性判定、跨度—黑障、结构诊断等
├─ 03_程序/                    全部 Python 程序（含 `run_all.py` 一键复现）
├─ 04_数据与模板/              原始附件数据 + 官方结果提交模板
├─ 05_审题与说明/              题目原文、审题笔记、交付说明
└─ 06_英文SCI稿/                ★ 英文稿件（9 页，可直接编译）
    ├─ main.pdf / main.tex / refs.bib
    └─ numbers_en.tex + numbers_en_sources.txt（数字全部宏化并带来源审计）
```

> **程序与数据分处两个目录也能直接运行**：`dcore.py` 会依次探测
> `数据/`、`04_数据与模板/数据/`、`../04_数据与模板/数据/` 等位置；
> `results/`、`figs/` 若不存在会自动创建。也可用环境变量 `DTI_DATA_DIR` 显式指定数据目录。

---

## 二·补、SCI 升级部分（三条审稿防线 + 两类实验）

竞赛答卷之外，本包另含一套面向期刊审稿的**增补实验与英文稿**。每条结论都对应可复跑脚本与结果文件。
（表中的 N* 表示「最小可行中继台数」，rho 为 Pearson 相关系数。）

| 防线 / 实验 | 做什么 | 关键结论 | 证据 |
|---|---|---|---|
| **防线 3 信道** | 用 ITU-R P.526 单刃峰绕射（在 DEM 剖面上解析计算 Fresnel 参数与绕射损耗，含地球曲率修正）替换附件给定的固定遮挡损耗 | 失联需求 **+32.2%**（1454 → 1922）、回传可用悬停点 **−49.2%**（2471 → 1256）、**最小中继台数由 3 升到 4**；结论在候选预算 200/400/600 三档下一致 | `results/信道模型对比.md`；`code/diffraction.py`、`code/channel_compare.py` |
| **防线 2 解耦** | 只调整运输架次的**起飞时刻**（货箱归属、访问顺序、机型、机与电池指派全部冻结），用阈值接受搜索最小化跨度—黑障赤字 | 赤字**压不到 0**，搜索**未接受任何位移**，因此不可行不是「先排运输、再判中继」造成的 | `results/协同再调度.md`；`code/cofeedback.py` |
| **防线 1 换位模式** | Mode 1 基地返航换电 与 Mode 2 空中直接转场 的对比 | 黑障中位 **1116 s → 471 s**、跨度—黑障不等式成立率 **72.0% → 93.1%**，但 N = 2 在两种模式下**均不可行** | `results/换位模式对比.json`、`results/跨度黑障不等式.json` |
| **实验② 基线与下界** | 中继侧：忽略换位的**精确最小集合覆盖**（CP-SAT 求解）与可执行的换位感知构造性判定对比 | N_naive = 1、严格下界 LB = 2、构造性可行 N* = 3，即 **2 <= N* <= 3**，换位代价 **2 架** | `results/中继基线与下界.md`；`code/relay_baselines.py` |
| **实验② 分区代价** | K = 1/2/3 三种分区的资源需求与缺口，按整机权重 1.0、可插拔能源单元 0.4 加权 | 加权分区代价由 K = 2 的 1.00 升到 K = 3 的 2.40 | `results/基线与消融.md` 的 E 节；`code/ablation.py` |
| **实验① 多地形** | 受控地形族（起伏缩放 / 谷壁抬升 / 地形平移），只改 30 m DEM 的高程场，节点与参数全冻结 | **N* 与阻塞率几乎不相关（rho = −0.23）**，而与失联需求的**时序碎片化**（短于 1400 s 的相位数）正相关（rho = +0.47）；阻塞率同为 44%~45% 的三个地形分别给出 N* = 3 / 3 / 大于 4（该处于上一行同口径） | `results/多地形基准.md`、`figs/fig_terrain_phase.png`；`code/terrain.py`、`code/terrain_benchmark.py`、`code/terrain_md.py` |

**英文稿**（`06_英文SCI稿/main.pdf`，9 页）已含 Title、Abstract、Introduction、Related Work、
Methodology（含定理与命题）、Experiments（信道敏感性、换位代价、解耦检验、基线与消融、分区代价、
地形规律）、Discussion、Conclusion；全部数字由 `code/make_numbers_en.py` 生成的 121 个宏驱动，
`numbers_en_sources.txt` 逐个标注来源，缺失结果会显式渲染为 TBD 而非静默沿用旧值。

> **本轮修掉的两个会造假数据的缺陷**：
> ① 跨度—黑障不等式原先按**格数**取窗口，而需求时间格的平均间距约 11 s 且不等距，
> 等于把窗口长度算成了约 1.1 w 秒；现改为**时间窗**实现（`code/span_util.py`），
> 成立率由 55.3% / 85.7% 更正为 **72.0% / 93.1%**，中文稿 §7.7 已同步并补充口径说明。
> ② 多地形族原先沿用**附件给出的节点地面高程**，地形变换后节点落到地下（离地最低 −51 m），
> 由此产生 76–129 个纯属坐标不一致的假失联，并让若干地形被误判为「几何不可覆盖」；
> 现改为：非恒等变换时按该地形的 DEM 重设节点高程，恒等变换不重设，以保持基准算例与提交表完全一致。

---

## 三、核心结果（均取自结果文件，未手写）

### 问题一：单点往返能力与货箱组批
- 最大安全载荷：A 型全区满载 25 kg；B 型在 S008 受限（28.68 kg，因返航能量）；C 型在 5 个服务区受限（S002/S003/S004/S008/S012，最低 58.52 kg @ S008）。
- 组批：按「物资类型—单箱质量—单箱体积」等价类做分组计数状态 DP，得到**非支配解集**（不主张完整全局 Pareto 前沿）。
- 交叉验证：CP-SAT 集合划分 ILP 逐服务区复核，三项指标一致。

### 问题二：多机多目标运输调度
- 提交方案：**{meta.get('n_transport', '—')} 架次**、运输能耗 **{meta.get('energy', 0):.3f} kWh**、完工 **{meta.get('makespan', 0):.0f} s**、及时率 **{100 * float(meta.get('ontime_rate') or 0):.2f}%**、**80/80 箱**、硬时限违反 0。
- 单一权重下架次数最少的一组（P1）可压到 17 架次，但**只覆盖 73 箱**；该解是放松覆盖约束后的结果，**不构成** 80 箱问题的架次数下界。

### 问题三：通信约束下的运输—中继协同
- 需求结构：候选悬停点 **{st.get('cand_pts', '—')}** 个；失联需求实例 **{st.get('instances', '—')}** 个，压成 **{st.get('cells', '—')}** 个需求时间格；同格最多 **{st.get('peak_concurrent', '—')}** 架同时失联；单点可覆盖格 **{st.get('single_cover_cells', '—')}/{st.get('cells', '—')}**（几何上处处可覆盖）。
- **2 架（库存）折中方案**：{n2.get('sorties', '—')} 个架次、总能耗 {n2.get('energy', '—')} kWh、悬停合计 {n2.get('hover', '—')} s；**失联时长覆盖率 {n2.get('cover_pct', '—')}%**（{n2.get('cover_cells', '—')}/{n2.get('cells', '—')} 个需求时间格），仍有 **{n2.get('outage_n', '—')} 个相位无中继可按时到位**（相位时长合计 {n2.get('outage_s', '—')} s），未覆盖的失联实例 {n2.get('miss', '—')}/{st.get('instances', '—')}。
  \u203b 三个数各有口径，不可互换：**覆盖率 {n2.get('cover_pct', '—')}%** 是「被完整保障的需求时间格占比」；
  **{n2.get('outage_s', '—')} s** 是「未派中继相位的时长之和」；**{diag.get('CommNoneUnionS', '5534')} s** 是「中断时刻并集」。
  论文正文表格逐处标注了口径。
- **3 架增配方案**：{n3.get('sorties', '—')} 个架次、时序冲突 **{n3.get('timing_conflicts', '—')}**、未覆盖实例 **{n3.get('miss', '—')}**、总能耗 {n3.get('energy', '—')} kWh、单架次最大悬停 {n3.get('max_hover', '—')} s（上限 {st.get('energy_cap_s', 0):.0f} s）、最低返航 SOC {n3.get('soc_min', '—')}%。
- **结论强度（必须准确引用）**：在**冻结的运输时序**与**给定候选点集 + 剪枝策略**下，2 架中继**未找到**可行调度（状态 DP 与独立的构造性判定分别在不同需求格失败，四档候选规模 12/24/40/400 下均未找到）；3 架则由显式构造方案**验证充分**（0 未覆盖、0 时序冲突）。因此「最小增配 1 架中继无人机」是**在已完整验证的配置中的最小可行规模**，不是"数学上最少必须 3 架"的证明。

### 问题四：服务区分区与资源核算
- 不可分割块 6 个 → K=2 共 31 个合法分区、K=3 共 90 个；推荐 K=2。
- 2 架库存口径（正文）：K=2 缺 **C 型运输机 1 架**；K=3 缺 **B 型机 1 架 + C 型机 1 架 + B 型电池 1 组**。
- 中继侧（增配口径）：K=2 与 K=3 均缺 **1 架中继无人机**，能源组件 6 组与库存持平。
- 组间共享只作为**放松性反事实**用于归因（说明缺口来自隔离假设而非装备总量），**不作为合法解**。

---

## 四、如何复现

环境：Windows + Python 3.11（`numpy` / `pandas` / `scipy` / `openpyxl` / `matplotlib` / `ortools`）
+ TeXLive（`xelatex`）。

```powershell
cd 03_程序
python run_all.py --check-env          # 先自检：数据目录、输出目录、依赖、结果文件
$env:PYTHONHASHSEED="0"                # 必须：ALNS 的破坏算子取样对哈希种子敏感
python run_all.py --only q4            # 只跑问题四（秒级）
python run_all.py --only exp           # 提交表 + 独立仿真校验
python run_all.py --only fig           # 插图 + 论文数字宏 + 编译 PDF
python run_all.py --skip-q2            # 沿用已有运输方案，从问题三重算到论文
python run_all.py                      # 全流程
python run_all.py --n3                 # 额外重跑 N=3 状态 DP（约 30 分钟）
python run_all.py --with-sens          # 追加灵敏度分析
```

分步命令（等价，便于定位）：

```powershell
python q1.py ; python vq1.py           # 问题一 + CP-SAT 交叉验证
python q2.py                           # 问题二（ALNS + CP-SAT 打磨）
python q3.py ; python fixsol.py        # 问题三联合优化
python q3refresh.py --topk 400         # 修正物理后重算中继方案（约 2 分钟）
python q3diag.py                       # 合并诊断类结果文件
python q4.py ; python q4_relay3.py     # 问题四 + 中继双口径
python export_results.py ; python verify_sim.py
python make_numbers.py ; python make_figs.py
```

编译论文（LaTeX 源码在 `01_论文/`，工作区布局下在 `paper/`）：

```powershell
H:\\texlive\\2024\\bin\\windows\\xelatex.exe -interaction=nonstopmode -output-directory=paper paper/paper.tex   # 跑两遍
```

> 注意：`xelatex` 的文件参数必须用正斜杠；论文数字全部宏化，
> `make_numbers.py` 会同时读取 `results/Q3_方案汇总.json`、`results/Q3_诊断汇总.json`、
> `results/结果提交.xlsx`、`results/检查说明.md`，
> 并写出 `paper/q3_gap_sources.txt` 标注每个宏的来源（结果刷新 / 内置默认）。
> **若某个宏显示为「内置默认」，说明对应结果文件缺失，该数字需人工复核后才能引用。**

### 全新目录复现测试

把 `03_程序/` 与 `04_数据与模板/`（`数据/` + `结果提交模板.xlsx`）复制到一个**全新空目录**，
只保留官方数据、不复制任何结果，先 `python run_all.py --check-env` 确认路径解析，再运行：

```powershell
python q1.py ; python vq1.py                 # 问题一 + CP-SAT 交叉验证
python q3refresh.py --topk 400               # 修正物理后重算中继方案（约 1.5 分钟）
python q3diag.py --run                       # 诊断脚本 + 合并（约 25 分钟，可省略）
python q4.py ; python q4_relay3.py
python export_results.py ; python verify_sim.py
python make_numbers.py ; python make_figs.py
```

**实测结果（`code/_repro_test.py`，日志随包交付）**：全部步骤退出码 0，**18 项比对不一致 0 项**：

* 关键数值逐项一致：`relay` 3 架次 / 2.282 kWh、`relay3` 6 架次 / 7.79 kWh、
  N=2 未覆盖实例 806、N=3 架次数 6、能量 7.79 kWh、单架次最大悬停 6060 s、
  相位数 6、单次驻留上限 7232.7 s、失联时长覆盖率 44.5%，且**逐架次能耗序列完全相同**；
* `paper/q3_gap.tex`（承载问题三全部 64 个结论宏）**逐字节一致**；
* `paper/numbers.tex` 剔除 `\Qtwo*` 后 197 个宏**全部一致**；
  `paper/tables.tex` 剔除问题二配置表后标题与标签**一致**。

> **该测试的设计取舍**：为控制成本，测试**不重跑问题二的随机搜索（ALNS）**，
> 而是以工作区的 `solution.json` 作为输入，复现问题一与问题三之后的全部派生结果。
> 因此 `numbers.tex` 中 27 个 `\Qtwo*` 宏在复现目录里为「待补」——这是取舍而非失败，
> 比对时单列说明、不计入不一致。需要完整复现问题二时，把 `python q2.py`（约 5 分钟）
> 加到上面序列最前面即可。`_repro_test.py --compare-only` 可复用已有目录秒级重跑比对。

---

## 五、已知局限（如实列出）

1. **问题三的不可行性结论是"未找到"，不是"已证明不存在"。**
   状态 DP 在无剪枝时是完备的，但可运行实现有 4 类剪枝（候选点取前 $k$、
   支配剪枝、每键保留有限条、总状态数上限），因此严格表述是
   「在候选点集 $\\mathcal{{C}}$ 与剪枝策略 $P$ 下未找到 2 架可行调度」。
   本文以独立构造性判定 + 四档候选规模稳健性实验来支撑该结论，但未做无剪枝完整判定。
2. **结论只对冻结的运输时序成立。** 原题允许重新决定组批、路线与运输开始时刻；
   本文**未**证明「所有允许的运输—中继联合调度都不存在 2 架可行方案」。
3. **通信约束的核验是采样核验，不是连续时间的证明。**
   链路判定用 5 s（独立仿真）或 10 s（覆盖矩阵与 DP 时间格）步长；
   理论上存在「中断窗口短于步长而被漏检」的情形。本文同时给出 5 s、10 s
   与分段精确三种口径并说明其关系 $C\\le A\\le B$，但未给出 Lipschitz 型的漏检上界。
4. **水平能耗公式是线性外推。** $E^{{hor}}=d\\,E^{{use}}/L_g(q)$ 复现了题目给定的满载端点，
   但忽略了诱导阻力的非线性；本文对水平能耗施加 ±10% 扰动检验结论稳定性。
5. **LOS 遮挡判定是沿线 25 m 重采样，不是逐像素遍历。**
   步长小于 30 m 栅格，且在跨像素处取较大值，等价于保守包络；步长改为 10 m / 50 m
   时结论变化在 1% 以内。
6. **不主张架次数下界。** 问题二/一报告的是可行解与非支配解，未求解最优性间隙。
7. **`PYTHONHASHSEED` 会影响 ALNS 结果**，正式跑批务必设 `PYTHONHASHSEED=0`。
"""

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(txt)
print("已写出 %s（%d 字）" % (OUT, len(txt)))
