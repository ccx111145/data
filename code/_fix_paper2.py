# -*- coding: utf-8 -*-
"""_fix_paper2.py —— 修正审读发现的正文缺陷：
  (1) QthreeNThreeSortiesCell 默认值 "4（换组件拆分后 7）" → "7（已满足组件容量，无需再拆分）"
  (2) §7.6 关于"还需拆分、架次数会更多"的过期叙述
  (3) "5 m 量级经纬网格" → 0.0035°（≈350–390 m）
  (4) 栅格起点与格号计数口径
  (5) "Δ=DemCell/3=10 s" 的单位错误
  (6) 中继架次数 7/7 的表述
"""
import re

MN = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\make_numbers.py"
PT = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"

s = open(MN, encoding="utf-8").read()
a = '"QthreeNThreeSortiesCell": "4（换组件拆分后 7）"'
b = '"QthreeNThreeSortiesCell": "7（已满足组件容量，无需再拆分）"'
if a in s:
    s = s.replace(a, b)
    open(MN, "w", encoding="utf-8").write(s)
    print("[OK] 宏默认值已修正")
else:
    print("[MISS] 宏默认值未找到")

t = open(PT, encoding="utf-8").read()
reps = [
    # (3) 候选点网格分辨率
    (r"在 DEM 覆盖范围内按 5\,m 量级经纬网格 $\times$ 悬停离地高度",
     r"在 DEM 覆盖范围内按 $0.0035^\circ$ 经纬网格（$\approx350$--$390$\,m，约为 30\,m DEM 像元的 12 倍）$\times$ 悬停离地高度"),
    # (5) 单位错误
    (r"把整段任务期按 $\Delta=\DemCell/3=10$\,s 的统一栅格切成 \QthreeDpCells{} 个\textbf{时间格}",
     r"以 $\Delta=10$\,s 为步长构造统一时间栅格，并\textbf{只保留「至少有一架运输机处于直连不可用」的时刻}，"
     r"共得 \QthreeDpCells{} 个\textbf{需求时间格}"),
]
for x, y in reps:
    if x in t:
        t = t.replace(x, y)
        print("[OK]", x[:34])
    else:
        print("[MISS]", x[:34])
open(PT, "w", encoding="utf-8").write(t)
print("done")
