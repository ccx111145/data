# -*- coding: utf-8 -*-
"""
dcore.py —— 2026 中国研究生数学建模竞赛 D 题
「山区洪涝灾害下无人机运输与通信协同优化」统一物理口径核心库

四问共用本模块，保证论文中所有单位、编号、计算口径完全一致。

设计原则
--------
1. 节点高度：O01/服务区的地面海拔取附件给定值（题目："参数以附件给定值为准"）；
   巡航海拔取航段沿线 30 m DEM 最高地面高程与两端给定海拔的较大者 + 50 m。
2. 航段时间：t = h+/v_up + d/v_c + h-/v_dn （爬升/巡航/下降三阶段）。
3. 航段能耗：E = E_hor + E_up
      E_hor = d / L_g(q) * E_g^use        （由"等效航程"定义反推，见论文假设 A3）
      E_up  = (m0 + q) * g * h+ / (eta_up * 3.6e6)   [kWh]
   下降能耗效率为 0，不计下降附加能耗。
4. 返航安全余量：E_sortie <= (1 - rho_g) * E_g^use
5. 充电：两阶段等效模型，SOC<90% 段占 T_full 的 65%，90%~100% 段占 35%。
6. 通信：FSPL = 32.45 + 20lg f(MHz) + 20lg D(km)；地形遮挡附加 L_obs；
   双向链路门限取两方向较小者；接收门限 P_th = P_sens + M。
"""
from __future__ import annotations

import math
import os
import numpy as np
import pandas as pd
import scipy.io as sio
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(_CODE_DIR)                      # .../D题

#: 数据目录的候选位置（按顺序探测，取第一个真实存在的）。这样同一套程序在
#: 「工作区 code/ + 数据/」与「交付包 03_程序/ + 04_数据与模板/数据/」两种布局下
#: 都能直接运行，无需手工改路径。
_DATA_CANDIDATES = [
    os.environ.get("DTI_DATA_DIR") or "",
    os.path.join(BASE, "数据"),
    os.path.join(BASE, "04_数据与模板", "数据"),
    os.path.join(BASE, "..", "04_数据与模板", "数据"),
    os.path.join(BASE, "..", "数据"),
    os.path.join(_CODE_DIR, "数据"),
    os.path.join(BASE, "D题", "数据"),
]

_PARAM_REL = "无人机应急物资运输基础数据"


def _pick_data_dir():
    for c in _DATA_CANDIDATES:
        if c and os.path.isdir(os.path.join(c, _PARAM_REL)):
            return os.path.abspath(c)
    return os.path.join(BASE, "数据")                  # 兜底：报错信息指向约定位置


DATA = _pick_data_dir()
PARAM_DIR = os.path.join(DATA, _PARAM_REL)
GEO_DIR = os.path.join(DATA, "镇龙乡地理空间数据", "镇龙乡及周边地理数据")
DEM_MAT = os.path.join(GEO_DIR, "数字高程模型数据（DEM）", "镇龙乡及周边30米DEM.mat")

#: 输出目录（与 BASE 同级；不存在时自动创建，保证在全新目录里也能直接跑通）
RESULTS = os.path.join(BASE, "results")
FIGS = os.path.join(BASE, "figs")
for _d in (RESULTS, FIGS):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass

G = 9.80665          # m/s^2
J_PER_KWH = 3.6e6
R_EARTH = 6371008.8  # m


# ---------------------------------------------------------------------------
# 外部可执行文件解析
#
# 原先各脚本把 TeX 二进制硬编码成 H:\texlive\2024\bin\windows\xelatex.exe，
# 别人 clone 本仓库后必然跑不通。这里统一成"环境变量 → PATH → 本机常见位置"
# 三级回退，仓库里不再依赖任何人的绝对路径。
# ---------------------------------------------------------------------------
import shutil as _shutil                                            # noqa: E402

#: 允许用环境变量覆盖，便于指定非默认 TeX 发行版
_BIN_ENV = {
    "xelatex": "DTS_XELATEX",
    "pdflatex": "DTS_PDFLATEX",
    "bibtex": "DTS_BIBTEX",
    "soffice": "DTS_SOFFICE",
    "pandoc": "DTS_PANDOC",
}

#: 本机常见安装位置（仅作最后回退，找不到也无所谓）
_BIN_FALLBACK = {
    "xelatex": [r"H:\texlive\2024\bin\windows\xelatex.exe",
                r"C:\texlive\2024\bin\windows\xelatex.exe"],
    "pdflatex": [r"H:\texlive\2024\bin\windows\pdflatex.exe",
                 r"C:\texlive\2024\bin\windows\pdflatex.exe"],
    "bibtex": [r"H:\texlive\2024\bin\windows\bibtex.exe",
               r"C:\texlive\2024\bin\windows\bibtex.exe"],
    "soffice": [r"C:\Program Files\LibreOffice\program\soffice.exe"],
    "pandoc": [],
}


def find_bin(name: str) -> str:
    """定位外部可执行文件；找不到时抛错并给出可操作的提示。

    顺序：环境变量 → PATH → 本机常见位置。返回绝对路径或可直接调用的名字。
    """
    env = _BIN_ENV.get(name)
    if env:
        v = os.environ.get(env)
        if v and os.path.exists(v):
            return v
    p = _shutil.which(name)
    if p:
        return p
    for cand in _BIN_FALLBACK.get(name, []):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(
        "%s 未找到。请把它加入 PATH，或用环境变量 %s 指定完整路径。"
        % (name, _BIN_ENV.get(name, "DTS_" + name.upper())))


def find_bin_soft(name: str):
    """同 find_bin，但找不到时返回 None 而不抛错（用于可选工具）。"""
    try:
        return find_bin(name)
    except FileNotFoundError:
        return None


# ----------------------------------------------------------------------------
# DEM
# ----------------------------------------------------------------------------
_DEM = None


class DEM:
    """Copernicus GLO-30 DSM（EPSG:4326，1/3600°）。行=自北向南，列=自西向东。"""

    def __init__(self, path: str = DEM_MAT):
        m = sio.loadmat(path)
        self.z = np.asarray(m["dem"], dtype=np.float64)
        self.lat = np.asarray(m["latitude"], dtype=np.float64).ravel()   # 递减
        self.lon = np.asarray(m["longitude"], dtype=np.float64).ravel()  # 递增
        self.nodata = float(np.asarray(m["nodata"]).ravel()[0])
        self.tr = np.asarray(m["transform"], dtype=np.float64).ravel()
        self.dlat = self.lat[1] - self.lat[0]   # < 0
        self.dlon = self.lon[1] - self.lon[0]   # > 0
        self.ny, self.nx = self.z.shape
        self._zfill = np.where(self.z <= self.nodata + 1, np.nan, self.z)

    # -- 索引 --------------------------------------------------------------
    def ij(self, lon, lat):
        scalar = not (np.ndim(lon) or np.ndim(lat))
        lo = np.atleast_1d(np.asarray(lon, dtype=np.float64))
        la = np.atleast_1d(np.asarray(lat, dtype=np.float64))
        lo, la = np.broadcast_arrays(lo, la)
        j = np.rint((lo - self.lon[0]) / self.dlon).astype(np.int64)
        i = np.rint((la - self.lat[0]) / self.dlat).astype(np.int64)
        inb = (i >= 0) & (i < self.ny) & (j >= 0) & (j < self.nx)
        i = np.clip(i, 0, self.ny - 1)
        j = np.clip(j, 0, self.nx - 1)
        if scalar:
            return int(i[0]), int(j[0]), bool(inb[0])
        return i, j, inb

    def at(self, lon, lat):
        """最近邻取高程；越界返回 0。"""
        i, j, inb = self.ij(lon, lat)
        v = self.z[i, j]
        v = np.where(inb, v, 0.0)
        return float(v) if np.ndim(v) == 0 else v

    def at_checked(self, lon, lat):
        i, j, inb = self.ij(lon, lat)
        return self.z[i, j], inb

    # -- 沿线最高地面 ------------------------------------------------------
    def line_max(self, lon1, lat1, lon2, lat2, step=25.0):
        """直线上重采样（步长 step 米）× 取沿途 30 m DEM 最高地面高程。"""
        d = haversine(lon1, lat1, lon2, lat2)
        n = max(2, int(math.ceil(d / step)) + 1)
        t = np.linspace(0.0, 1.0, n)
        lo = lon1 + (lon2 - lon1) * t
        la = lat1 + (lat2 - lat1) * t
        return float(np.max(self.at(lo, la)))


def get_dem() -> DEM:
    global _DEM
    if _DEM is None:
        _DEM = DEM()
    return _DEM


def set_dem(dem) -> None:
    """注入自定义 DEM（用于多地形基准实验，见 code/terrain.py）。

    传 None 恢复为附件原始 DEM。副作用：DEM 代次 +1 并清空航段缓存，
    使后续 `leg()` 按新地形重算巡航高度。调用后应重建 ``q2.Instance()``
    并清空 `q2._COVER[0]`（覆盖模型缓存）。
    """
    global _DEM
    _DEM = dem
    _DEM_GEN[0] += 1
    _LEG_CACHE.clear()
    _COVER_CACHE.clear()


#: 供 `q2._cover` 之类模块级缓存在换地形后失效（由 terrain.py 显式调用）
_COVER_CACHE: dict = {}


# ----------------------------------------------------------------------------
# 几何
# ----------------------------------------------------------------------------
def haversine(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


# ----------------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Node:
    nid: str
    name: str
    lon: float
    lat: float
    elev: float          # 附件给定地面海拔 (m)
    kind: str            # 'O' 调度中心 / 'S' 服务区
    pop: int = 0

    @property
    def op_alt(self) -> float:
        """作业高度：O01 取地面海拔；服务区取地面海拔 + 30 m。"""
        return self.elev if self.kind == "O" else self.elev + 30.0


@dataclass(frozen=True)
class DroneType:
    gid: str
    name: str
    m_empty: float       # 含电池空载总质量 kg
    q_max: float         # 最大载货质量 kg
    v_cap: float         # 可用装载体积 m^3
    v_cruise: float      # 计划巡航速度 m/s
    range_empty: float   # 空载标准航程 m
    range_full: float    # 满载标准航程 m
    e_use: float         # 单组电池可用能量 kWh
    rho: float           # 返航电量下限（= 返航安全余量比例）
    t_prep: float        # 工位固定准备时间 s
    t_load_box: float    # 每箱装载时间 s
    t_hand_base: float   # 接收点基础交接时间 s
    t_hand_box: float    # 每箱增加交接时间 s
    v_up: float
    v_dn: float
    eta_up: float
    eta_dn: float

    def equiv_range(self, q):
        q = np.clip(q, 0.0, self.q_max)
        return self.range_empty - (self.range_empty - self.range_full) * (q / self.q_max) ** 1.5


@dataclass(frozen=True)
class Box:
    bid: str
    sid: str
    kind: str
    mass: float
    vol: float
    first_batch: bool
    first_deadline: float      # s, inf if not first batch
    expect_time: float         # s
    priority: int


@dataclass(frozen=True)
class RelayType:
    gid: str
    name: str
    m_empty: float
    m_comm: float
    mtow: float
    v_cruise: float
    p_cruise: float      # kW
    e_use: float         # kWh
    rho: float
    t_prep: float
    t_link: float
    t_turn: float
    v_up: float
    v_dn: float
    eta_up: float
    eta_dn: float
    p_hover: float       # kW
    p_comm: float        # kW
    h_max_agl: float     # m


@dataclass(frozen=True)
class CommParams:
    f_mhz: float
    l_sys: float
    l_obs: float
    p_sens: float
    margin: float
    # (Pt dBm, Gt dBi, Gr dBi)
    transport: Tuple[float, float, float]
    relay_access: Tuple[float, float, float]
    relay_backhaul: Tuple[float, float, float]
    gateway: Tuple[float, float, float]
    gw_ant_h: float
    #: 信道模型：'observed' = 附件给定口径（FSPL + 固定遮挡附加损耗，二值）；
    #: 'p526' = ITU-R P.526 单刃峰绕射（由地形剖面解析计算绕射损耗）；
    #: 'p526ub' = 同上前提但取多刃峰保守上界。见 code/diffraction.py。
    channel_model: str = "observed"
    #: 地球有效半径因子（仅 'p526*' 使用）
    k_earth: float = 4.0 / 3.0
    #: 地形剖面重采样步长 (m)
    prof_step: float = 25.0


# ----------------------------------------------------------------------------
# 装载
# ----------------------------------------------------------------------------
def load_all():
    dem = get_dem()

    # --- 调度中心与服务区 ---
    xl = os.path.join(PARAM_DIR, "调度中心与服务区.xlsx")
    df = pd.read_excel(xl, sheet_name="数据", header=None)
    nodes: Dict[str, Node] = {}
    # 调度中心块：第 3 行数据（0-based 2）
    for _, r in df.iterrows():
        v = r.tolist()
        if v[0] == "O01":
            nodes["O01"] = Node("O01", str(v[1]), float(v[2]), float(v[3]), float(v[4]), "O")
        elif isinstance(v[0], str) and v[0].startswith("S") and len(v[0]) == 4:
            nodes[v[0]] = Node(v[0], str(v[1]), float(v[2]), float(v[3]), float(v[4]), "S",
                               int(v[5]) if v[5] == v[5] else 0)
    SIDS = [f"S{i:03d}" for i in range(1, 16)]

    # --- 运输无人机（按块解析，避免"共享电池库存"块中同样以 A/B/C 开头的行覆盖机型参数） ---
    xl = os.path.join(PARAM_DIR, "运输无人机数据.xlsx")
    rows = [r.tolist() for _, r in pd.read_excel(xl, sheet_name="数据", header=None).iterrows()]

    def block(rows, first_cell, nth=0):
        """返回以 first_cell 开头的那一行之后、到下一个空行为止的连续数据行。nth 指定第几次出现。"""
        seen = 0
        for k, v in enumerate(rows):
            if v[0] == first_cell:
                if seen < nth:
                    seen += 1
                    continue
                out = []
                for w in rows[k + 1:]:
                    if w[0] is None or (isinstance(w[0], float) and w[0] != w[0]):
                        break
                    out.append(w)
                return out
        raise KeyError(first_cell)

    ttypes: Dict[str, DroneType] = {}
    for v in block(rows, "机型编号")[:3]:
        ttypes[v[0]] = DroneType(
            gid=v[0], name=str(v[1]), m_empty=float(v[2]), q_max=float(v[3]),
            v_cap=float(v[4]), v_cruise=float(v[5]), range_empty=float(v[6]),
            range_full=float(v[7]), e_use=float(v[8]), rho=float(v[9]) / 100.0,
            t_prep=float(v[10]), t_load_box=float(v[11]), t_hand_base=float(v[12]),
            t_hand_box=float(v[13]), v_up=float(v[14]), v_dn=float(v[15]),
            eta_up=float(v[16]), eta_dn=float(v[17]))
    fleet: Dict[str, List[str]] = {"A": [], "B": [], "C": []}
    for v in block(rows, "无人机编号"):
        fleet[str(v[1])].append(v[0])
    batt = {v[0]: (int(v[1]), float(v[2])) for v in block(rows, "机型编号", nth=1)}

    # --- 中继无人机 ---
    xl = os.path.join(PARAM_DIR, "中继无人机数据.xlsx")
    rrows = [r.tolist() for _, r in pd.read_excel(xl, sheet_name="数据", header=None).iterrows()]
    rtype = None
    for v in block(rrows, "机型编号"):
        rtype = RelayType(gid=v[0], name=str(v[1]), m_empty=float(v[2]), m_comm=float(v[3]),
                          mtow=float(v[4]), v_cruise=float(v[5]), p_cruise=float(v[6]),
                          e_use=float(v[7]), rho=float(v[8]) / 100.0, t_prep=float(v[9]),
                          t_link=float(v[10]), t_turn=float(v[11]), v_up=float(v[12]),
                          v_dn=float(v[13]), eta_up=float(v[14]), eta_dn=float(v[15]),
                          p_hover=float(v[16]), p_comm=float(v[17]), h_max_agl=float(v[18]))
    rfleet = [v[0] for v in block(rrows, "中继无人机编号")]
    rb = [v for v in block(rrows, "机型编号", nth=1) if isinstance(v[1], (int, float)) and v[1] == v[1]]
    rbatt = (int(rb[0][1]), float(rb[0][2])) if rb else (0, 0.0)

    # --- 货箱 ---
    xl = os.path.join(PARAM_DIR, "物资需求与配送时限.xlsx")
    bx = pd.read_excel(xl, sheet_name="逐箱货箱清单")
    boxes: List[Box] = []
    for _, r in bx.iterrows():
        if not isinstance(r["货箱编号"], str):
            continue
        fb = str(r["是否首批保障"]).strip() == "是"
        fd = float(r["首批截止时间（s）"]) if fb and r["首批截止时间（s）"] == r["首批截止时间（s）"] else math.inf
        boxes.append(Box(bid=r["货箱编号"], sid=r["服务区编号"], kind=r["物资类型"],
                         mass=float(r["单箱质量（kg）"]), vol=float(r["单箱体积（m³）"]),
                         first_batch=fb, first_deadline=fd,
                         expect_time=float(r["期望送达时间（s）"]),
                         priority=int(r["应急优先系数"])))

    # --- 通信参数 ---
    xl = os.path.join(PARAM_DIR, "通信链路参数.xlsx")
    cz = pd.read_excel(xl, sheet_name="数据", header=None)
    val = {}
    for _, r in cz.iterrows():
        v = r.tolist()
        if isinstance(v[3], str) and v[3] != "符号" and v[4] == v[4]:
            key = (str(v[0]), str(v[1]))
            val[key] = float(v[4])
    comm = CommParams(
        f_mhz=val[("传播参数", "载波频率（MHz）")],
        l_sys=val[("传播参数", "系统损耗（dB)")] if ("传播参数", "系统损耗（dB)") in val else val[("传播参数", "系统损耗（dB）")],
        l_obs=val[("传播参数", "地形遮挡附加损耗（dB）")],
        p_sens=val[("接收参数", "接收灵敏度（dBm）")],
        margin=val[("接收参数", "衰落裕量（dB）")],
        transport=(val[("运输无人机", "发射功率（dBm）")], val[("运输无人机", "天线增益（dBi）")],
                   val[("运输无人机", "天线增益（dBi）")]),
        relay_access=(val[("中继接入端", "发射功率（dBm）")], val[("中继接入端", "天线增益（dBi）")],
                      val[("中继接入端", "天线增益（dBi）")]),
        relay_backhaul=(val[("中继回传端", "发射功率（dBm）")], val[("中继回传端", "天线增益（dBi）")],
                        val[("中继回传端", "天线增益（dBi）")]),
        gateway=(val[("固定网关 G01", "发射功率（dBm）")], val[("固定网关 G01", "天线增益（dBi）")],
                 val[("固定网关 G01", "天线增益（dBi）")]),
        gw_ant_h=val[("固定网关 G01", "天线离地高度（m）")],
        channel_model=os.environ.get("DTI_CHANNEL", "observed"),
        k_earth=float(os.environ.get("DTI_KEARTH", 4.0 / 3.0)),
        prof_step=float(os.environ.get("DTI_PROFSTEP", 25.0)),
    )

    return dict(dem=dem, nodes=nodes, SIDS=SIDS, ttypes=ttypes, fleet=fleet, batt=batt,
                rtype=rtype, rfleet=rfleet, rbatt=rbatt, boxes=boxes, comm=comm)


# ----------------------------------------------------------------------------
# 航段物理量
# ----------------------------------------------------------------------------
@dataclass
class Leg:
    src: str
    dst: str
    dist: float          # 水平巡航距离 m
    h_max_ground: float  # 沿线最高地面高程 m
    cruise_alt: float    # 计划巡航海拔 m
    h_up: float
    h_dn: float
    t_flight: float
    e_hor: float
    e_up: float

    @property
    def e_total(self):
        return self.e_hor + self.e_up


_LEG_CACHE: Dict[Tuple[str, str, str, float], Leg] = {}
#: DEM 代次：`set_dem` 每次调用 +1。航段缓存必须把它纳入键，
#: 否则换地形后仍会命中上一个地形的巡航高度（多地形基准实验的关键正确性条件）。
_DEM_GEN = [0]


def dem_generation() -> int:
    return int(_DEM_GEN[0])


def leg(nodes: Dict[str, Node], dt: DroneType, src: str, dst: str, q: float,
        dem: DEM = None) -> Leg:
    """计算 src->dst 航段（载荷 q kg）的时间与能耗。"""
    key = (dt.gid, src, dst, round(q, 4), int(_DEM_GEN[0]))
    hit = _LEG_CACHE.get(key)
    if hit is not None:
        return hit
    dem = dem or get_dem()
    a, b = nodes[src], nodes[dst]
    d = haversine(a.lon, a.lat, b.lon, b.lat)
    gmax = dem.line_max(a.lon, a.lat, b.lon, b.lat)
    cruise = max(gmax, a.elev, b.elev) + 50.0
    h_up = cruise - a.op_alt
    h_dn = cruise - b.op_alt
    t = h_up / dt.v_up + d / dt.v_cruise + h_dn / dt.v_dn
    e_hor = d / float(dt.equiv_range(q)) * dt.e_use
    e_up = (dt.m_empty + q) * G * h_up / (dt.eta_up * J_PER_KWH)
    L = Leg(src, dst, d, gmax, cruise, h_up, h_dn, t, e_hor, e_up)
    _LEG_CACHE[key] = L
    return L


def sortie_energy(nodes, dt, stops: Sequence[str], loads: Sequence[float]):
    """
    stops = [O01, S_a, S_b, ..., O01]，loads[i] = 到达 stops[i] 时的剩余载荷（kg）。
    返回 (总能耗 kWh, 逐航段 Leg 列表)。
    """
    legs = []
    tot = 0.0
    for i in range(len(stops) - 1):
        L = leg(nodes, dt, stops[i], stops[i + 1], loads[i])
        legs.append(L)
        tot += L.e_total
    return tot, legs


def sortie_timeline(nodes, dt, stops: Sequence[str], loads: Sequence[float], n_boxes_at: Sequence[int]):
    """
    返回 (总时长 s, 逐站交付完成时刻相对架次开始的偏移列表, 航段列表)。
    n_boxes_at[i] = 在 stops[i] 卸下的箱数。
    """
    totE, legs = sortie_energy(nodes, dt, stops, loads)
    t = dt.t_prep + dt.t_load_box * sum(n_boxes_at)          # 装载阶段
    offs = [None] * len(stops)
    for i in range(1, len(stops) - 1):
        t += legs[i - 1].t_flight
        t += dt.t_hand_base + dt.t_hand_box * n_boxes_at[i]
        offs[i] = t
    t += legs[-1].t_flight                                   # 返航
    return t, offs, legs, totE


# ----------------------------------------------------------------------------
# 充电
# ----------------------------------------------------------------------------
def charge_time(soc, t_full):
    """两阶段等效充电模型：返回从 SOC=soc 充至 100% 所需时间 (s)。"""
    soc = np.clip(np.asarray(soc, dtype=np.float64), 0.0, 1.0)
    fast = t_full * (0.65 * (0.90 - soc) / 0.90 + 0.35)
    slow = t_full * 0.35 * (1.0 - soc) / 0.10
    r = np.where(soc < 0.90, fast, slow)
    r = np.where(soc >= 1.0, 0.0, r)
    return r if r.ndim else float(r)


# ----------------------------------------------------------------------------
# 通信
# ----------------------------------------------------------------------------
def fspl(f_mhz, d_m):
    """自由空间传播损耗 (dB)，d 以米计。"""
    d_km = np.maximum(np.asarray(d_m, dtype=np.float64) / 1000.0, 1e-9)
    return 32.45 + 20.0 * np.log10(f_mhz) + 20.0 * np.log10(d_km)


def lmax(tx, rx, cp: CommParams):
    """方向 tx->rx 的最大允许总传播损耗 (dB)。tx/rx = (Pt, Gt, Gr)。"""
    pth = cp.p_sens + cp.margin
    return tx[0] + tx[1] + rx[2] - cp.l_sys - pth


def lmax_bidir(a, b, cp: CommParams):
    return min(lmax(a, b, cp), lmax(b, a, cp))


def los_blocked(lon1, lat1, alt1, lon2, lat2, alt2, dem=None, step=25.0, tol=1e-9):
    """两端点三维视线是否被 30 m DEM 地形遮挡（端点本身不计）。"""
    dem = dem or get_dem()
    d = haversine(lon1, lat1, lon2, lat2)
    n = max(3, int(math.ceil(d / step)) + 1)
    t = np.linspace(0.0, 1.0, n)
    lo = lon1 + (lon2 - lon1) * t
    la = lat1 + (lat2 - lat1) * t
    al = alt1 + (alt2 - alt1) * t
    terr = dem.at(lo, la)
    return bool(np.any(al[1:-1] < terr[1:-1] - tol))


def los_blocked_batch(p_fixed, pts, dem=None, step=25.0):
    """一个固定端点 p_fixed=(lon,lat,alt) 对一批端点 pts[(m,3)] 的视线遮挡（向量化）。
    返回 bool 数组 (m,)。"""
    dem = dem or get_dem()
    pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
    m = len(pts)
    if m == 0:
        return np.zeros(0, dtype=bool)
    lo1, la1, al1 = p_fixed
    lo2 = pts[:, 0]
    la2 = pts[:, 1]
    al2 = pts[:, 2]
    # 各对水平距离
    p1 = math.radians(la1)
    p2 = np.radians(la2)
    dp = p2 - p1
    dl = np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    dist = 2 * R_EARTH * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    nmax = max(3, int(math.ceil(float(dist.max()) / step)) + 1)
    t = np.linspace(0.0, 1.0, nmax)[None, :]                 # (1, nmax)
    lo = lo1 + (lo2[:, None] - lo1) * t                      # (m, nmax)
    la = la1 + (la2[:, None] - la1) * t
    al = al1 + (al2[:, None] - al1) * t
    terr = dem.at(lo, la)
    blocked = np.any(al[:, 1:-1] < terr[:, 1:-1], axis=1)
    return blocked


class Comm:
    """基于三个端点位置（含中继当前位置）计算链路状态。"""

    def __init__(self, nodes, cp: CommParams, dem=None):
        self.nodes = nodes
        self.cp = cp
        self.dem = dem or get_dem()
        o = nodes["O01"]
        self.gw = (o.lon, o.lat, o.elev + cp.gw_ant_h)
        self.l_dir = lmax_bidir(cp.transport, cp.gateway, cp)
        self.l_acc = lmax_bidir(cp.transport, cp.relay_access, cp)
        self.l_bh = lmax_bidir(cp.relay_backhaul, cp.gateway, cp)

    # -- 单链路 ------------------------------------------------------------
    def _dist3(self, a, b):
        dh = haversine(a[0], a[1], b[0], b[1])
        return math.sqrt(dh * dh + (a[2] - b[2]) ** 2)

    def link(self, pA, pB, paramsA, paramsB, l_th):
        """返回 (可用?, FSPL, 是否遮挡, 总损耗)。"""
        d3 = self._dist3(pA, pB)
        blocked = los_blocked(pA[0], pA[1], pA[2], pB[0], pB[1], pB[2], self.dem)
        lp = float(fspl(self.cp.f_mhz, d3)) + (self.cp.l_obs if blocked else 0.0)
        return (lp <= l_th), float(fspl(self.cp.f_mhz, d3)), blocked, lp

    def direct(self, p_t):
        return self.link(p_t, self.gw, self.cp.transport, self.cp.gateway, self.l_dir)

    def access(self, p_t, p_r):
        return self.link(p_t, p_r, self.cp.transport, self.cp.relay_access, self.l_acc)

    def backhaul(self, p_r):
        return self.link(p_r, self.gw, self.cp.relay_backhaul, self.cp.gateway, self.l_bh)


# ----------------------------------------------------------------------------
# 中继无人机飞行
# ----------------------------------------------------------------------------
def relay_flight(rtype: RelayType, nodes, hover_lon, hover_lat, h_agl, dem=None):
    """
    中继架次：O01 --(爬升/巡航/下降)--> 悬停点(h_agl 离地) --服务--> O01。
    返回去程/返程时间与能耗、巡航海拔、悬停海拔。

    **巡航海拔（修正版）**
    --------------------
    题述"计划巡航海拔取该航段所经过 DEM 像元的最高地面高程以上 50 m"，
    但本航段的**终点是悬停点本身**，其作业高度为 `地面 + h_agl`，可能高于按地形算出的海拔。
    因此巡航海拔必须同时不低于悬停海拔，否则会出现"负下降高度"这种非物理结果：

        cruise = max( 沿线最高地面 + 50 , O01 地面 + 50 , 悬停海拔 )

    这样 h_dn = cruise - hover_alt >= 0，且当悬停点很高时 h_up 会相应增大，
    爬升段的时间与能耗被正确计入（而不是把负下降简单截断为 0）。
    """
    dem = dem or get_dem()
    o = nodes["O01"]
    d = haversine(o.lon, o.lat, hover_lon, hover_lat)
    gmax = dem.line_max(o.lon, o.lat, hover_lon, hover_lat)
    g_h = float(dem.at(hover_lon, hover_lat))
    hover_alt = g_h + h_agl
    cruise = max(gmax + 50.0, o.elev + 50.0, hover_alt)
    h_up = cruise - o.op_alt
    h_dn = cruise - hover_alt
    assert h_up >= -1e-9 and h_dn >= -1e-9, "中继飞行剖面出现负高度"
    t_out = h_up / rtype.v_up + d / rtype.v_cruise + h_dn / rtype.v_dn
    m = rtype.mtow
    e_out = rtype.p_cruise * (d / rtype.v_cruise) / 3600.0 + m * G * h_up / (rtype.eta_up * J_PER_KWH)
    # 返程：由悬停海拔爬升（若巡航海拔高于悬停海拔）到巡航海拔，再下降至 O01
    h_up2 = cruise - hover_alt
    h_dn2 = cruise - o.op_alt
    t_back = h_up2 / rtype.v_up + d / rtype.v_cruise + h_dn2 / rtype.v_dn
    e_back = rtype.p_cruise * (d / rtype.v_cruise) / 3600.0 + m * G * h_up2 / (rtype.eta_up * J_PER_KWH)
    return dict(t_out=t_out, e_out=e_out, t_back=t_back, e_back=e_back, t_fly=t_out + t_back,
                e_fly=e_out + e_back, cruise=cruise, hover_alt=hover_alt, ground=g_h, dist=d,
                h_up=h_up, h_dn=h_dn, h_up2=h_up2, h_dn2=h_dn2)


def relay_transit(rtype: RelayType, nodes, from_pt, to_pt, dem=None):
    """
    **空中直接转场（Mode 2）**：中继由一个悬停点直接飞往另一个悬停点，不返回 O01。
    返回 (转场时间 s, 转场能耗 kWh, 巡航海拔 m)。

    与基地返航模式（Mode 1）的差别：省去「返航 + 架次周转 τ_turn + 再出动」，
    代之以两点间的水平距离与两端高度差，黑障窗口显著缩短。
    """
    dem = dem or get_dem()
    lo1, la1, alt1 = from_pt
    lo2, la2, alt2 = to_pt
    d = haversine(lo1, la1, lo2, la2)
    gmax = dem.line_max(lo1, la1, lo2, la2)
    cruise = max(gmax, float(alt1), float(alt2)) + 50.0
    h_up = max(0.0, cruise - float(alt1))
    h_dn = max(0.0, cruise - float(alt2))
    t = h_up / rtype.v_up + d / rtype.v_cruise + h_dn / rtype.v_dn
    m = rtype.mtow
    e = (rtype.p_cruise * (d / rtype.v_cruise) / 3600.0
         + m * G * h_up / (rtype.eta_up * J_PER_KWH))
    return t, e, cruise


# ----------------------------------------------------------------------------
# 便捷
# ----------------------------------------------------------------------------
def box_index(boxes) -> Dict[str, Box]:
    return {b.bid: b for b in boxes}


if __name__ == "__main__":
    d = load_all()
    print("nodes:", len(d["nodes"]), "boxes:", len(d["boxes"]), "fleet:", {k: len(v) for k, v in d["fleet"].items()})
    print("batt:", d["batt"], "rbatt:", d["rbatt"], "rfleet:", d["rfleet"])
    print("comm:", d["comm"])
    c = Comm(d["nodes"], d["comm"])
    print("L_dir=%.1f L_acc=%.1f L_back=%.1f  Pth=%.1f" % (c.l_dir, c.l_acc, c.l_bh, d["comm"].p_sens + d["comm"].margin))
    o = d["nodes"]["O01"]
    for i in (1, 8, 15):
        s = d["nodes"][f"S{i:03d}"]
        for g in ("A", "B", "C"):
            L = leg(d["nodes"], d["ttypes"][g], "O01", s.nid, d["ttypes"][g].q_max)
            Lb = leg(d["nodes"], d["ttypes"][g], s.nid, "O01", 0.0)
            t, offs, legs, E = sortie_timeline(d["nodes"], d["ttypes"][g], ["O01", s.nid, "O01"],
                                               [d["ttypes"][g].q_max, 0.0], [0, 1, 0])
            print("%s %s d=%.0f cruise=%.1f t=%.0f E=%.3f (%.1f%% of %.1f)" %
                  (s.nid, g, L.dist, L.cruise_alt, t, E, 100 * E / d["ttypes"][g].e_use, d["ttypes"][g].e_use))
