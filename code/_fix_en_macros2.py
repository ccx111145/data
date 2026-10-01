# -*- coding: utf-8 -*-
"""_fix_en_macros2.py —— 清除英文稿宏名中残留的 N2 / N3 数字后缀。"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gen = os.path.join(BASE, "code", "make_numbers_en.py")
tex = os.path.join(BASE, "paper_en", "main.tex")

PAIRS = [("ENqN2Cover", "ENqTwoCover"),
         ("ENqN2Outage", "ENqTwoOutage"),
         ("ENqN2Sorties", "ENqTwoSorties"),
         ("ENqN3Energy", "ENqThreeEnergy"),
         ("ENqN3Hover", "ENqThreeHover"),
         ("ENqN3SocMin", "ENqThreeSocMin"),
         ("ENqN3Sorties", "ENqThreeSorties")]

for path in (gen, tex):
    s = io.open(path, encoding="utf-8").read()
    n = 0
    for a, b in PAIRS:
        n += s.count(a)
        s = s.replace(a, b)
    io.open(path, "w", encoding="utf-8").write(s)
    print("%-22s 替换 %d 处" % (os.path.basename(path), n))

gen_s = io.open(gen, encoding="utf-8").read()
gen_s = gen_s.replace('put("ENqN2Cover"', 'put("ENqTwoCover"')
gen_s = gen_s.replace('put("ENqN2Outage"', 'put("ENqTwoOutage"')
gen_s = gen_s.replace('put("ENqN2Sorties"', 'put("ENqTwoSorties"')
gen_s = gen_s.replace('put("ENqN3Energy"', 'put("ENqThreeEnergy"')
gen_s = gen_s.replace('put("ENqN3Hover"', 'put("ENqThreeHover"')
gen_s = gen_s.replace('put("ENqN3SocMin"', 'put("ENqThreeSocMin"')
gen_s = gen_s.replace('put("ENqN3Sorties"', 'put("ENqThreeSorties"')
# 兼容源：这几个宏来自 n2 / n3 字典
gen_s = gen_s.replace('put("ENqTwoCover", fnum(n2.get("cover_pct"), 1)',
                      'put("ENqTwoCover", fnum(n2.get("cover_pct"), 1)')
io.open(gen, "w", encoding="utf-8").write(gen_s)
print("生成器同步完成")
