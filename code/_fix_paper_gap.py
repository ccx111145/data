# -*- coding: utf-8 -*-
"""_fix_paper_gap.py —— 修正论文中"最小增配需追加能源组件"的过期表述。
最终结论：增配 1 架中继即可，现有 6 组能源组件足够支撑 3 架中继。"""
import io

P = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"
s = open(P, encoding="utf-8").read()

reps = [
    (r"故\textbf{最小增配 $=\QthreeGapN$ 架中继无人机（外加相应能源组件）}；",
     r"故\textbf{最小增配 $=\QthreeGapN$ 架中继无人机，能源组件无需增加}"
     r"（现有 \RelayBat{} 组即可支撑增配后的 \QthreeNeedN{} 架中继）；"),
    (r"故完整增援清单 $=$ 运输侧 \QfourKind{} $+$ 中继侧 \QthreeGapN{} 架中继与相应能源组件。",
     r"故完整增援清单 $=$ 运输侧 \QfourKind{} $+$ 中继侧 \QthreeGapN{} 架中继无人机"
     r"（能源组件现有库存即可，无缺口）。"),
    (r"\item 因此\textbf{最小增配为 1 架中继无人机 + 相应能源组件}：",
     r"\item 因此\textbf{最小增配为 \QthreeGapN{} 架中继无人机，且无需增加能源组件}："),
    (r"\item \textbf{最小增配为 \QthreeGapN{} 架中继无人机（外加相应能源组件）}。",
     r"\item \textbf{最小增配为 \QthreeGapN{} 架中继无人机，能源组件沿用现有 \RelayBat{} 组}。"),
    (r"\item 故 \textbf{中继无人机缺口 $= \QthreeNeedN-\RelayN=\QthreeGapN$ 架}，另需相应能源组件。",
     r"\item 故 \textbf{中继无人机缺口 $= \QthreeNeedN-\RelayN=\QthreeGapN$ 架}；"
     r"能源组件无缺口（增配后共需 \RelayBat{} 组，与库存持平）。"),
    (r"\QfourKind{}（$K=2$）\textbf{加上}中继侧 \QthreeGapN{} 架中继无人机与相应能源组件。",
     r"\QfourKind{}（$K=2$）\textbf{加上}中继侧 \QthreeGapN{} 架中继无人机（能源组件无缺口）。"),
]
n = 0
for a, b in reps:
    if a not in s:
        print("MISS:", a[:50])
    else:
        s = s.replace(a, b, 1)
        n += 1
open(P, "w", encoding="utf-8").write(s)
print("已替换 %d/%d 处" % (n, len(reps)))
