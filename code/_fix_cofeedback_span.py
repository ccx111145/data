# -*- coding: utf-8 -*-
"""_fix_cofeedback_span.py —— 修正协同再调度目标函数中的**换代点**错误。

原实现先算 `solo[k]`（存在某个点在该格不出错），再取 `solo` 的最长连续段作为 span。
这等价于允许**逐格自由更换**保障点——把换位黑障又抹掉了，于是赤字恒为 0
（实测 992 格 solo 全真、span 中位 496 格），目标函数失去意义。

正确口径（与 `span_blackout.py`、`span_util.py` 统一）：span[j] 必须是**同一个点**
从第 j 格起连续可独保的最大格数。本脚本把 cofeedback 改为
  1) 由 `fails`（每个强点的失败时刻表）反推 (格 × 点) 的"可独保"矩阵 `ok_mat`；
  2) 用 `span_util.span_cells(ok_mat)` 计算 span；
  3) 用 `span_util.star_and_deficit` 计算 (★) 与赤字。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "cofeedback.py")
s = io.open(P, encoding="utf-8").read()

OLD = '''def solo_and_span(cells, fails, starts, n_cell):
    """给定开始时刻，返回 (solo_ok, span)。"""
    solo = np.zeros(n_cell, dtype=bool)
    for per in fails:
        if per is None:
            continue
        bad = np.zeros(n_cell + 2, dtype=np.int32)
        for k, t_rel in enumerate(per):
            if len(t_rel) == 0:
                continue
            t_abs = t_rel + starts[k]
            i0 = np.searchsorted(cells, t_abs, side="left")
            i1 = np.searchsorted(cells, t_abs, side="right")
            for a, b in zip(i0, i1):
                if a < n_cell:
                    bad[a] += 1
                    bad[min(b, n_cell)] -= 1
        solo |= (np.cumsum(bad)[:n_cell] == 0)
    span = np.zeros(n_cell, dtype=np.int64)
    run = 0
    for k in range(n_cell - 1, -1, -1):
        run = run + 1 if solo[k] else 0
        span[k] = run
    return solo, span'''

NEW = '''def ok_matrix(cells, fails, starts, n_cell):
    """返回 (n_cells, n_points) 的布尔矩阵：`ok[k, j]` 表示强点 j 在第 k 格
    **不产生任何失败**（即能单独保障该格的全部失联实例）。

    注意：**不能**先对点取并集再找连续段——那等于允许逐格更换保障点，
    会把换位黑障悄悄抹掉（这正是原实现的错误）。
    """
    pts = [f for f in fails if f is not None]
    m = np.zeros((n_cell, len(pts)), dtype=bool)
    for j, per in enumerate(pts):
        bad = np.zeros(n_cell + 2, dtype=np.int32)
        for k, t_rel in enumerate(per):
            if len(t_rel) == 0:
                continue
            t_abs = np.asarray(t_rel, dtype=np.float64) + float(starts[k])
            i0 = np.searchsorted(cells, t_abs, side="left")
            i1 = np.searchsorted(cells, t_abs, side="right")
            for a, b in zip(i0, i1):
                if a < n_cell:
                    bad[a] += 1
                    bad[min(b, n_cell)] -= 1
        m[:, j] = (np.cumsum(bad)[:n_cell] == 0)
    return m


def solo_and_span(cells, fails, starts, n_cell):
    """返回 (solo, span)：solo[k] = 存在点可独保该格；span[k] = **同一个点**从 k 起
    连续可独保的最大格数（由 `ok_matrix` + `span_util.span_cells` 得到）。"""
    m = ok_matrix(cells, fails, starts, n_cell)
    solo = m.any(axis=1) if m.shape[1] else np.zeros(n_cell, dtype=bool)
    span = SU.span_cells(m)
    return solo, span'''

assert s.count(OLD) == 1, ("solo_and_span", s.count(OLD))
s = s.replace(OLD, NEW)
io.open(P, "w", encoding="utf-8").write(s)
print("cofeedback.py: span 改为「同点连续」口径")
