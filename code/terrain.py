# -*- coding: utf-8 -*-
"""
terrain.py —— 多地形基准：由真实 DEM 生成**受控地形族**（SCI 实验补齐 ①）

为什么不用别的 DEM
------------------
审稿人要求「多地形算例」。手头只有本案例的 30 m DEM；直接去下载别的 DEM 会引入
**无法控制的混杂因素**（节点布局、面积、离网距离、货箱清单全都变了），
得到的是"两个不同算例"，而不是"地形对结论的影响"。

本文的做法是构造 **受控地形族**：保持节点经纬度、货箱清单、机型与全部通信参数不变，
只对高程场做**单调的垂直变换**，从而把"地形起伏强度"变成单一控制变量：

    T_α(z) = z_ref + α · (z − z_ref)          （α = 起伏缩放系数）

* α < 1 → 起伏被压平 → 接近「平原/缓丘」；
* α = 1 → 附件原始 DEM（中度山区，本案）；
* α > 1 → 起伏被放大 → 接近「深切峡谷/高山」。

为覆盖另一种地形**形态**（而非只有起伏幅度），另给出「深切峡谷」族：
在变换后的高程场上，沿一条人工河道做**V 形下切**：

    T_{α,c}(z, x) = T_α(z) − c · max(0, 1 − (d(x)/W)²) · H_cut

其中 d(x) 为到河道中心线的水平距离，W 为河谷半宽，H_cut 为下切深度。
河道取 DEM 覆盖区对角线方向的一条折线，穿过调度中心附近的作业区，
从而在运输航路上制造真实的"深谷遮挡"。

阻塞率（occlusion ratio）作为地形的**可测量代理指标**：运输航迹采样点中
直连不可用（或绕射损耗超过门限）的比例。实验即以「阻塞率」为横轴，
画中继最小台数 N* 的相变图。

用法：
    from terrain import make_dem, occlusion_ratio
    dem = make_dem(alpha=1.4, cut=0.0)     # 返回一个可替换 dcore 的 DEM 对象
    D.set_dem(dem)                          # 全局生效（之后需重建 Instance）
"""
from __future__ import annotations

import math

import numpy as np

import dcore as D

#: 河道中心线（DEM 覆盖范围内的一条折线，近似沿镇龙乡主沟谷方向）
RIVER_PTS = [(109.1500, 23.0100), (109.2000, 23.0300),
             (109.2400, 23.0450), (109.2900, 23.0700)]
#: 河谷半宽 (m) 与下切深度 (m)
RIVER_HALF_W = 900.0
RIVER_CUT = 180.0


class TerrainDEM:
    """对基础 DEM 施加受控垂直变换后的 DEM（接口与 `dcore.DEM` 一致）。"""

    def __init__(self, base: D.DEM, alpha: float = 1.0, cut: float = 0.0,
                 cut_depth: float = RIVER_CUT, half_w: float = RIVER_HALF_W,
                 river_pts=None, shift=(0, 0)):
        self.base = base
        self.alpha = float(alpha)
        self.cut = float(cut)
        self.cut_depth = float(cut_depth)
        self.half_w = float(half_w)
        self.river_pts = list(river_pts or RIVER_PTS)
        self.shift = (int(shift[0]), int(shift[1]))

        z = np.array(base.z, dtype=np.float64, copy=True)
        finite = np.isfinite(z)
        z_ref = float(np.median(z[finite]))
        z = z_ref + self.alpha * (z - z_ref)
        if self.cut > 0.0:
            # 「深切峡谷」= 沿走廊**抬升两侧谷壁**（而不是把本就低洼的河谷再挖深，
            # 那样不会新增任何遮挡）。走廊内保持原高程，走廊外抬升 c·cut_depth。
            z = z + self.cut * self.cut_depth * (1.0 - self._river_profile(base))
        if self.shift != (0, 0):
            # 地形**平移**：节点经纬度不变、地形场整体搬移 —— 这等价于"同一套任务
            # 换到另一片同样起伏的山区执行"，是真正的"不同地形实现"，
            # 而统计量（起伏、均值）保持可比。边缘按最近行/列复制，避免出现 0 高程。
            di, dj = self.shift
            z = np.roll(z, (di, dj), axis=(0, 1))
            if di > 0:
                z[:di, :] = z[di:di + 1, :]
            elif di < 0:
                z[di:, :] = z[di - 1:di, :]
            if dj > 0:
                z[:, :dj] = z[:, dj:dj + 1]
            elif dj < 0:
                z[:, dj:] = z[:, dj - 1:dj]
        self.z = z
        self.lat = base.lat
        self.lon = base.lon
        self.nodata = base.nodata
        # 供审计/绘图
        self.stats = dict(
            z_ref=round(z_ref, 2),
            z_min=round(float(np.nanmin(z)), 2),
            z_max=round(float(np.nanmax(z)), 2),
            relief=round(float(np.nanmax(z) - np.nanmin(z)), 2),
            base_relief=round(float(np.nanmax(base.z) - np.nanmin(base.z)), 2),
            wall_add_m=round(self.cut * self.cut_depth, 1),
            shift_cells=list(self.shift),
            shift_km=[round(di * 30.0 / 1000.0, 3) for di in self.shift],
        )

    # -- 河道下切掩膜 ------------------------------------------------------
    def _river_profile(self, base: D.DEM) -> np.ndarray:
        """返回 (ny, nx) 的 V 形下切深度场（0 ~ cut_depth）。

        采用局部等距圆柱投影把经纬度转成米，误差远小于 900 m 的河谷半宽。
        """
        ny, nx = base.z.shape
        lat0 = float(np.mean(base.lat))
        m_per_deg_lat = 110574.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
        lo = base.lon[None, :].repeat(ny, axis=0)
        la = base.lat[:, None].repeat(nx, axis=1)
        X = (lo - base.lon[0]) * m_per_deg_lon
        Y = (la - base.lat[0]) * m_per_deg_lat
        best = np.full((ny, nx), np.inf)
        for (lo1, la1), (lo2, la2) in zip(self.river_pts[:-1], self.river_pts[1:]):
            x1 = (lo1 - base.lon[0]) * m_per_deg_lon
            y1 = (la1 - base.lat[0]) * m_per_deg_lat
            x2 = (lo2 - base.lon[0]) * m_per_deg_lon
            y2 = (la2 - base.lat[0]) * m_per_deg_lat
            dx, dy = x2 - x1, y2 - y1
            seg2 = dx * dx + dy * dy
            if seg2 < 1e-9:
                d = np.hypot(X - x1, Y - y1)
            else:
                t = np.clip(((X - x1) * dx + (Y - y1) * dy) / seg2, 0.0, 1.0)
                d = np.hypot(X - (x1 + t * dx), Y - (y1 + t * dy))
            best = np.minimum(best, d)
        r = np.clip(best / self.half_w, 0.0, 1.0)
        return 1.0 - r * r                       # 中心 1 → 边缘 0

    # -- 与 dcore.DEM 同名的接口 ------------------------------------------
    def ij(self, lon, lat):
        return self.base.ij(lon, lat)

    def at(self, lon, lat):
        i, j, inb = self.base.ij(lon, lat)
        if np.ndim(i) == 0:
            if not bool(inb):
                return 0.0
            return float(self.z[int(i), int(j)])
        ii = np.asarray(i)
        jj = np.asarray(j)
        ib = np.asarray(inb)
        v = self.z[np.where(ib, ii, 0), np.where(ib, jj, 0)]
        return np.where(ib, v, 0.0)

    def at_checked(self, lon, lat):
        i, j, inb = self.base.ij(lon, lat)
        return float(self.z[i, j]), inb

    def line_max(self, lon1, lat1, lon2, lat2, step=25.0):
        d = D.haversine(lon1, lat1, lon2, lat2)
        n = max(2, int(math.ceil(d / step)) + 1)
        t = np.linspace(0.0, 1.0, n)
        return float(np.max(self.at(lon1 + (lon2 - lon1) * t,
                                    lat1 + (lat2 - lat1) * t)))


def align_nodes(inst, dem=None, verbose=False):
    """把实例中各节点的地面高程改为**该地形下**的 DEM 高程。

    为什么必须做这一步：附件给出的节点高程是**原始地形**下的地面海拔，
    而 `Node.op_alt`（作业高度 = 地面 + 30 m）与 `dcore.leg()` 的
    `cruise = max(沿线地形, a.elev, b.elev) + 50 m` 都会用到它。
    一旦地形被缩放/平移/抬升而节点经纬度不变，附件高程就不再到应地形，
    运输机会被规划到**地下**（实测地形平移族中离地高度低至 −51 m），
    由此产生的"失联"是纯粹的坐标不一致假象。

    本函数按 `dem.at(lon, lat)` 重设 `elev`，使地形族内部自洽。
    """
    dem = dem or D.get_dem()
    n_fix = 0
    for nid, nd in inst.nodes.items():
        g = float(dem.at(nd.lon, nd.lat))
        if abs(g - nd.elev) > 1e-9:
            object.__setattr__(nd, "elev", g)      # Node 为 frozen dataclass
            n_fix += 1
    if verbose:
        print("    节点高程按地形重对齐：%d/%d 个节点被修正" % (n_fix, len(inst.nodes)))
    return n_fix


def ground_clearance(inst, dem=None):
    """诊断：节点作业高度相对该地形地面的离地高度（负值表示"在地下"）。"""
    dem = dem or D.get_dem()
    out = []
    for nid, nd in inst.nodes.items():
        g = float(dem.at(nd.lon, nd.lat))
        out.append((nid, float(nd.op_alt) - g))
    return out


def is_identity(alpha: float = 1.0, cut: float = 0.0, shift=(0, 0)) -> bool:
    """是否为恒等变换（未改地形）。恒等时**不得**重对齐节点高程，
    否则会改动论文与提交表所用的基准算例（附件给定高程 vs 30 m DEM 最近邻存在数米差）。"""
    return abs(alpha - 1.0) < 1e-12 and abs(cut) < 1e-12 and tuple(shift) == (0, 0)


def make_dem(alpha: float = 1.0, cut: float = 0.0, base=None, shift=(0, 0)):
    """构造受控地形 DEM。

    * ``alpha`` —— 起伏缩放系数（1.0 = 附件原始 DEM）；
    * ``cut``   —— 峡谷谷壁抬升强度（0 = 无）；
    * ``shift`` —— 地形场整体平移（单位：DEM 像元，1 像元 ≈ 30 m），
                   用于生成"同一套任务、不同地形实现"的样本。
    """
    return TerrainDEM(base or D.DEM(), alpha=alpha, cut=cut, shift=shift)


def occlusion_ratio(inst, dem, samples=None, model: str = "observed"):
    """阻塞率：运输航迹采样点中直连不可用的比例（地形强度的可测量代理）。"""
    import comm as C
    import q2 as Q
    import solution_io as SIO

    link = C.Link(inst, dem=dem, channel_model=model)
    sol = SIO.load()
    tot = bad = 0
    per_sortie = []
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"])
                for a in areas for b in r["boxes"][a]}
        s = Q.Sortie(g=r["type"], areas=areas, load=load,
                     dur=float(r["end"]) - float(r["start"]),
                     E=float(r["energy"]), offs=offs)
        tr = C.sortie_track(inst, s, float(r["start"]), 10.0)
        if len(tr["t"]) == 0:
            continue
        ok, _, _ = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        tot += len(ok)
        bad += int((~ok).sum())
        per_sortie.append(float((~ok).mean()))
    return dict(ratio=(bad / tot if tot else 0.0), n_samples=int(tot),
                n_bad=int(bad),
                per_sortie_median=float(np.median(per_sortie)) if per_sortie else 0.0)
