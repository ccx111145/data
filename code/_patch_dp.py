# -*- coding: utf-8 -*-
"""_patch_dp.py —— 让 q3dpN.solve 在失败时返回诊断字典，成功时返回四元组。"""
p = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\q3dpN.py"
s = open(p, encoding="utf-8").read()
reps = [
    ('        return None, "首格无可行配置", pb\n', '        return None, "首格无可行配置", pb, None\n'),
    ('            return None, "回溯失败 k=%d" % k, pb\n', '            return None, "回溯失败 k=%d" % k, pb, None\n'),
    ('    return seq, dp[end], pb\n', '    return seq, dp[end], pb, None\n'),
]
for a, b in reps:
    if a not in s:
        print("MISS:", a.strip()[:50])
    s = s.replace(a, b)
open(p, "w", encoding="utf-8").write(s)
print("patched")
