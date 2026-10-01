# -*- coding: utf-8 -*-
"""_fix_dp_sig.py —— 去掉 Wmax 截断，新增 exact 模式参数。"""
p = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\q3dpN.py"
s = open(p, encoding="utf-8").read()
old = ('def solve(ph, N=2, grid=10.0, topk=12, keep_slack=3, max_states=40000, inst=None, verbose=True,\n'
       '          per_key=2, Wmax_s=1300.0, max_hover_s=None, mode="base"):')
new = ('def solve(ph, N=2, grid=10.0, topk=12, keep_slack=3, max_states=40000, inst=None, verbose=True,\n'
       '          per_key=2, Wmax_s=None, max_hover_s=None, mode="base", exact=False):')
if old not in s:
    print("MISS signature")
else:
    s = s.replace(old, new)
    print("[OK] signature")
old2 = "    Wmax = max(1, int(round(Wmax_s / grid)))\n"
if old2 in s:
    s = s.replace(old2, "    # Wmax_s 已废弃：黑障窗口按逐点对精确秒数计算，不做任何截断\n")
    print("[OK] Wmax removed")
open(p, "w", encoding="utf-8").write(s)
print("done")
