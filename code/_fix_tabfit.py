# -*- coding: utf-8 -*-
"""_fix_tabfit.py —— 给 make_numbers.py 中列数较多的表加 `fit=True`（缩放到 \\linewidth），
消除交付版 PDF 里剩余的 Overfull \\hbox 表格（审阅 #26 排版质量）。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "make_numbers.py")
s = io.open(P, encoding="utf-8").read()
n = 0
PAIRS = [
    ('rows, align="lrrrrr", size=r"\\footnotesize")',
     'rows, align="lrrrrr", size=r"\\footnotesize", fit=True)'),
    ('rows, align="lrrrrrrrr", size=r"\\footnotesize",',
     'rows, align="lrrrrrrrr", size=r"\\footnotesize", fit=True,'),
    ('rows, align="lllrrrrrrrrr", size=r"\\scriptsize")',
     'rows, align="lllrrrrrrrrr", size=r"\\scriptsize", fit=True)'),
]
for old, new in PAIRS:
    c = s.count(old)
    print("[%s] %d 处：%s" % ("OK" if c == 1 else "MISS", c, old[:56]))
    if c == 1:
        s = s.replace(old, new)
        n += 1
io.open(P, "w", encoding="utf-8").write(s)
print("共修改 %d 处" % n)
