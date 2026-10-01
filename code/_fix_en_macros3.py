# -*- coding: utf-8 -*-
"""_fix_en_macros3.py —— 清除 ENcf*Mk0 / Mk1 中的数字（\newcommand 名不能含数字）。"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gen = os.path.join(BASE, "code", "make_numbers_en.py")
tex = os.path.join(BASE, "paper_en", "main.tex")

PAIRS = [("Mk0", "MkA"), ("Mk1", "MkB")]
for path in (gen, tex):
    s = io.open(path, encoding="utf-8").read()
    n = 0
    for a, b in PAIRS:
        n += s.count(a)
        s = s.replace(a, b)
    io.open(path, "w", encoding="utf-8").write(s)
    print("%-22s 替换 %d 处" % (os.path.basename(path), n))

# 全量自检：生成后不允许任何含数字的宏名
import re
g = io.open(gen, encoding="utf-8").read()
names = set(re.findall(r'"(EN[A-Za-z0-9]+)"', g))
bad = sorted(n for n in names if any(c.isdigit() for c in n))
print("生成器中含数字的宏名：%s" % (bad if bad else "无"))
