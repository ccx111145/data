# -*- coding: utf-8 -*-
"""
q3dp.py —— 中继部署动态规划（2 架中继、逐时刻覆盖）

状态：cell k 上两架中继各自的悬停位置 (a, b)（可为 IDLE = 停在 O01）
可行性：(a, b) 的并集必须覆盖 cell k 的全部通信需求实例
转移代价：位置变化 = 新开一个中继架次（两台同时换位被禁止——否则换位期间无人提供保障）
换位可行性：某台换位时，另一台必须能**单独**覆盖换位前后各 W 秒内的所有需求
目标：最少中继架次数，其次最少中继总能耗
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

import dcore as D
import comm as C
import relay as R

IDLE = -1


def cell_index(T, grid):
    return np.unique((np.floor(np.asarray(T) / grid) * grid).astype(np.int64))


def prepare(inst, T, P, cand, cov, meta, grid=10.0, per_cell=14):
    """
    返回 dict(cells, cell_groups, pool, cov_pool, alone, pref_not)
      cells       : 有需求的时刻（栅格化）
      cell_groups : 每个 cell 对应的实例行号
      cov_pool    : (n_inst, n_pool) 布尔覆盖矩阵
      alone       : (n_cell, n_pool) 该点能否单独覆盖整格
    """
    cells = cell_index(T, grid)
    cid = np.searchsorted(cells, (np.floor(T / grid) * grid).astype(np.int64))
    groups = [np.nonzero(cid == k)[0] for k in range(len(cells))]
    # 候选池：每格增益前若干 + 最佳单点
    pool = set()
    for g in groups:
        gains = cov[g].sum(axis=0)
        for c in np.argsort(-gains)[:per_cell]:
            pool.add(int(c))
    pool = sorted(pool)
    covp = cov[:, pool]
    alone = np.zeros((len(cells), len(pool)), dtype=bool)
    for k, g in enumerate(groups):
        alone[k] = covp[g].all(axis=0)
    pref_not = np.zeros((len(pool), len(cells) + 1), dtype=np.int32)
    for j in range(len(pool)):
        pref_not[j, 1:] = np.cumsum(~alone[:, j])
    return dict(cells=cells, cid=cid, groups=groups, pool=pool, cov_pool=covp, alone=alone,
                pref_not=pref_not, meta=meta)


def alone_covers(dat, j, k0, k1):
    """候选池第 j 个点能否在 cell 区间 [k0,k1] 内单独覆盖全部需求。"""
    k0 = max(0, k0); k1 = min(len(dat["cells"]) - 1, k1)
    if k1 < k0:
        return True
    return dat["pref_not"][j, k1 + 1] - dat["pref_not"][j, k0] == 0


def solve_dp(inst, dat, grid=10.0, W=900.0, allow_pair=True, verbose=True):
    """动态规划求最少中继架次的部署方案。返回 (seq, cost) 或 (None, 原因)。"""
    cells = dat["cells"]
    pool = dat["pool"]
    n = len(cells)
    npool = len(pool)
    Wc = max(1, int(round(W / grid)))

    # 每格的可行配置
    cfg = []
    n_single = n_pair = 0
    for k, g in enumerate(dat["groups"]):
        singles = [j for j in range(npool) if dat["alone"][k, j]]
        if singles:
            n_single += 1
            cfg.append([(j, IDLE) for j in singles[:20]] + [(IDLE, j) for j in singles[:20]])
            continue
        if not allow_pair:
            return None, "cell %d 无法被单点覆盖且未启用双点" % k
        sub = dat["cov_pool"][g]
        pairs = []
        for j1 in range(npool):
            rest = sub[~sub[:, j1]]
            if len(rest) == 0:
                continue
            need = rest.all(axis=0)
            for j2 in np.nonzero(need)[0]:
                if j2 > j1:
                    pairs.append((j1, int(j2)))
        if not pairs:
            return None, "cell %d 无可行配置" % k
        n_pair += 1
        cfg.append(pairs[:40])
    if verbose:
        print("  可行配置：单点可覆盖格 %d 个，需双点格 %d 个" % (n_single, n_pair))

    INF = float("inf")

    def cost_of(st):
        return (1 if st[0] >= 0 else 0) + (1 if st[1] >= 0 else 0)

    dp = {st: cost_of(st) for st in cfg[0]}
    parents = [dict()]                       # parents[k][state] = 前一格状态

    for k in range(1, n):
        rowmin, rowarg = {}, {}
        colmin, colarg = {}, {}
        for (a, b), v in dp.items():
            if v < rowmin.get(b, INF):
                rowmin[b], rowarg[b] = v, (a, b)
            if v < colmin.get(a, INF):
                colmin[a], colarg[a] = v, (a, b)
        cur, par = {}, {}
        for (a2, b2) in cfg[k]:
            best, bp = INF, None
            v = dp.get((a2, b2), INF)
            if v < best:
                best, bp = v, (a2, b2)
            if b2 in rowmin:                       # 只换第一台
                if b2 == IDLE or alone_covers(dat, b2, k - Wc, k + Wc):
                    x = rowmin[b2] + (1 if a2 >= 0 else 0)
                    if x < best:
                        best, bp = x, rowarg[b2]
            if a2 in colmin:                       # 只换第二台
                if a2 == IDLE or alone_covers(dat, a2, k - Wc, k + Wc):
                    x = colmin[a2] + (1 if b2 >= 0 else 0)
                    if x < best:
                        best, bp = x, colarg[a2]
            cur[(a2, b2)] = best
            par[(a2, b2)] = bp
        cur = {kk: vv for kk, vv in cur.items() if vv < INF}
        par = {kk: vv for kk, vv in par.items() if kk in cur}
        if cur:
            mn = min(cur.values())
            keep = {kk: vv for kk, vv in cur.items() if vv <= mn + 3}
            cur = keep
            par = {kk: vv for kk, vv in par.items() if kk in keep}
        dp = cur
        parents.append(par)
        if not dp:
            return None, "第 %d 格（t=%.0f s）无可行状态：换位约束过紧" % (k, cells[k])

    end = min(dp, key=lambda s: dp[s])
    seq = [None] * n
    st = end
    for k in range(n - 1, -1, -1):
        seq[k] = st
        if k == 0:
            break
        st = parents[k][st]
        if st is None:
            return None, "回溯失败于 k=%d" % k
    return seq, dp[end]


def to_deployments(seq, dat, grid):
    """把逐格位置序列合并为部署段（同一位置连续段）。"""
    cells = dat["cells"]
    pool = dat["pool"]
    meta = dat["meta"]
    segs = {0: [], 1: []}     # 中继 A / B
    for slot in (0, 1):
        cur = None
        for k, st in enumerate(seq):
            j = st[slot]
            if cur is not None and cur["j"] == j:
                cur["k1"] = k
                continue
            if cur is not None:
                segs[slot].append(cur)
            cur = dict(j=j, k0=k, k1=k)
        if cur is not None:
            segs[slot].append(cur)
    out = []
    for slot in (0, 1):
        for sg in segs[slot]:
            if sg["j"] == IDLE:
                continue
            c = pool[sg["j"]]
            lo, la, g, agl = meta[c]
            out.append(dict(slot=slot, pool_idx=sg["j"], lon=lo, lat=la, ground=g, agl=agl,
                            t0=float(cells[sg["k0"]]), t1=float(cells[sg["k1"]]),
                            k0=sg["k0"], k1=sg["k1"]))
    out.sort(key=lambda d: (d["t0"], d["slot"]))
    return out
