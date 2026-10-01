# -*- coding: utf-8 -*-
"""_patch_q3.py —— 把 q3.solve 切到严格中继排程（不可行则记为中断）。"""
import io

p = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\q3.py"
s = open(p, encoding="utf-8").read()
reps = [
    ("        ss, warn = schedule_relay(inst, ph, verbose=False)\n",
     "        ss, warn, outage = schedule_relay(inst, ph, verbose=False, strict=True)\n"),
    ('            score = (0 if v["ok"] else 1, viol, short, len(ss), m["tardiness"], m["makespan"])',
     '            score = (len(outage), 0 if v["ok"] else 1, viol, short, len(ss),\n'
     '                     m["tardiness"], m["makespan"])'),
    ("            best = (score, tag, sol, pol, m, ph, ss, warn, v)",
     "            best = (score, tag, sol, pol, m, ph, ss, warn, v, outage)"),
    ("    _, tag, sol, pol, m, ph, ss, warn, v = best",
     "    _, tag, sol, pol, m, ph, ss, warn, v, outage = best"),
    ('    res = dict(ok=v["ok"], sol=sol, pol=pol, ph=ph, sorties=ss, warn=warn, verify=v,\n'
     '               scheme=tag, cover_w=cover_w)',
     '    res = dict(ok=v["ok"], sol=sol, pol=pol, ph=ph, sorties=ss, warn=warn, verify=v,\n'
     '               outage=outage, scheme=tag, cover_w=cover_w)'),
]
for a, b in reps:
    if a not in s:
        print("MISS:", a[:60])
    s = s.replace(a, b)
open(p, "w", encoding="utf-8").write(s)
print("patched")
