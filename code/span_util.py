# -*- coding: utf-8 -*-
"""
span_util.py —— 「跨度—黑障不等式」(★) 的**时间窗**实现（唯一权威口径）。

为什么单独抽出来
----------------
需求时间格 `cells` 只包含"存在失联"的时刻，相邻格的平均间隔约 11 s，
**并不是 10 s 均匀栅格**。因此把黑障窗口 $w$（秒）换算成"格数"再按
`span[k - w_cells]` 取窗口是**错的**：它把窗口长度算成了 $w_{\\rm cells}\\times 11$ 秒左右。

正确做法是按**时间**取窗口：对每个格 $k$，令
$j_k=\\min\\{j:\\ t_j \\ge t_k - w\\}$（即 $[t_k-w,\\,t_k]$ 内的首个需求格），
则"在 $t_k$ 完成换位"要求另一架**单独覆盖** $j_k \\ldots k$ 这一段需求格，即

    span[j_k] >= k - j_k + 1 .

赤字（deficiency）$D=\\sum_k \\max\\bigl(0,\\,(k-j_k+1)-\\mathrm{span}[j_k]\\bigr)$，
(★) 成立率 = $\\#\\{k: \\text{上式成立}\\}/n$。

本模块被 `span_blackout.py`、`cofeedback.py`、`q3diag.py` 共用，
以保证中文稿、英文稿与协同再调度实验使用**同一套口径**。
"""
from __future__ import annotations

import numpy as np


def windows(cells, w_s):
    """返回每个格 k 的窗口左端格号 j_k（时间窗 [t_k - w_s, t_k] 内的首个需求格）。"""
    cells = np.asarray(cells, dtype=np.float64)
    return np.searchsorted(cells, cells - float(w_s), side="left").astype(np.int64)


def span_cells(mask_rows):
    """mask_rows: (n_cells, n_points) 的 bool 矩阵，True 表示该点能单独覆盖该格。

    返回 span[j] = 从第 j 格起、存在**同一个**点连续单独覆盖的最大格数。
    """
    m = np.asarray(mask_rows, dtype=bool)
    n = m.shape[0]
    span = np.zeros(n, dtype=np.int64)
    if n == 0:
        return span
    # 每个点在各格的可覆盖标记：对每个 j，最长连续 True 段
    run = np.zeros(m.shape[1], dtype=np.int64)
    for k in range(n - 1, -1, -1):
        run = np.where(m[k], run + 1, 0)
        span[k] = run.max() if m.shape[1] else 0
    return span


def star_and_deficit(cells, span, w_s):
    """返回 (ok: bool 数组, deficit_cells: int, worst: dict|None)。

    ok[k] 为真 ⟺ 在 $t_k$ 完成换位时，(★) 成立（存在单点可独保整个时间窗）。
    deficit 以**格数**计，另给出对应的最坏窗口信息。
    """
    cells = np.asarray(cells, dtype=np.float64)
    span = np.asarray(span, dtype=np.int64)
    n = len(cells)
    ok = np.zeros(n, dtype=bool)
    d = 0
    worst = None
    if n == 0:
        return ok, 0, None
    j = windows(cells, w_s)
    for k in range(n):
        jj = int(j[k])
        need = k - jj + 1
        got = int(span[jj]) if jj < n else 0
        if got >= need:
            ok[k] = True
        else:
            gap = need - got
            d += gap
            if worst is None or gap > worst["gap_cells"]:
                worst = dict(k=k, t=float(cells[k]), j=int(jj), t0=float(cells[jj]),
                             need_cells=int(need), span_cells=int(got),
                             gap_cells=int(gap),
                             gap_s=float(gap * (cells[k] - cells[jj]) / max(1, need - 1))
                             if need > 1 else 0.0)
    return ok, int(d), worst


def star_rate(cells, span, w_s):
    ok, d, worst = star_and_deficit(cells, span, w_s)
    n = max(1, len(cells))
    return float(ok.mean()), int(ok.sum()), int(len(cells)), d, worst
