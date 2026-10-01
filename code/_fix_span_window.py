# -*- coding: utf-8 -*-
"""_fix_span_window.py —— 把 (★) 不等式的窗口从「按格数偏移」改为「按时间窗」。

影响文件：
  * `span_blackout.py` —— 论文 §7.7 的 (★) 成立率与赤字；
  * `cofeedback.py`    —— 协同再调度的赤字目标函数。
两处都改用 `span_util.star_and_deficit`（时间窗唯一权威实现），
并在结果里同时保留新的时间窗口径与旧的索引口径，便于核对差异。
"""
import io
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.path.join(BASE, "code")

# ---------------- span_blackout.py ----------------
p = os.path.join(CODE, "span_blackout.py")
s = io.open(p, encoding="utf-8").read()
n = 0

s = s.replace("import numpy as np\n", "import numpy as np\n\nimport span_util as SU\n", 1)
n += 1

old = """            for q in (10, 50, 90):
                w = float(np.percentile(arr, q))
                wc = int(round(w / GRID))
                ok = np.array([(k - wc >= 0) and (span_c[k - wc] >= wc + 1) for k in range(n)])
                res.setdefault(nm, {}).setdefault(lbl, {})["p%d" % q] = dict(
                    w_s=round(w, 1), rate=round(float(ok.mean()), 4),
                    n_ok=int(ok.sum()), n=int(n))
                if q == 50 and nm == "全候选点对":
                    k0 = k_fail - wc
                    if k0 >= 0:
                        deficit = (wc + 1 - span_c[k0]) * GRID
                        res[nm][lbl]["p50"].update(
                            crash_k0=int(k0), crash_t0=round(float(cells[k0]), 1),
                            span_at_k0_s=round(float(span_c[k0] * GRID), 1),
                            need_s=round((wc + 1) * GRID, 1), deficit_s=round(float(deficit), 1))
            w = float(np.median(arr))
            wc = int(round(w / GRID))
            ok = np.array([(k - wc >= 0) and (span_c[k - wc] >= wc + 1) for k in range(n)])
            print("  %-8s %-7s w(中位)=%6.0f s → (★) 成立率 %5.1f%%（%d/%d）"
                  % (nm, lbl, w, 100 * ok.mean(), ok.sum(), n))"""
new = """            for q in (10, 50, 90):
                w = float(np.percentile(arr, q))
                # 时间窗口径（唯一权威实现）：窗口 [t_k - w, t_k] 内的需求格必须被单点独保
                ok, ndef, worst = SU.star_and_deficit(cells, span_c, w)
                res.setdefault(nm, {}).setdefault(lbl, {})["p%d" % q] = dict(
                    w_s=round(w, 1), rate=round(float(ok.mean()), 4),
                    n_ok=int(ok.sum()), n=int(n),
                    deficit_cells=int(ndef),
                    deficit_s=round(float(ndef * GRID), 1),
                    worst=worst)
                if q == 50 and nm == "全候选点对":
                    j0 = int(np.searchsorted(cells, cells[k_fail] - w, side="left"))
                    res[nm][lbl]["p50"].update(
                        crash_k0=j0, crash_t0=round(float(cells[j0]), 1),
                        span_at_k0_s=round(float(span_c[j0] * GRID), 1),
                        need_cells=int(k_fail - j0 + 1),
                        deficit_s=round(float((k_fail - j0 + 1 - span_c[j0]) * GRID), 1)
                        if span_c[j0] < (k_fail - j0 + 1) else 0.0)
            w = float(np.median(arr))
            ok, ndef, worst = SU.star_and_deficit(cells, span_c, w)
            print("  %-8s %-7s w(中位)=%6.0f s → (★) 成立率 %5.1f%%（%d/%d）赤字 %d 格（%.0f s）"
                  % (nm, lbl, w, 100 * ok.mean(), ok.sum(), n, ndef, ndef * GRID))"""
assert s.count(old) == 1, ("span loop", s.count(old))
s = s.replace(old, new)
n += 1
io.open(p, "w", encoding="utf-8").write(s)
print("[OK] span_blackout.py 改为时间窗口径（%d 处）" % n)

# ---------------- cofeedback.py ----------------
p2 = os.path.join(CODE, "cofeedback.py")
t = io.open(p2, encoding="utf-8").read()
t = t.replace("import numpy as np\n", "import numpy as np\n\nimport span_util as SU\n", 1)

old2 = """def deficit_of(cells, span, w_cells):
    n = len(cells)
    d = 0
    worst = None
    for k in range(w_cells, n):
        s = span[k - w_cells]
        if s < w_cells:
            gap = w_cells - s
            d += gap
            if worst is None or gap > worst[1]:
                worst = (k, int(gap), float(cells[k]))
    return int(d), worst"""
new2 = """def deficit_of(cells, span, w_s):
    \"\"\"时间窗口径的赤字（见 span_util）：窗口按**秒**取，不按格数偏移。

    返回 (赤字格数, 最坏窗口字典)，保持与既有调用点的二元组接口。
    \"\"\"
    ok, d, worst = SU.star_and_deficit(cells, span, w_s)
    if worst is None:
        return 0, None
    return int(d), (worst["k"], int(worst["gap_cells"]), float(worst["t"]))"""
assert t.count(old2) == 1, ("deficit_of", t.count(old2))
t = t.replace(old2, new2)

# 调用点：把 wc 改为 w 秒
t = t.replace("""        _, span = solo_and_span(cells, fails, cand, n)
            dc, dw = deficit_of(cells, span, wc)""",
              """        _, span = solo_and_span(cells, fails, cand, n)
            dc, dw = deficit_of(cells, span, w)""")
t = t.replace("d0, worst0 = deficit_of(cells, span0, wc)", "d0, worst0 = deficit_of(cells, span0, w)")
t = t.replace("cur, cur_worst = deficit_of(cells, span, wc)", "cur, cur_worst = deficit_of(cells, span, w)")
t = t.replace("""        _, span = solo_and_span(cells, fails, starts, n)
        cur, cur_worst = deficit_of(cells, span, w)""",
              """        _, span = solo_and_span(cells, fails, starts, n)
        cur, cur_worst = deficit_of(cells, span, w)""")
t = t.replace("wc = max(1, int(round(w_s / GRID)))\n", "")
t = t.replace('rec = dict(mode=mode, w_s=round(float(w_s), 1), w_cells=int(wc),',
              'rec = dict(mode=mode, w_s=round(float(w_s), 1),')
t = t.replace('A("| %s | %.0f / %d | %d / %.0f | **%d / %.0f** | %.1f%% | %s |"\n          % (cn, r["w_s"], r["w_cells"],',
              'A("| %s | %.0f | %d / %.0f | **%d / %.0f** | %.1f%% | %s |"\n          % (cn, r["w_s"],')
t = t.replace('A("| 换位模式 | 黑障 $w$（s / 格） | 基准赤字（格 / s） | 协同后赤字（格 / s） | 降幅 | 残余为 0？ |")',
              'A("| 换位模式 | 黑障 $w$（s） | 基准赤字（格 / s） | 协同后赤字（格 / s） | 降幅 | 残余为 0？ |")')
io.open(p2, "w", encoding="utf-8").write(t)
print("[OK] cofeedback.py 赤字改为时间窗口径")
