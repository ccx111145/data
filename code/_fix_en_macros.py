# -*- coding: utf-8 -*-
"""_fix_en_macros.py —— LaTeX 控制序列**不能含数字**，把英文稿宏名全部去数字。

映射：
  ENchP526*  -> ENchAlt*        (ITU-R P.526 单刃峰)
  ENchP526ub*-> ENchAltUb*      (多刃峰上界)
  ENch*N1..N4-> ENch*NA..ND
  ENq3*      -> ENq*
  ENcf*D0/D1 -> ENcf*DefA/DefB
"""
import io
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gen = os.path.join(BASE, "code", "make_numbers_en.py")
tex = os.path.join(BASE, "paper_en", "main.tex")

PAIRS = [
    ('("observed", "Obs"), ("p526", "P526"), ("p526ub", "P526ub")',
     '("observed", "Obs"), ("p526", "Alt"), ("p526ub", "AltUb")'),
    ('put("ENch%sN%d" % (tag, N),', 'put("ENch%sN%s" % (tag, "ABCD"[N - 1]),'),
    ("ENq3", "ENq"),
    ("ENcf%sD0", "ENcf%sDefA"),
    ("ENcf%sD1", "ENcf%sDefB"),
]

s = io.open(gen, encoding="utf-8").read()
for a, b in PAIRS:
    n = s.count(a)
    s = s.replace(a, b)
    print("[gen] %-52s x%d" % (a[:50], n))
io.open(gen, "w", encoding="utf-8").write(s)

t = io.open(tex, encoding="utf-8").read()
for a, b in [("ENchP526ub", "ENchAltUb"), ("ENchP526", "ENchAlt"),
             ("ENq3", "ENq"),
             ("ENchObsN1", "ENchObsNA"), ("ENchObsN2", "ENchObsNB"),
             ("ENchObsN3", "ENchObsNC"), ("ENchObsN4", "ENchObsND"),
             ("ENchAltN1", "ENchAltNA"), ("ENchAltN2", "ENchAltNB"),
             ("ENchAltN3", "ENchAltNC"), ("ENchAltN4", "ENchAltND"),
             ("ENchAltUbN1", "ENchAltUbNA"), ("ENchAltUbN2", "ENchAltUbNB"),
             ("ENchAltUbN3", "ENchAltUbNC"), ("ENchAltUbN4", "ENchAltUbND"),
             ("ENcfBaseD0", "ENcfBaseDefA"), ("ENcfBaseD1", "ENcfBaseDefB"),
             ("ENcfAirD0", "ENcfAirDefA"), ("ENcfAirD1", "ENcfAirDefB"),
             ("ENq4AK2RelayNeed", "ENqfourAKtwoRelayNeed"),
             ("ENq4BK2RelayNeed", "ENqfourBKtwoRelayNeed"),
             ("ENq4AK3RelayNeed", "ENqfourAKthreeRelayNeed"),
             ("ENq4BK3RelayNeed", "ENqfourBKthreeRelayNeed"),
             ("ENq4AK2RelayGap", "ENqfourAKtwoRelayGap"),
             ("ENq4BK2RelayGap", "ENqfourBKtwoRelayGap"),
             ("ENq4AK3RelayGap", "ENqfourAKthreeRelayGap"),
             ("ENq4BK3RelayGap", "ENqfourBKthreeRelayGap"),
             ("ENq4AK2Cross", "ENqfourAKtwoCross"),
             ("ENq4BK2Cross", "ENqfourBKtwoCross"),
             ("ENq4AK3Cross", "ENqfourAKthreeCross"),
             ("ENq4BK3Cross", "ENqfourBKthreeCross")]:
    if a in t:
        t = t.replace(a, b)
io.open(tex, "w", encoding="utf-8").write(t)

# 生成器里的 Q4 宏名也去数字
s = io.open(gen, encoding="utf-8").read()
s = s.replace('"ENq4%sK%sRelayNeed" % (tag, K)', '"ENqfour%sK%sRelayNeed" % (tag, "two" if K == "2" else "three")')
s = s.replace('"ENq4%sK%sRelayGap" % (tag, K)', '"ENqfour%sK%sRelayGap" % (tag, "two" if K == "2" else "three")')
s = s.replace('"ENq4%sK%sCross" % (tag, K)', '"ENqfour%sK%sCross" % (tag, "two" if K == "2" else "three")')
io.open(gen, "w", encoding="utf-8").write(s)
print("已同步 tex 与生成器")
