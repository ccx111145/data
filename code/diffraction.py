# -*- coding: utf-8 -*-
"""
diffraction.py —— ITU-R P.526 单刃峰绕射模型（防线 3）

动机
----
国赛版把地形遮挡写成「FSPL + 固定遮挡附加损耗 $L_{\\mathrm{obs}}=10$ dB」，
这是一个**二值**模型：视线被挡就加 10 dB，否则不加。审稿人必然质疑：
真实山区里"擦着山脊飞"和"被一整座山挡住"的代价相差几十 dB，
固定常数既没有物理依据，也会系统性高估或低估失联时长。

本模块实现 ITU-R P.526 建议书的**单刃峰（single knife-edge）绕射**模型，
把遮挡损耗改成由地形剖面解析计算的 $J(\\nu)$：

    ν = h·sqrt( 2(d1+d2) / (λ·d1·d2) )                          (Fresnel 参数)
    J(ν) = 6.9 + 20·lg( sqrt((ν-0.1)^2 + 1) + ν - 0.1 )   dB,  ν > -0.78
    J(ν) = 0                                              dB,  ν ≤ -0.78

其中 h 为刃峰顶部高出两端点连线的距离（在地球曲率修正后取正值=高于视线），
d1/d2 为刃峰到两端的水平距离，λ 为波长。地球曲率凸起按有效地球半径因子
k = 4/3 修正：Δ = d1·d2 / (2·k·R)。

另外给出一个**多刃峰上界**：把所有 ν > 0 的刃峰损耗直接相加。
这是已知的保守过估计，用作 J 的不确定度上界（真实多刃峰损耗介于
"最强单刃峰"与"各刃峰之和"之间）。

对外接口
--------
``knife_edge_batch(p_fixed, pts, f_mhz, dem, step, k)`` →
    (j_single, j_upper, nu_max, n_edge, h_obs, d1_obs, d2_obs)
每个数组长度为 m（pts 行数），逐对计算。

``J_single(nu)`` → ITU-R P.526 单刃峰损耗 (dB)。

作者备注：本模块**不改动**国赛版的既有口径；`comm.Link` 通过
``channel_model`` 参数在 'observed'（原口径）与 'p526'（本模块）之间切换。
"""
from __future__ import annotations

import math

import numpy as np

import dcore as D

#: 有效地球半径因子（ITU-R P.526 建议用于对流层折射的平均值）
K_EARTH = 4.0 / 3.0
#: 光速 (m/s)
C_LIGHT = 299792458.0


def wavelength_m(f_mhz: float) -> float:
    return C_LIGHT / (f_mhz * 1e6)


def J_single(nu):
    """ITU-R P.526 单刃峰绕射损耗 (dB)。nu 可为数组。"""
    nu = np.asarray(nu, dtype=np.float64)
    out = np.zeros_like(nu)
    m = nu > -0.78
    if np.any(m):
        v = nu[m]
        out[m] = 6.9 + 20.0 * np.log10(np.sqrt((v - 0.1) ** 2 + 1.0) + v - 0.1)
    return out


def _profile(p_fixed, pts, dem, step):
    """构造 (m, n) 的地形剖面、视线高度与水平距离。"""
    pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
    m = len(pts)
    lo1, la1, al1 = float(p_fixed[0]), float(p_fixed[1]), float(p_fixed[2])
    lo2, la2, al2 = pts[:, 0], pts[:, 1], pts[:, 2]
    p1 = math.radians(la1)
    p2 = np.radians(la2)
    dp = p2 - p1
    dl = np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    dist = 2 * D.R_EARTH * np.arcsin(np.minimum(1.0, np.sqrt(a)))     # (m,)
    nmax = max(3, int(math.ceil(float(dist.max()) / step)) + 1)
    t = np.linspace(0.0, 1.0, nmax)[None, :]
    lo = lo1 + (lo2[:, None] - lo1) * t
    la = la1 + (la2[:, None] - la1) * t
    al = al1 + (al2[:, None] - al1) * t
    terr = dem.at(lo, la)
    s = dist[:, None] * t                                  # 沿路径的水平距离 (m)
    return terr, al, s, dist, t


def knife_edge_batch(p_fixed, pts, f_mhz, dem=None, step: float = 25.0,
                     k: float = K_EARTH):
    """对 (p_fixed, pts) 的每一对计算 ITU-R P.526 单刃峰绕射损耗。

    返回 (j_single, j_upper, nu_max, n_edge, h_obs, d1_obs, d2_obs)：
      * j_single —— 最强刃峰的 J(ν)（主口径）
      * j_upper  —— 所有 ν>0 刃峰的 J 之和（保守上界）
      * nu_max   —— 最大 Fresnel 参数
      * n_edge   —— ν>0 的采样点个数（"刃峰"计数，用于诊断地形复杂度）
      * h_obs/d1_obs/d2_obs —— 主导刃峰的几何量（审计用）
    """
    dem = dem or D.get_dem()
    pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
    m = len(pts)
    if m == 0:
        z = np.zeros(0)
        return z, z, z, np.zeros(0, dtype=int), z, z, z
    lam = wavelength_m(f_mhz)
    terr, al, s, dist, t = _profile(p_fixed, pts, dem, step)
    n = terr.shape[1]
    if n <= 2:
        z = np.zeros(m)
        return z, z, z, np.zeros(m, dtype=int), z, z, z
    d2 = dist[:, None] - s                                       # (m, n)
    # 地球曲率凸起：地势相对视线的抬高
    with np.errstate(divide="ignore", invalid="ignore"):
        bulge = s * d2 / (2.0 * k * D.R_EARTH)
    h = terr - al - bulge                                        # >0 表示高出视线
    interior = np.zeros(n, dtype=bool)
    interior[1:-1] = True
    # Fresnel 参数（端点处 d1 或 d2 为 0，必须排除）
    d1s = np.where(s <= 0.0, np.nan, s)
    d2s = np.where(d2 <= 0.0, np.nan, d2)
    with np.errstate(divide="ignore", invalid="ignore"):
        nu = h * np.sqrt(2.0 * (d1s + d2s) / (lam * d1s * d2s))
    nu = np.where(interior[None, :] & np.isfinite(nu), nu, -np.inf)
    idx = np.argmax(nu, axis=1)
    rows = np.arange(m)
    nu_max = nu[rows, idx]
    nu_max = np.where(np.isfinite(nu_max), nu_max, -1e9)
    h_obs = h[rows, idx]
    d1_obs = s[rows, idx]
    d2_obs = d2[rows, idx]
    j_single = J_single(nu_max)
    # 上界：所有 ν>0 的刃峰损耗相加
    nu_pos = np.where(nu > 0.0, nu, -np.inf)
    nu_pos = np.where(np.isfinite(nu_pos), nu_pos, -0.78)
    j_upper = J_single(np.maximum(nu_pos, -0.78)).sum(axis=1)
    n_edge = (nu > 0.0).sum(axis=1)
    return j_single, j_upper, nu_max, n_edge, h_obs, d1_obs, d2_obs


def blockage_ratio(p_fixed, pts, dem=None, step: float = 25.0, k: float = K_EARTH):
    """视线被地形穿过的"深度"比例（诊断用）：h>0 的采样点占比。"""
    dem = dem or D.get_dem()
    pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
    if len(pts) == 0:
        return np.zeros(0)
    terr, al, s, dist, t = _profile(p_fixed, pts, dem, step)
    d2 = dist[:, None] - s
    with np.errstate(divide="ignore", invalid="ignore"):
        bulge = s * d2 / (2.0 * k * D.R_EARTH)
    h = terr - al - bulge
    interior = np.zeros(terr.shape[1], dtype=bool)
    interior[1:-1] = True
    return (h[:, interior] > 0.0).mean(axis=1)
