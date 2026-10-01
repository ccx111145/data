# -*- coding: utf-8 -*-
"""_fix_macronames.py —— LaTeX 宏名不能含数字，重命名本轮新增的含数字宏。"""
import os
MN = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\make_numbers.py"
PT = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\paper\paper.tex"
FIX = [
    ("QthreeN3GreedySorties", "QthreeNGreedySorties"),
    ("QthreeN3GreedyEnergy", "QthreeNGreedyEnergy"),
    ("QthreeN3GreedySocMin", "QthreeNGreedySocMin"),
    ("QthreeFailCellTopk12", "QthreeFailCellLow"),
    ("QthreeFailCellTopk24", "QthreeFailCellHigh"),
]
for p in (MN, PT):
    s = open(p, encoding="utf-8").read()
    for a, b in FIX:
        n = s.count(a)
        s = s.replace(a, b)
        if n:
            print("[%s] %s -> %s (%d)" % (os.path.basename(p), a, b, n))
    open(p, "w", encoding="utf-8").write(s)
print("done")
