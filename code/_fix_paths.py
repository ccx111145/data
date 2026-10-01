# -*- coding: utf-8 -*-
"""_fix_paths.py —— 把各模块里硬编码的 `os.path.join(D.BASE, "results")` / `"figs"`
统一替换成 `D.RESULTS` / `D.FIGS`（dcore 会自动创建），使交付包里
「03_程序/ + 04_数据与模板/数据/」这种分离布局也能直接跑通并落盘（审阅 #26 / #30）。
"""
import io
import os
import re

CODE = os.path.dirname(os.path.abspath(__file__))
PAT = [
    (re.compile(r'os\.path\.join\(\s*D\.BASE\s*,\s*"results"\s*\)'), "D.RESULTS"),
    (re.compile(r'os\.path\.join\(\s*D\.BASE\s*,\s*"figs"\s*\)'), "D.FIGS"),
    (re.compile(r'os\.path\.join\(\s*BASE\s*,\s*"results"\s*\)'), "D.RESULTS"),
]

n_file = n_sub = 0
for fn in sorted(os.listdir(CODE)):
    if not fn.endswith(".py") or fn == os.path.basename(__file__):
        continue
    p = os.path.join(CODE, fn)
    with io.open(p, "r", encoding="utf-8") as f:
        s = f.read()
    o = s
    for rx, new in PAT:
        s, k = rx.subn(new, s)
        n_sub += k
    if s != o:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(s)
        n_file += 1
        print("[OK] %s" % fn)
print("\n共修改 %d 个文件、%d 处" % (n_file, n_sub))
