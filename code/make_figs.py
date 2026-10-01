# -*- coding: utf-8 -*-
"""
make_figs.py —— 2026 中国研究生数学建模竞赛 D 题 论文插图生成器

生成 figs/ 下的全部插图（中文标注，SimHei / Microsoft YaHei，缺失自动回退）：
    fig_env.png           30 m DEM 晕渲 + O01/S001-S015 位置
    fig_q1_payload.png    三机型在 15 个服务区的最大安全载荷
    fig_q1_pareto.png     问题一 (架次数, 总能耗, 累计作业时间) Pareto 前沿
    fig_q1_rho.png        返航安全余量 rho 灵敏度双轴图
    fig_q2_gantt.png      问题二运输架次甘特图
    fig_q2_pareto.png     问题二四目标平行坐标图
    fig_q3_gantt.png      问题三运输 + 中继联合甘特图
    fig_q3_comm.png       通信保障图（直连/中继/中断着色）
    fig_q4_partition.png  2/3 分区方案示意

数据来源（自动降级）：
    1) results/solution.json（标准接口，见 solution_io.py）
    2) results/结果提交.xlsx / Q3_基准运输方案.xlsx / Q2_结果.xlsx 中的 Q2_运输架次 + Q2_逐箱交付
    3) results/Q1_*.xlsx、results/Q3_中继试算.xlsx
    4) 以上都缺时：调用 q1.max_safe_payload / cscan.build_solution 现场重算

容错原则：任一图数据缺失或异常时只打印/记录提示并跳过，绝不让整体中断。
运行：  cd code;  H:\\python\\python.exe make_figs.py
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.colors import LightSource

import dcore as D

# ---------------------------------------------------------------------------
# 路径与日志
# ---------------------------------------------------------------------------
BASE = D.BASE
OUT = D.RESULTS
FIGS = os.path.join(BASE, "figs")
os.makedirs(FIGS, exist_ok=True)
LOGFILE = os.path.join(OUT, "图件生成日志.txt")

_LOGLINES: List[str] = []


def log(msg: str) -> None:
    _LOGLINES.append(str(msg))
    try:
        print(msg)
    except Exception:
        pass


def flush_log() -> None:
    try:
        with open(LOGFILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_LOGLINES) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 中文字体
# ---------------------------------------------------------------------------
CJK_FONT = "DejaVu Sans"


def setup_font() -> str:
    """选择可用的中文字体，缺失自动回退。"""
    global CJK_FONT
    cands = ["SimHei", "Microsoft YaHei", "SimSun", "DengXian", "KaiTi",
             "Arial Unicode MS", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
    try:
        avail = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        avail = set()
    for c in cands:
        if c in avail:
            CJK_FONT = c
            break
    matplotlib.rcParams["font.sans-serif"] = [CJK_FONT, "DejaVu Sans"]
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["figure.dpi"] = 120
    matplotlib.rcParams["savefig.bbox"] = "tight"
    return CJK_FONT


def save_fig(fig, name: str) -> str:
    path = os.path.join(FIGS, name)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    log("  [OK] %s" % name)
    return path


# ---------------------------------------------------------------------------
# 通用数据装载
# ---------------------------------------------------------------------------
_SOL_CACHE = None
_SOL_SRC = ""


def _parse_route(s) -> List[str]:
    if s is None or (isinstance(s, float) and s != s):
        return ["O01", "O01"]
    t = str(s).replace("->", ">").replace("→", ">").replace("—", ">")
    parts = [p.strip() for p in t.replace(";", ">").replace(",", ">").split(">") if p.strip()]
    if not parts:
        return ["O01", "O01"]
    if parts[0] != "O01":
        parts = ["O01"] + parts
    if parts[-1] != "O01":
        parts = parts + ["O01"]
    return parts


def _norm(s) -> str:
    """列名归一化：去括号、去下划线、全角转半角并小写，用于跨表列名兼容。"""
    s = str(s)
    for a, b in (("（", "("), ("）", ")"), ("／", "/"), ("　", " ")):
        s = s.replace(a, b)
    s = "".join(ch for ch in s.lower() if ch not in "()_/· ")
    # 单位后缀统一：kw h -> kwh
    return s.replace("kwh", "kwh")


def _pick(df, *cands):
    """在 DataFrame 中按候选列名（兼容全/半角括号与单位后缀）挑一列。"""
    idx = {_norm(c): c for c in df.columns}
    for c in cands:
        if c in df.columns:
            return c
    for c in cands:
        k = _norm(c)
        if k in idx:
            return idx[k]
    return None


def _g(r, col, default=None):
    if col is None:
        return default
    v = r.get(col, default)
    return default if v is None else v


def _fnum(v, default=0.0):
    try:
        f = float(v)
        return default if f != f else f
    except Exception:
        return default


def _xlsx_candidates() -> List[str]:
    return [os.path.join(OUT, "结果提交.xlsx"),
            os.path.join(OUT, "Q3_基准运输方案.xlsx"),
            os.path.join(OUT, "Q2_结果.xlsx")]


def _transport_from_xlsx() -> Optional[List[dict]]:
    """从结果表构造标准 transport 记录（按优先级尝试多个文件）。"""
    for p in _xlsx_candidates():
        if not os.path.exists(p):
            continue
        try:
            xl = pd.ExcelFile(p)
        except Exception as e:
            log("  ! 打不开 %s: %s" % (os.path.basename(p), e))
            continue
        if "Q2_运输架次" not in xl.sheet_names:
            continue
        df = xl.parse("Q2_运输架次")
        if df.empty:
            continue
        c_sid = _pick(df, "架次编号")
        c_dr = _pick(df, "无人机编号")
        c_g = _pick(df, "机型编号")
        c_bat = _pick(df, "电池编号")
        c_st = _pick(df, "开始时刻_s", "开始时刻")
        c_en = _pick(df, "返回O01时刻_s", "返回O01时刻")
        c_E = _pick(df, "架次能耗_kWh", "架次能耗")
        c_soc = _pick(df, "返航SOC_pct", "返航SOC")
        c_chg = _pick(df, "充电时长_s", "充电时长")
        c_rt = _pick(df, "访问服务区顺序")
        if c_sid is None or c_rt is None:
            log("  ! %s[Q2_运输架次] 缺少必需列，跳过。" % os.path.basename(p))
            continue
        deliver = {}
        if "Q2_逐箱交付" in xl.sheet_names:
            d2 = xl.parse("Q2_逐箱交付")
            c_b = _pick(d2, "货箱编号"); c_s = _pick(d2, "架次编号")
            c_a = _pick(d2, "服务区编号"); c_t = _pick(d2, "交付完成时刻_s", "交付完成时刻")
            if c_b is not None and c_s is not None:
                for _, r in d2.iterrows():
                    bid = r[c_b]
                    if isinstance(bid, str):
                        deliver[bid] = (str(r[c_s]), str(_g(r, c_a, "")), _fnum(_g(r, c_t, 0.0)))
        recs = []
        for _, r in df.iterrows():
            route = _parse_route(r[c_rt])
            sid = str(r[c_sid])
            boxes, dlv = {}, {}
            for bid, (s0, ar, t) in deliver.items():
                if s0 == sid:
                    boxes.setdefault(ar, []).append(bid)
                    dlv[bid] = t
            recs.append(dict(
                sid=sid, drone=str(_g(r, c_dr, "")), type=str(_g(r, c_g, "")),
                battery=str(_g(r, c_bat, "")),
                start=_fnum(_g(r, c_st, 0.0)), end=_fnum(_g(r, c_en, 0.0)),
                energy=_fnum(_g(r, c_E, 0.0)),
                soc=_fnum(_g(r, c_soc, 0.0)) / 100.0,
                chg=_fnum(_g(r, c_chg, 0.0)),
                route=route, boxes=boxes, deliver=dlv))
        if recs:
            log("  · transport 来自 %s（%d 架次）" % (os.path.basename(p), len(recs)))
            return recs
    return None


def _relay_from_xlsx() -> Optional[List[dict]]:
    cands = [os.path.join(OUT, "结果提交.xlsx"), os.path.join(OUT, "Q3_中继试算.xlsx")]
    for p in cands:
        if not os.path.exists(p):
            continue
        try:
            xl = pd.ExcelFile(p)
        except Exception:
            continue
        if "Q3_中继架次" in xl.sheet_names:
            df = xl.parse("Q3_中继架次")
        elif "Sheet1" in xl.sheet_names:
            df = xl.parse("Sheet1")
        else:
            continue
        if df.empty:
            continue
        c_sid = _pick(df, "中继架次编号", "序号")
        c_dr = _pick(df, "中继无人机编号", "无人机")
        c_cp = _pick(df, "能源组件编号", "能源组件")
        c_lo = _pick(df, "悬停经度", "经度")
        c_la = _pick(df, "悬停纬度", "纬度")
        c_alt = _pick(df, "悬停海拔_m", "悬停海拔")
        c_agl = _pick(df, "离地_m", "离地")
        c_dp = _pick(df, "开始时刻_s", "开始_s", "开始")
        c_lk = _pick(df, "建链完成时刻_s", "建链完成_s", "建链完成")
        c_en = _pick(df, "服务结束时刻_s", "服务结束_s", "服务结束")
        c_bk = _pick(df, "返回O01时刻_s", "返回_s", "返回")
        c_E = _pick(df, "架次能耗_kWh", "总能耗_kWh", "总能耗")
        if c_lo is None or c_la is None or c_alt is None:
            continue
        recs = []
        for i, r in df.iterrows():
            try:
                alt = _fnum(r[c_alt])
                agl = _fnum(_g(r, c_agl, 300.0), 300.0)
                recs.append(dict(
                    sid=str(_g(r, c_sid, i + 1)), drone=str(_g(r, c_dr, "")),
                    comp=str(_g(r, c_cp, "")),
                    lon=_fnum(r[c_lo]), lat=_fnum(r[c_la]), hover_alt=alt, agl=agl,
                    ground=alt - agl,
                    depart=_fnum(_g(r, c_dp, 0.0)), link_done=_fnum(_g(r, c_lk, 0.0)),
                    end=_fnum(_g(r, c_en, 0.0)), back=_fnum(_g(r, c_bk, 0.0)),
                    e_total=_fnum(_g(r, c_E, 0.0)),
                    soc=_fnum(_g(r, _pick(df, "返航SOC", "返航SOC_pct"), 0.0)) / 100.0,
                    chg=_fnum(_g(r, _pick(df, "充电_s", "充电时长_s"), 0.0))))
            except Exception:
                continue
        if recs:
            log("  · relay 来自 %s（%d 架次）" % (os.path.basename(p), len(recs)))
            return recs
    return None


def _coverage_from_xlsx() -> Optional[List[dict]]:
    """从 结果提交.xlsx 的 Q3_通信保障 表读通信分段（运输架次编号, 起止时刻, 保障方式）。"""
    p = os.path.join(OUT, "结果提交.xlsx")
    if not os.path.exists(p):
        return None
    try:
        xl = pd.ExcelFile(p)
    except Exception:
        return None
    if "Q3_通信保障" not in xl.sheet_names:
        return None
    df = xl.parse("Q3_通信保障")
    if df.empty:
        return None
    c_sid = _pick(df, "运输架次编号"); c_t0 = _pick(df, "开始时刻_s", "开始时刻")
    c_t1 = _pick(df, "结束时刻_s", "结束时刻"); c_md = _pick(df, "保障方式")
    c_ph = _pick(df, "通信阶段"); c_rl = _pick(df, "中继架次编号")
    if c_sid is None or c_md is None or c_t0 is None or c_t1 is None:
        return None
    recs = []
    for _, r in df.iterrows():
        raw = str(_g(r, c_md, "none")).strip()
        low = raw.lower()
        # 注意：「中继」与「中断」都以「中」开头，必须分别精确判定
        if raw.startswith("直") or low in ("direct", "直连"):
            m = "direct"
        elif raw.startswith("中继") or low in ("relay", "中继"):
            m = "relay"
        else:
            m = "none"
        recs.append(dict(sid=str(r[c_sid]), phase=str(_g(r, c_ph, "")),
                         t0=_fnum(r[c_t0]), t1=_fnum(r[c_t1]), mode=m,
                         relay=str(_g(r, c_rl, ""))))
    log("  · coverage 来自 %s[Q3_通信保障]（%d 段：直连 %d / 中继 %d / 中断 %d）"
        % (os.path.basename(p), len(recs),
           sum(1 for x in recs if x["mode"] == "direct"),
           sum(1 for x in recs if x["mode"] == "relay"),
           sum(1 for x in recs if x["mode"] == "none")))
    return recs


def load_solution(force_fallback: bool = False) -> dict:
    """返回 dict(transport=..., relay=..., coverage=..., src=...)，缺数据时返回空表。

    优先级：results/solution.json → 结果提交.xlsx / Q3_基准运输方案.xlsx / Q2_结果.xlsx。
    solution.json 中 relay/coverage 为空时，自动从结果表补齐（Q3_中继试算.xlsx / Q3_通信保障）。
    """
    global _SOL_CACHE, _SOL_SRC
    if _SOL_CACHE is not None and not force_fallback:
        return _SOL_CACHE
    sol = dict(transport=[], relay=[], coverage=[], meta={}, src="", relay_src="")
    p = os.path.join(OUT, "solution.json")
    if os.path.exists(p) and not force_fallback:
        try:
            with open(p, "r", encoding="utf-8") as f:
                j = json.load(f)
            sol = dict(transport=j.get("transport", []) or [],
                       relay=j.get("relay", []) or [],
                       coverage=j.get("coverage", []) or [],
                       meta=j.get("meta", {}) or {}, src="solution.json",
                       relay_src="solution.json" if (j.get("relay") or []) else "")
            log("· 读取 results/solution.json：运输架次 %d，中继架次 %d，覆盖记录 %d"
                % (len(sol["transport"]), len(sol["relay"]), len(sol["coverage"])))
        except Exception as e:
            log("! solution.json 解析失败（%s），改用 results 表格降级。" % e)
    if not sol["transport"]:
        tr = _transport_from_xlsx()
        if tr:
            sol["transport"] = tr
            sol["src"] = "xlsx"
    if not sol["relay"]:
        try:
            rl = _relay_from_xlsx()
        except Exception as e:
            log("  ! 中继架次降级读取失败：%s" % e)
            rl = None
        if rl:
            sol["relay"] = rl
            sol["relay_src"] = "xlsx（试算）"
            log("  · 已从结果表补齐中继架次 %d 个（标注为试算方案）。" % len(rl))
    if not sol["coverage"]:
        try:
            cov = _coverage_from_xlsx()
        except Exception as e:
            log("  ! 通信分段降级读取失败：%s" % e)
            cov = None
        if cov:
            sol["coverage"] = cov
    if not sol["transport"]:
        log("! 未找到可用的运输架次数据（solution.json / 结果提交.xlsx / Q3_基准运输方案.xlsx / Q2_结果.xlsx 均不可用）。")
    _SOL_CACHE, _SOL_SRC = sol, sol["src"]
    return sol


def _boxes_by_sid(boxes) -> Dict[str, list]:
    d = {}
    for b in boxes:
        d.setdefault(b.sid, []).append(b)
    return d


@dataclass
class _ShimSortie:
    """只为了复用 comm.sortie_track 的最小架次对象。"""
    g: str
    areas: List[str]
    load: Dict[str, List[str]] = field(default_factory=dict)


class _ShimInst:
    """只为了复用 comm.py 的最小实例对象（避免 import q2 带来的重依赖）。"""

    def __init__(self, d):
        self.d = d
        self.nodes = d["nodes"]
        self.types = d["ttypes"]
        self.boxes = d["boxes"]
        self.SIDS = d["SIDS"]


# ---------------------------------------------------------------------------
# 图 1：DEM 晕渲 + 节点
# ---------------------------------------------------------------------------
DEM_BOX = dict(lon=(109.120, 109.330), lat=(22.975, 23.115))


def _dem_crop(box=DEM_BOX):
    dem = D.get_dem()
    ii = np.where((dem.lat <= box["lat"][1]) & (dem.lat >= box["lat"][0]))[0]
    jj = np.where((dem.lon >= box["lon"][0]) & (dem.lon <= box["lon"][1]))[0]
    if len(ii) == 0 or len(jj) == 0:
        ii = np.arange(dem.ny)
        jj = np.arange(dem.nx)
    Z = dem.z[ii[0]:ii[-1] + 1, jj[0]:jj[-1] + 1].astype(float)
    lon = dem.lon[jj[0]:jj[-1] + 1]
    lat = dem.lat[ii[0]:ii[-1] + 1]
    return Z, lon, lat


def _dem_background(ax, box=DEM_BOX, cmap="terrain", hill=True, contours=14, alpha=1.0):
    Z, lon, lat = _dem_crop(box)
    extent = (lon[0], lon[-1], lat[-1], lat[0])
    if hill:
        ls = LightSource(azdeg=315, altdeg=45)
        rgb = ls.shade(Z, cmap=plt.get_cmap(cmap), blend_mode="soft",
                       vert_exag=1.6, dx=30.0, dy=30.0)
        rgb[..., 3] = alpha
        im = ax.imshow(rgb, extent=extent, origin="upper", interpolation="bilinear")
    else:
        im = ax.imshow(Z, extent=extent, origin="upper", cmap=cmap, alpha=alpha)
    if contours:
        step = max(1, len(lon) // 260)
        ax.contour(lon[::step], lat[::step], Z[::step, ::step], levels=contours,
                   colors="k", linewidths=0.35, alpha=0.45)
    ax.set_aspect(1.0 / math.cos(math.radians(0.5 * (lat[0] + lat[-1]))))
    return im, Z, lon, lat


def _sid_label(sid: str) -> str:
    """服务区短标签：S001 -> 1（去掉前导零，避免与字母 O 混淆）。"""
    s = str(sid)
    t = s[1:] if s[:1].upper() == "S" else s
    try:
        return str(int(t))
    except Exception:
        return t


def fig_env(d) -> bool:
    nodes = d["nodes"]
    fig, ax = plt.subplots(figsize=(9.2, 7.4))
    im, Z, lon, lat = _dem_background(ax)
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    sm = ScalarMappable(norm=Normalize(vmin=float(Z.min()), vmax=float(Z.max())),
                        cmap=plt.get_cmap("terrain"))
    sm.set_array(Z)
    cb = fig.colorbar(sm, ax=ax, fraction=0.036, pad=0.02)
    cb.set_label("地面高程 / m（Copernicus GLO-30，30 m）", fontsize=9)
    # 等高线高程标注
    cs = ax.contour(lon[::1], lat[::1], Z[::1, ::1], levels=8, colors="k",
                    linewidths=0.3, alpha=0.35)
    ax.clabel(cs, fmt="%.0f", fontsize=5, colors="k")
    o = nodes["O01"]
    ax.plot(o.lon, o.lat, marker="*", ms=17, color="#d62728", mec="k", mew=0.6,
            ls="none", zorder=6, label="O01 调度中心")
    xs, ys, labs = [], [], []
    for sid in d["SIDS"]:
        nd = nodes[sid]
        xs.append(nd.lon); ys.append(nd.lat); labs.append(_sid_label(sid))
    ax.scatter(xs, ys, s=34, c="#1f77b4", edgecolors="k", linewidths=0.5,
               zorder=5, label="S001–S015 服务区")
    for x, y, t in zip(xs, ys, labs):
        ax.annotate(t, (x, y), textcoords="offset points", xytext=(6, 4),
                    fontsize=7.5, color="#08306b", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.62))
    ax.set_xlabel("经度 / °E"); ax.set_ylabel("纬度 / °N")
    ax.set_title("图 1  镇龙乡 30 m DEM 晕渲地形与调度中心 O01、服务区 S001–S015 分布", fontsize=11)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.85)
    ax.grid(alpha=0.18, ls=":")
    save_fig(fig, "fig_env.png")
    return True


# ---------------------------------------------------------------------------
# 图 2：Q1 最大安全载荷
# ---------------------------------------------------------------------------
def _q1_payload_table(d) -> Optional[pd.DataFrame]:
    p = os.path.join(OUT, "Q1_最大安全载荷.xlsx")
    if os.path.exists(p):
        try:
            df = pd.read_excel(p)
            need = {"服务区编号", "机型编号", "最大安全载荷_kg"}
            if need <= set(df.columns):
                log("  · 最大安全载荷来自 Q1_最大安全载荷.xlsx")
                return df
        except Exception as e:
            log("  ! Q1_最大安全载荷.xlsx 读取失败：%s" % e)
    log("  · Q1_最大安全载荷.xlsx 缺失，改用 q1.max_safe_payload 现场重算。")
    try:
        import q1 as Q1
        nodes, types = d["nodes"], d["ttypes"]
        rows = []
        for sid in d["SIDS"]:
            for g in ("A", "B", "C"):
                dt = types[g]
                q, e = Q1.max_safe_payload(nodes, dt, sid, dt.rho)
                rows.append(dict(服务区编号=sid, 机型编号=g, 最大载货质量_kg=dt.q_max,
                                 最大安全载荷_kg=q, 该载荷往返能耗_kWh=e))
        return pd.DataFrame(rows)
    except Exception as e:
        log("  ! 现场重算失败：%s" % e)
        return None


def fig_q1_payload(d) -> bool:
    df = _q1_payload_table(d)
    if df is None or df.empty:
        log("[跳过] fig_q1_payload.png —— 无最大安全载荷数据")
        return False
    sids = list(d["SIDS"])
    types = ["A", "B", "C"]
    colors = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
    qmax = {"A": d["ttypes"]["A"].q_max, "B": d["ttypes"]["B"].q_max, "C": d["ttypes"]["C"].q_max}
    x = np.arange(len(sids))
    w = 0.27
    fig, ax = plt.subplots(figsize=(10.6, 4.9))
    for i, g in enumerate(types):
        vals = []
        for sid in sids:
            sub = df[(df["服务区编号"] == sid) & (df["机型编号"] == g)]
            vals.append(float(sub["最大安全载荷_kg"].iloc[0]) if len(sub) else np.nan)
        bars = ax.bar(x + (i - 1) * w, vals, w, label="%s 型（载重上限 %.0f kg）" % (g, qmax[g]),
                      color=colors[g], edgecolor="k", linewidth=0.4)
        for xx, v in zip(bars, vals):
            if v == v and v < qmax[g] - 1e-6:
                ax.annotate("%.0f" % v, (xx.get_x() + xx.get_width() / 2, v),
                            textcoords="offset points", xytext=(0, 2), ha="center",
                            fontsize=6.4, color="#8c2d04")
    for g in types:
        ax.axhline(qmax[g], color=colors[g], ls="--", lw=0.9, alpha=0.75)
    ax.set_xticks(x); ax.set_xticklabels([s[1:] for s in sids], fontsize=8)
    ax.set_xlabel("服务区编号"); ax.set_ylabel("最大安全载荷 / kg")
    ax.set_title("图 2  三机型在 15 个服务区的最大安全载荷（虚线为载重上限，标注为受返航能量限制的取值）", fontsize=11)
    ax.legend(fontsize=8.5, ncol=3, loc="upper center")
    ax.set_ylim(0, 92)
    ax.grid(axis="y", alpha=0.25, ls=":")
    save_fig(fig, "fig_q1_payload.png")
    return True


# ---------------------------------------------------------------------------
# 图 3：Q1 Pareto 前沿
# ---------------------------------------------------------------------------
def _q1_front_points() -> List[dict]:
    pts = []
    p = os.path.join(OUT, "Q1_前沿.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for it in json.load(f):
                    pts.append(dict(name="前沿点", count=int(it["count"]),
                                    E=float(it["E"]), T=float(it["T"])))
            log("  · Q1 前沿点 %d 个（Q1_前沿.json）" % len(pts))
        except Exception as e:
            log("  ! Q1_前沿.json 读取失败：%s" % e)
    nfront = len(pts)
    xp = os.path.join(OUT, "Q1_单点组批.xlsx")
    if os.path.exists(xp):
        try:
            xl = pd.ExcelFile(xp)
            for sn in xl.sheet_names:
                df = xl.parse(sn)
                if "架次能耗_kWh" not in df.columns or "往返时间_s" not in df.columns:
                    continue
                pts.append(dict(name=sn, count=len(df),
                                E=float(df["架次能耗_kWh"].sum()),
                                T=float(df["往返时间_s"].sum())))
            log("  · Q1 具名方案 %d 个（Q1_单点组批.xlsx）" % (len(pts) - nfront))
        except Exception as e:
            log("  ! Q1_单点组批.xlsx 读取失败：%s" % e)
    # 去重
    seen, out = set(), []
    for q in pts:
        k = (q["count"], round(q["E"], 3), round(q["T"], 1))
        if k in seen:
            continue
        seen.add(k); out.append(q)
    return out


def fig_q1_pareto(d) -> bool:
    pts = _q1_front_points()
    if not pts:
        log("[跳过] fig_q1_pareto.png —— 无 Pareto 前沿数据（Q1_前沿.json / Q1_单点组批.xlsx 均缺失）")
        return False
    E = np.array([q["E"] for q in pts]); T = np.array([q["T"] for q in pts])
    C = np.array([q["count"] for q in pts])
    fig = plt.figure(figsize=(11.4, 4.8))
    ax = fig.add_subplot(1, 2, 1)
    sc = ax.scatter(E, T / 3600.0, c=C, cmap="viridis", s=110, edgecolors="k", linewidths=0.6, zorder=4)
    for q in pts:
        ax.annotate(q["name"], (q["E"], q["T"] / 3600.0), textcoords="offset points",
                    xytext=(6, 5), fontsize=7.5)
    cb = fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.02)
    cb.set_label("架次数", fontsize=9)
    ax.set_xlabel("总运输能耗 / kWh"); ax.set_ylabel("累计作业时间 / h")
    ax.set_title("(a) 能耗–工时权衡（颜色 = 架次数）", fontsize=10.5)
    ax.grid(alpha=0.25, ls=":")

    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    ax2.scatter(C, E, T / 3600.0, c=C, cmap="viridis", s=80, depthshade=False,
                edgecolors="k", linewidths=0.5)
    for q in pts:
        ax2.text(q["count"], q["E"], q["T"] / 3600.0, q["name"], fontsize=6.5)
    ax2.set_xlabel("架次数", fontsize=9); ax2.set_ylabel("总能耗 / kWh", fontsize=9)
    ax2.set_zlabel("累计工时 / h", fontsize=9)
    ax2.set_title("(b) 三目标 Pareto 前沿三维视图", fontsize=10.5)
    ax2.view_init(elev=22, azim=-58)
    fig.suptitle("图 3  问题一 Pareto 前沿：(架次数, 总运输能耗, 累计作业时间)", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save_fig(fig, "fig_q1_pareto.png")
    return True


# ---------------------------------------------------------------------------
# 图 4：rho 灵敏度
# ---------------------------------------------------------------------------
def fig_q1_rho(d) -> bool:
    p = os.path.join(OUT, "Q1_灵敏度.xlsx")
    if not os.path.exists(p):
        log("[跳过] fig_q1_rho.png —— 缺少 results/Q1_灵敏度.xlsx"
            "（运行 code/q1.py 的 sensitivity() 可生成）")
        return False
    try:
        df = pd.read_excel(p)
    except Exception as e:
        log("[跳过] fig_q1_rho.png —— Q1_灵敏度.xlsx 读取失败：%s" % e)
        return False
    if "返航安全余量比例" not in df.columns:
        log("[跳过] fig_q1_rho.png —— 灵敏度表缺少 '返航安全余量比例' 列")
        return False
    rho = df["返航安全余量比例"].astype(float).values
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    colors = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
    for g in ("A", "B", "C"):
        cm = "%s型最大安全载荷均值_kg" % g
        cmin = "%s型最小安全载荷_kg" % g
        if cm in df.columns:
            ax.plot(rho, df[cm].astype(float), marker="o", ms=5, color=colors[g],
                    label="%s 型最大安全载荷均值" % g, lw=1.8)
        if cmin in df.columns:
            ax.plot(rho, df[cmin].astype(float), marker="v", ms=4.5, color=colors[g],
                    ls=":", lw=1.2, alpha=0.85, label="%s 型最小安全载荷（最不利服务区）" % g)
    ax.axhline(80, color=colors["C"], ls="--", lw=0.8, alpha=0.6)
    ax.set_xlabel(r"返航安全余量 $\rho$")
    ax.set_ylabel("最大安全载荷 / kg")
    ax.set_title("图 4  返航安全余量 $\\rho$ 灵敏度：载荷上限与架次数", fontsize=11)
    ax.grid(alpha=0.25, ls=":")

    ax2 = ax.twinx()
    if "最少架次数" in df.columns:
        v = pd.to_numeric(df["最少架次数"], errors="coerce").astype(float).values
        if np.any(np.isfinite(v)):
            ax2.step(rho, v, where="mid", color="#c0392b", lw=2.0, marker="s", ms=5,
                     label="全场景最少架次数")
    if "最少架次方案总能耗_kWh" in df.columns:
        v2 = pd.to_numeric(df["最少架次方案总能耗_kWh"], errors="coerce").astype(float).values
        if np.any(np.isfinite(v2)):
            ax2.plot(rho, v2, color="#8e44ad", lw=1.4, ls="--", marker="^", ms=4.5, alpha=0.85,
                     label="最少架次方案总能耗 / kWh")
    ax2.set_ylabel("架次数 / 总能耗 (kWh)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.2, ncol=2, loc="lower left", framealpha=0.9)
    ax.set_xticks(rho)
    save_fig(fig, "fig_q1_rho.png")
    return True


# ---------------------------------------------------------------------------
# 图 5：Q2 运输甘特图
# ---------------------------------------------------------------------------
def _drone_order(recs: Sequence[dict]) -> List[str]:
    ids = sorted({str(r.get("drone", "")) for r in recs if r.get("drone")})
    def key(x):
        pre = "".join(ch for ch in x if ch.isalpha())
        num = "".join(ch for ch in x if ch.isdigit())
        return (pre, int(num) if num else 0)
    return sorted(ids, key=key)


def fig_q2_gantt(d, sol: dict) -> bool:
    recs = sol.get("transport") or []
    if not recs:
        log("[跳过] fig_q2_gantt.png —— 无运输架次数据")
        return False
    drones = _drone_order(recs)
    if not drones:
        log("[跳过] fig_q2_gantt.png —— 架次记录缺少无人机编号")
        return False
    ymap = {u: i for i, u in enumerate(drones)}
    colors = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
    fig, ax = plt.subplots(figsize=(11.6, 5.3))
    mk = {"A": "", "B": "", "C": ""}
    tmax = 0.0
    for r in recs:
        g = str(r.get("type", "")).upper()
        c = colors.get(g, "#7f7f7f")
        y = ymap.get(str(r.get("drone", "")), None)
        if y is None:
            continue
        s0, e0 = float(r.get("start", 0.0)), float(r.get("end", 0.0))
        tmax = max(tmax, e0)
        ax.broken_barh([(s0, max(1.0, e0 - s0))], (y - 0.34, 0.68), facecolors=c,
                       edgecolor="k", linewidth=0.5, alpha=0.9, zorder=3)
        route = [x for x in r.get("route", []) if x not in ("O01",)]
        lab = "→".join(_sid_label(x) for x in route) if route else ""
        if lab:
            ax.annotate(lab, (0.5 * (s0 + e0), y), ha="center", va="center",
                        fontsize=6.2, color="white", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.08", fc="none", ec="none"))
        chg = float(r.get("chg", 0.0) or 0.0)
        if chg > 1.0:
            ax.broken_barh([(e0, chg)], (y - 0.34, 0.68), facecolors="none",
                           edgecolor=c, hatch="////", linewidth=0.4, alpha=0.75, zorder=2)
            tmax = max(tmax, e0 + chg)
    for dl, txt in ((3600, "首批时限 3600 s"), (7200, "7200 s"), (10800, "10800 s")):
        if tmax > dl * 0.35:
            ax.axvline(dl, color="#c0392b", ls="--", lw=0.9, alpha=0.7)
            ax.annotate(txt, (dl, len(drones) - 0.4), fontsize=6.8, color="#c0392b",
                        rotation=90, va="top", ha="right")
    ax.set_yticks(range(len(drones)))
    ax.set_yticklabels(drones, fontsize=8.5)
    ax.set_ylim(-0.7, len(drones) - 0.3)
    ax.set_xlabel("时间 / s（0 为调度开始时刻）")
    ax.set_ylabel("运输无人机 / 中继无人机")
    ax.set_title("图 5  问题二运输架次甘特图（实心 = 架次作业，斜纹 = 电池充电周转）", fontsize=11)
    handles = [Patch(facecolor=colors[g], edgecolor="k",
                     label="%s 型（%s）%s" % (g, "、".join(d["fleet"][g]),
                                             "" if g in {str(x.get("type", "")).upper() for x in recs}
                                             else "（本方案未出动）"))
               for g in ("A", "B", "C")]
    handles.append(Patch(facecolor="none", edgecolor="k", hatch="////", label="充电周转时段"))
    ax.legend(handles=handles, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    ax.grid(axis="x", alpha=0.25, ls=":")
    save_fig(fig, "fig_q2_gantt.png")
    return True


# ---------------------------------------------------------------------------
# 图 6：Q2 四目标平行坐标
# ---------------------------------------------------------------------------
def fig_q2_pareto(d) -> bool:
    p = os.path.join(OUT, "Q2_raw.json")
    if not os.path.exists(p):
        log("[跳过] fig_q2_pareto.png —— 缺少 results/Q2_raw.json")
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        log("[跳过] fig_q2_pareto.png —— Q2_raw.json 解析失败：%s" % e)
        return False
    front = raw.get("front") or []
    if not front:
        log("[跳过] fig_q2_pareto.png —— Q2_raw.json 无 front 字段")
        return False
    summ = raw.get("summary") or {}
    axes_def = [("count", "架次数", True), ("energy", "总能耗 / kWh", True),
                ("makespan", "完工时间 / s", True), ("tard", "延误量 / s（越小越及时）", True)]

    def val(rec, k):
        if k in rec:
            return float(rec[k])
        return float("nan")

    allrec = [dict(name=r.get("name", "?"), **{k: val(r, k) for k, _, _ in axes_def}) for r in front]
    for nm, r in summ.items():
        allrec.append(dict(name=nm, count=float(r.get("count", np.nan)),
                           energy=float(r.get("energy", np.nan)),
                           makespan=float(r.get("makespan", np.nan)),
                           tard=float(r.get("tardiness", np.nan))))
    arr = {k: np.array([r[k] for r in allrec], dtype=float) for k, _, _ in axes_def}
    lo = {k: np.nanmin(arr[k]) for k, _, _ in axes_def}
    hi = {k: np.nanmax(arr[k]) for k, _, _ in axes_def}
    n = len(axes_def)
    fig, ax = plt.subplots(figsize=(9.6, 5.2))
    xs = np.arange(n)
    for x in xs:
        ax.axvline(x, color="#555555", lw=1.0, alpha=0.8)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            ax.plot([x - 0.02, x + 0.02], [frac, frac], color="#555555", lw=0.8)
    nfront = len(front)
    cmap = plt.get_cmap("tab10")
    for i, r in enumerate(allrec):
        ys = []
        for k, _, _ in axes_def:
            v = r[k]
            ys.append(0.5 if not np.isfinite(v) or hi[k] - lo[k] < 1e-12
                      else (v - lo[k]) / (hi[k] - lo[k]))
        isfront = i < nfront
        ax.plot(xs, ys, marker="o", ms=4.5, lw=2.2 if isfront else 1.0,
                color=cmap(i % 10), alpha=0.95 if isfront else 0.45,
                label=("%s [前沿]" % r["name"]) if isfront else ("%s（配置）" % r["name"]))
        if isfront:
            ax.annotate(r["name"], (xs[-1], ys[-1]), textcoords="offset points",
                        xytext=(6, 0), fontsize=7, color=cmap(i % 10), va="center")
    for x, (k, lab, _) in zip(xs, axes_def):
        ax.annotate("%s\nmin=%.3g" % (lab, lo[k]), (x, -0.075), ha="center", va="top",
                    fontsize=8.2, annotation_clip=False)
        ax.annotate("max=%.3g" % hi[k], (x, 1.045), ha="center", va="bottom",
                    fontsize=7.4, annotation_clip=False)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlim(-0.35, n - 0.5); ax.set_ylim(-0.02, 1.03)
    ax.set_title("图 6  问题二四目标（架次数 / 能耗 / 完工时间 / 延误量）平行坐标图", fontsize=11)
    ax.legend(fontsize=7.2, loc="upper left", framealpha=0.88)
    for s in ("left", "right", "top", "bottom"):
        ax.spines[s].set_visible(False)
    fig.subplots_adjust(bottom=0.22, top=0.9)
    save_fig(fig, "fig_q2_pareto.png")
    return True


# ---------------------------------------------------------------------------
# 图 7：Q3 运输 + 中继联合甘特图
# ---------------------------------------------------------------------------
def fig_q3_gantt(d, sol: dict) -> bool:
    tr = sol.get("transport") or []
    rl = sol.get("relay") or []
    if not tr and not rl:
        log("[跳过] fig_q3_gantt.png —— 无运输/中继架次数据")
        return False
    if not rl:
        log("[提示] fig_q3_gantt.png 只有运输架次、无中继架次，按纯运输甘特图绘制。")
    rows = _drone_order(tr) + sorted({str(r.get("drone", "")) for r in rl if r.get("drone")})
    if not rows:
        log("[跳过] fig_q3_gantt.png —— 缺少无人机编号")
        return False
    ymap = {u: i for i, u in enumerate(rows)}
    colors = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
    fig, ax = plt.subplots(figsize=(11.6, 5.8))
    tmax = 0.0
    for r in tr:
        y = ymap.get(str(r.get("drone", "")))
        if y is None:
            continue
        s0, e0 = float(r.get("start", 0.0)), float(r.get("end", 0.0))
        tmax = max(tmax, e0)
        ax.broken_barh([(s0, max(1.0, e0 - s0))], (y - 0.3, 0.6),
                       facecolors=colors.get(str(r.get("type", "")).upper(), "#7f7f7f"),
                       edgecolor="k", linewidth=0.5, alpha=0.92, zorder=3)
        route = [x for x in r.get("route", []) if x != "O01"]
        if route:
            ax.annotate("→".join(_sid_label(x) for x in route), (0.5 * (s0 + e0), y), ha="center",
                        va="center", fontsize=5.8, color="white", zorder=4)
    for i, r in enumerate(rl):
        y = ymap.get(str(r.get("drone", "")))
        if y is None:
            continue
        dep = float(r.get("depart", 0.0)); lk = float(r.get("link_done", dep))
        en = float(r.get("end", lk)); bk = float(r.get("back", en))
        tmax = max(tmax, bk)
        ax.broken_barh([(dep, max(1.0, lk - dep))], (y - 0.3, 0.6), facecolors="#f0ad4e",
                       edgecolor="k", linewidth=0.5, alpha=0.75, zorder=3)
        ax.broken_barh([(lk, max(1.0, en - lk))], (y - 0.3, 0.6), facecolors="#d9534f",
                       edgecolor="k", linewidth=0.5, hatch="\\\\\\", alpha=0.9, zorder=3)
        ax.broken_barh([(en, max(1.0, bk - en))], (y - 0.3, 0.6), facecolors="#f0ad4e",
                       edgecolor="k", linewidth=0.5, alpha=0.75, zorder=3)
        ax.annotate("#%s %.0fm" % (r.get("sid", i + 1), float(r.get("hover_alt", 0.0))),
                    (0.5 * (lk + en), y + 0.34), ha="center", va="bottom", fontsize=5.4,
                    color="#7a2a20")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8.5)
    ax.set_ylim(-0.7, len(rows) - 0.25)
    ax.axhline(len(_drone_order(tr)) - 0.5, color="k", ls=":", lw=0.9, alpha=0.6)
    ax.set_xlabel("时间 / s"); ax.set_ylabel("运输无人机（上）/ 中继无人机（下）")
    tt = "图 7  问题三运输与中继联合甘特图（中继橙 = 往返飞行，红斜纹 = 悬停建链服务）"
    if rl and sol.get("relay_src", "").startswith("xlsx"):
        tt = "图 7  问题三运输架次 + 中继试算架次联合甘特图（橙色 = 中继往返飞行，红斜纹 = 悬停建链服务）"
    ax.set_title(tt, fontsize=11)
    handles = [Patch(facecolor=c, edgecolor="k", label="%s 型运输架次" % g) for g, c in colors.items()]
    handles += [Patch(facecolor="#f0ad4e", edgecolor="k", label="中继转场飞行"),
                Patch(facecolor="#d9534f", edgecolor="k", hatch="\\\\\\", label="中继悬停建链服务")]
    ax.legend(handles=handles, fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    ax.grid(axis="x", alpha=0.25, ls=":")
    save_fig(fig, "fig_q3_gantt.png")
    return True


# ---------------------------------------------------------------------------
# 图 8：Q3 通信保障图
# ---------------------------------------------------------------------------
def _compute_coverage(d, sol: dict, dt_sample=20.0):
    """返回 (tracks, mode, relays)；mode[k] = 每个采样点的 'direct'/'relay'/'none'。"""
    import comm as C
    inst = _ShimInst(d)
    link = C.Link(inst)
    tracks, ok_all = {}, {}
    for r in sol["transport"]:
        route = [x for x in r.get("route", []) if x in d["nodes"]]
        areas = [x for x in route if x != "O01"]
        if not areas:
            continue
        s = _ShimSortie(g=str(r.get("type", "C")).upper(), areas=areas,
                        load={a: list((r.get("boxes") or {}).get(a, [])) for a in areas})
        tr = C.sortie_track(inst, s, float(r.get("start", 0.0)), dt_sample)
        if len(tr["t"]) == 0:
            continue
        ok, lp, bl = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        tracks[r.get("sid")] = tr
        ok_all[r.get("sid")] = np.asarray(ok, dtype=bool)
    return tracks, ok_all, link


def _coverage_modes(d, sol, tracks, ok_all, link, dt_sample=20.0):
    """在直连不可用采样点上判定中继是否可用。"""
    modes = {}
    for k, tr in tracks.items():
        m = np.where(~ok_all[k], "none", "direct").astype(object)
        modes[k] = m
    relay_ok = 0
    for r in sol.get("relay", []):
        pt = (float(r.get("lon", 0.0)), float(r.get("lat", 0.0)), float(r.get("hover_alt", 0.0)))
        t0, t1 = float(r.get("link_done", 0.0)), float(r.get("end", 0.0))
        if t1 <= t0:
            continue
        try:
            b_ok, _, _ = link.backhaul_ok(np.array([pt]))
            if not bool(b_ok[0]):
                continue
        except Exception:
            continue
        relay_ok += 1
        for k, tr in tracks.items():
            mask = (tr["t"] >= t0) & (tr["t"] <= t1) & (~ok_all[k])
            idx = np.nonzero(mask)[0]
            if len(idx) == 0:
                continue
            pts = np.c_[tr["lon"][idx], tr["lat"][idx], tr["alt"][idx]]
            try:
                a_ok, _, _ = link.access_ok(pts, pt)
            except Exception:
                continue
            for j, good in zip(idx, np.asarray(a_ok, dtype=bool)):
                if good:
                    modes[k][j] = "relay"
    return modes, relay_ok


def _modes_from_coverage(tracks, cov: Sequence[dict]) -> dict:
    """按 结果提交.xlsx[Q3_通信保障] / solution.json[coverage] 的分段给出各采样点链路状态。"""
    by = {}
    for c in cov:
        by.setdefault(str(c.get("sid", "")), []).append(c)
    modes = {}
    for k, tr in tracks.items():
        m = np.array(["none"] * len(tr["t"]), dtype=object)
        for c in by.get(str(k), []):
            sel = (tr["t"] >= float(c.get("t0", 0.0)) - 1e-9) & (tr["t"] <= float(c.get("t1", 0.0)) + 1e-9)
            m[sel] = str(c.get("mode", "none"))
        modes[k] = m
    return modes


def fig_q3_comm(d, sol: dict) -> bool:
    if not sol.get("transport"):
        log("[跳过] fig_q3_comm.png —— 无运输架次数据")
        return False
    try:
        import comm as C  # noqa: F401
    except Exception as e:
        log("[跳过] fig_q3_comm.png —— 无法导入 comm.py：%s" % e)
        return False
    try:
        tracks, ok_all, link = _compute_coverage(d, sol)
    except Exception as e:
        log("[跳过] fig_q3_comm.png —— 航迹/链路计算失败：%s" % e)
        log(traceback.format_exc())
        return False
    if not tracks:
        log("[跳过] fig_q3_comm.png —— 未能生成任何运输航迹")
        return False
    cov = sol.get("coverage") or []
    if cov:
        try:
            modes = _modes_from_coverage(tracks, cov)
            n_relay_ok = len({str(c.get("relay", "")) for c in cov if c.get("mode") == "relay"})
            log("  · 链路状态取自结果表的通信分段（%d 段）" % len(cov))
        except Exception as e:
            log("  ! 通信分段套用失败（%s），改用现场重算。" % e)
            cov = []
    if not cov:
        try:
            modes, n_relay_ok = _coverage_modes(d, sol, tracks, ok_all, link)
        except Exception as e:
            log("  ! 中继覆盖判定失败（%s），退化为直连/中断两色。" % e)
            modes = {k: np.where(~ok_all[k], "none", "direct").astype(object) for k in tracks}
            n_relay_ok = 0

    fig, ax = plt.subplots(figsize=(10.4, 8.0))
    _dem_background(ax, cmap="gist_earth", contours=10, alpha=0.85)
    col = {"direct": "#1a9850", "relay": "#2b6cb0", "none": "#d73027"}
    nm = {"direct": 0, "relay": 0, "none": 0}
    for k, tr in tracks.items():
        md = modes[k]
        for code in ("direct", "relay", "none"):
            sel = (md == code)
            if not sel.any():
                continue
            nm[code] += int(sel.sum())
            ax.plot(tr["lon"][sel], tr["lat"][sel], ls="none", marker=".", ms=3.4,
                    color=col[code], zorder=5)
    for r in sol.get("relay", []):
        ax.plot(float(r.get("lon", 0)), float(r.get("lat", 0)), marker="^", ms=10,
                color="#f0ad4e", mec="k", mew=0.7, ls="none", zorder=7)
        ax.annotate("#%s\n%.0fm" % (r.get("sid", ""), float(r.get("hover_alt", 0.0))),
                    (float(r.get("lon", 0)), float(r.get("lat", 0))), textcoords="offset points",
                    xytext=(5, 3), fontsize=5.8, color="#7a2a20", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6))
    o = d["nodes"]["O01"]
    ax.plot(o.lon, o.lat, marker="*", ms=18, color="#d62728", mec="k", mew=0.6, ls="none",
            zorder=9, label="O01（G01 网关）")
    for sid in d["SIDS"]:
        nd = d["nodes"][sid]
        ax.plot(nd.lon, nd.lat, marker="s", ms=4.5, color="#08306b", ls="none", zorder=6)
        ax.annotate(_sid_label(sid), (nd.lon, nd.lat), textcoords="offset points", xytext=(4, -8),
                    fontsize=6.6, color="#08306b", zorder=7)
    tot = max(1, sum(nm.values()))
    cov_sids = len({str(c.get("sid", "")) for c in (sol.get("coverage") or [])
                    if c.get("mode") == "relay"})
    handles = [Line2D([], [], color=col["direct"], marker=".", ls="none", ms=8,
                      label="直连可用（%.1f%%）" % (100 * nm["direct"] / tot)),
               Line2D([], [], color=col["relay"], marker=".", ls="none", ms=8,
                      label="需中继保障（%.1f%%）" % (100 * nm["relay"] / tot)),
               Line2D([], [], color=col["none"], marker=".", ls="none", ms=8,
                      label="通信中断（%.1f%%）" % (100 * nm["none"] / tot)),
               Line2D([], [], color="#f0ad4e", marker="^", ls="none", ms=9, mec="k",
                      label="中继悬停点：中继架次 %d 个，保障运输架次 %d 个"
                            % (len(sol.get("relay", [])), cov_sids or n_relay_ok))]
    ax.legend(handles=handles, fontsize=8, loc="upper left", framealpha=0.9)
    ax.set_xlabel("经度 / °E"); ax.set_ylabel("纬度 / °N")
    ttl = "图 8  问题三通信保障图：运输航迹按链路状态着色（采样步长 %.0f s）" % 20.0
    if sol.get("relay_src", "").startswith("xlsx"):
        ttl += "\n（中继悬停点为试算方案，尚待与运输排程联合校验）"
    ax.set_title(ttl, fontsize=11)
    save_fig(fig, "fig_q3_comm.png")
    log("  · 链路采样点：直连 %d，中继 %d，中断 %d" % (nm["direct"], nm["relay"], nm["none"]))
    return True


# ---------------------------------------------------------------------------
# 图 9：Q4 分区示意
# ---------------------------------------------------------------------------
def _find_q4_file() -> Optional[str]:
    for nm in ("Q4_分区配置.xlsx", "Q4_结果.xlsx", "Q4_分区.xlsx"):
        p = os.path.join(OUT, nm)
        if os.path.exists(p):
            return p
    return None


def fig_q4_partition(d) -> bool:
    p = _find_q4_file()
    if p is None:
        log("[跳过] fig_q4_partition.png —— 未找到 results/Q4_分区配置.xlsx"
            "（问题四尚未求解；该图将在 Q4 结果生成后自动产出）")
        return False
    try:
        xl = pd.ExcelFile(p)
    except Exception as e:
        log("[跳过] fig_q4_partition.png —— %s 读取失败：%s" % (os.path.basename(p), e))
        return False
    sn = None
    for s in xl.sheet_names:
        if "分区" in s:
            sn = s
            break
    if sn is None:
        sn = xl.sheet_names[0]
    df = xl.parse(sn)
    if df.empty:
        log("[跳过] fig_q4_partition.png —— %s[%s] 为空表" % (os.path.basename(p), sn))
        return False
    cols = list(df.columns)
    # 列名容错匹配（K（2或3）/ 任务组编号 / 服务区列表）
    col_k = next((c for c in cols if _norm(c) in ("k", "k2或3", "分区数")), None)
    if col_k is None:
        col_k = next((c for c in cols if _norm(c).startswith("k")), None)
    col_g = next((c for c in cols if "组编号" in str(c)), None)
    col_s = next((c for c in cols if "服务区列表" in str(c) or "服务区" in str(c)), None)
    if col_s is None:
        log("[跳过] fig_q4_partition.png —— %s[%s] 缺少 '服务区列表' 列"
            % (os.path.basename(p), sn))
        return False
    groups: Dict[int, Dict[int, List[str]]] = {}
    for idx, (_, r) in enumerate(df.iterrows()):
        try:
            K = int(float(r[col_k])) if col_k is not None and r[col_k] == r[col_k] else 2
        except Exception:
            K = 2
        gid = None
        if col_g is not None:
            mtxt = re.search(r"(\d+)\s*$", str(r[col_g]))
            gid = int(mtxt.group(1)) if mtxt else None
        if gid is None:
            gid = len(groups.get(K, {})) + 1
        raw = str(r[col_s]).replace("，", ";").replace(",", ";").replace("、", ";")
        sids = []
        for x in raw.split(";"):
            x = x.strip().strip("{}")
            if not x:
                continue
            if x.startswith("S"):
                sids.append(x)
            elif x.isdigit():
                sids.append("S%03d" % int(x))
        if sids:
            groups.setdefault(K, {})[gid] = sids
    if not groups:
        log("[跳过] fig_q4_partition.png —— 分区表解析后为空")
        return False
    Ks = sorted(groups)
    log("  · 分区方案：%s" % "；".join(
        "K=%d 共 %d 组（%s）" % (K, len(groups[K]),
                              " / ".join("%d 区" % len(v) for v in groups[K].values()))
        for K in Ks))
    fig, axes = plt.subplots(1, len(Ks), figsize=(6.4 * len(Ks), 6.6), squeeze=False)
    pal = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00"]
    for ax, K in zip(axes[0], Ks):
        _dem_background(ax, cmap="gist_earth", contours=8, alpha=0.8)
        o = d["nodes"]["O01"]
        ax.plot(o.lon, o.lat, marker="*", ms=17, color="#d62728", mec="k", mew=0.6,
                ls="none", zorder=8)
        for gi, (g, sids) in enumerate(sorted(groups[K].items())):
            c = pal[gi % len(pal)]
            for sid in sids:
                nd = d["nodes"].get(sid)
                if nd is None:
                    continue
                ax.plot([o.lon, nd.lon], [o.lat, nd.lat], color=c, lw=0.9, alpha=0.55, zorder=4)
                ax.plot(nd.lon, nd.lat, marker="o", ms=8.5, color=c, mec="k", mew=0.7,
                        ls="none", zorder=7)
                ax.annotate(_sid_label(sid), (nd.lon, nd.lat), textcoords="offset points",
                            xytext=(6, 2), fontsize=7.2, color="k", zorder=9,
                            bbox=dict(boxstyle="round,pad=0.10", fc="white",
                                      ec=c, lw=0.8, alpha=0.85))
        ax.set_title("%d 分区方案（%s）" % (K, " / ".join(
            "组%d：%d 个服务区" % (g, len(s)) for g, s in sorted(groups[K].items()))), fontsize=10)
        ax.set_xlabel("经度 / °E"); ax.set_ylabel("纬度 / °N")
    fig.suptitle("图 9  问题四服务区分区方案示意（同色 = 同一任务组，各组资源独立核算）", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save_fig(fig, "fig_q4_partition.png")
    return True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    f = setup_font()
    log("=" * 74)
    log("make_figs.py —— D 题论文插图生成")
    log("中文字体：%s" % f)
    log("输出目录：%s" % FIGS)

    try:
        d = D.load_all()
        log("· 基础数据：节点 %d，服务区 %d，货箱 %d，机队 %s"
            % (len(d["nodes"]), len(d["SIDS"]), len(d["boxes"]),
               {k: len(v) for k, v in d["fleet"].items()}))
    except Exception as e:
        log("!! 基础数据装载失败：%s" % e)
        log(traceback.format_exc())
        flush_log()
        return 2

    sol = load_solution()
    log("· 解数据来源：%s" % (sol.get("src") or "无"))

    tasks = [
        ("fig_env.png", lambda: fig_env(d)),
        ("fig_q1_payload.png", lambda: fig_q1_payload(d)),
        ("fig_q1_pareto.png", lambda: fig_q1_pareto(d)),
        ("fig_q1_rho.png", lambda: fig_q1_rho(d)),
        ("fig_q2_gantt.png", lambda: fig_q2_gantt(d, sol)),
        ("fig_q2_pareto.png", lambda: fig_q2_pareto(d)),
        ("fig_q3_gantt.png", lambda: fig_q3_gantt(d, sol)),
        ("fig_q3_comm.png", lambda: fig_q3_comm(d, sol)),
        ("fig_q4_partition.png", lambda: fig_q4_partition(d)),
    ]
    ok = 0
    for name, fn in tasks:
        log("-- %s" % name)
        try:
            if fn():
                ok += 1
        except Exception as e:
            log("  ! %s 生成异常，已跳过：%s" % (name, e))
            log(traceback.format_exc())
    log("-" * 74)
    log("完成：成功 %d / %d 张" % (ok, len(tasks)))
    try:
        pngs = sorted(x for x in os.listdir(FIGS) if x.lower().endswith(".png"))
        log("figs/ 现有：%s" % ", ".join(pngs))
    except Exception:
        pass
    flush_log()
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
