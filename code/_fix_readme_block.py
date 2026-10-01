# -*- coding: utf-8 -*-
"""_fix_readme_block.py —— 修复 `_write_readme.py` 中「二·补 SCI 升级」一节。

之前用字符串替换修改该节，导致 LaTeX 片段被级联替换破坏
（出现 `$LBLB = 2`、`$NN* = 3` 之类），并使 f-string 里出现
「expression part cannot include a backslash」的语法错误。

本脚本把整节重写为**不含花括号、不含反斜杠、不含美元号**的纯文本，
以彻底避开 f-string 的转义规则。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "_write_readme.py")
s = io.open(P, encoding="utf-8").read()

i = s.find("## 二·补、SCI 升级部分")
j = s.find("## 三、核心结果")
assert i > 0 and j > i, (i, j)

NEW = """## 二·补、SCI 升级部分（三条审稿防线 + 两类实验）

竞赛答卷之外，本包另含一套面向期刊审稿的**增补实验与英文稿**。每条结论都对应可复跑脚本与结果文件。
（表中的 N* 表示「最小可行中继台数」，rho 为 Pearson 相关系数。）

| 防线 / 实验 | 做什么 | 关键结论 | 证据 |
|---|---|---|---|
| **防线 3 信道** | 用 ITU-R P.526 单刃峰绕射（在 DEM 剖面上解析计算 Fresnel 参数与绕射损耗，含地球曲率修正）替换附件给定的固定遮挡损耗 | 失联需求 **+32.2%**（1454 → 1922）、回传可用悬停点 **−49.2%**（2471 → 1256）、**最小中继台数由 3 变为大于 3**；结论在候选预算 200/400/600 三档下一致 | `results/信道模型对比.md`；`code/diffraction.py`、`code/channel_compare.py` |
| **防线 2 解耦** | 只调整运输架次的**起飞时刻**（货箱归属、访问顺序、机型、机与电池指派全部冻结），用阈值接受搜索最小化跨度—黑障赤字 | 赤字**压不到 0**，搜索**未接受任何位移**，因此不可行不是「先排运输、再判中继」造成的 | `results/协同再调度.md`；`code/cofeedback.py` |
| **防线 1 换位模式** | Mode 1 基地返航换电 与 Mode 2 空中直接转场 的对比 | 黑障中位 **1116 s → 471 s**、跨度—黑障不等式成立率 **72.0% → 93.1%**，但 N = 2 在两种模式下**均不可行** | `results/换位模式对比.json`、`results/跨度黑障不等式.json` |
| **实验② 基线与下界** | 中继侧：忽略换位的**精确最小集合覆盖**（CP-SAT 求解）与可执行的换位感知构造性判定对比 | N_naive = 1、严格下界 LB = 2、构造性可行 N* = 3，即 **2 <= N* <= 3**，换位代价 **2 架** | `results/中继基线与下界.md`；`code/relay_baselines.py` |
| **实验② 分区代价** | K = 1/2/3 三种分区的资源需求与缺口，按整机权重 1.0、可插拔能源单元 0.4 加权 | 加权分区代价由 K = 2 的 1.00 升到 K = 3 的 2.40 | `results/基线与消融.md` 的 E 节；`code/ablation.py` |
| **实验① 多地形** | 受控地形族（起伏缩放 / 谷壁抬升 / 地形平移），只改 30 m DEM 的高程场，节点与参数全冻结 | **N* 与阻塞率几乎不相关（rho = −0.23）**，而与失联需求的**时序碎片化**（短于 1400 s 的相位数）正相关（rho = +0.47）；阻塞率同为 44%~45% 的三个地形分别给出 N* = 3 / 3 / 大于 4 | `results/多地形基准.md`、`figs/fig_terrain_phase.png`；`code/terrain.py`、`code/terrain_benchmark.py`、`code/terrain_md.py` |

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

"""

s = s[:i] + NEW + s[j:]
io.open(P, "w", encoding="utf-8").write(s)
print("已重写「二·补」整节（不含花括号/反斜杠/美元号）")
