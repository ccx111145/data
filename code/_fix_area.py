# -*- coding: utf-8 -*-
"""_fix_area.py —— 服务区编号宏漏掉 "S" 前缀（渲染成 008 而非 S008）。"""
p = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\make_numbers.py"
s = open(p, encoding="utf-8").read()
pairs = [
    ('P("QoneMinPayCArea", str(limC.loc[i, "服务区编号"])[1:])',
     'P("QoneMinPayCArea", str(limC.loc[i, "服务区编号"]))'),
    ('P("QoneMinPayBArea", str(limB.loc[ib, "服务区编号"])[1:])',
     'P("QoneMinPayBArea", str(limB.loc[ib, "服务区编号"]))'),
    ('P("QoneLimAreaList", "、".join(str(x)[1:] for x in limC["服务区编号"]))',
     'P("QoneLimAreaList", "、".join(str(x) for x in limC["服务区编号"]))'),
]
for a, b in pairs:
    if a in s:
        s = s.replace(a, b); print("[OK]", a[:44])
    else:
        print("[MISS]", a[:44])
open(p, "w", encoding="utf-8").write(s)
print("done")
