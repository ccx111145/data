# -*- coding: utf-8 -*-
"""
make_figs_en.py —— 英文 SCI 稿的实验图（全部由结果文件生成）。

产出（写入 figs/，供 paper_en/main.tex 通过 \\Dfig 引用）：
  fig_en_channel.png   信道口径对比：通信需求、可用悬停点、最小台数
  fig_en_baseline.png  中继侧基线夹逼：覆盖抽象 / 严格下界 / 构造性可行
  fig_en_feedback.png  协同再调度：赤字无法消除，且运输代价未变
  fig_en_modes.png     换位模式：黑障窗口与 (★) 成立率

用法：python make_figs_en.py
"""
from __future__ import annotations

import io
import json
import os

import numpy as np

import dcore as D

OUT = D.RESULTS
FIGS = D.FIGS

# 画布宽度（英寸）——必须与**目标版式的显示宽度**一致，否则图内字号会等比缩小。
#   IEEEtran 双栏跨栏显示 ≈7.07 in  -> 默认 7.2
#   elsarticle preprint 单栏显示 ≈5.3 in -> 用环境变量覆盖为 5.4
# 用法：DTS_FIGW=5.4 python make_figs_en.py
FIGW = float(os.environ.get("DTS_FIGW", "7.2"))


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # 字号按**最终排版宽度**定，而不是按画布尺寸定：这些图在 IEEEtran 双栏里
    # 会被缩到约 8.8 cm 宽，9 pt 的字缩完只剩 ~6 pt，100% 缩放下发虚。
    # 因此把基准字号提到 11、子图标题提到 12.5，并统一导出 PDF 矢量图
    # （见 save_fig：同时写 300 dpi PNG 供预览、矢量 PDF 供 LaTeX 内嵌）。
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8,
        # 子图标题统一 9.5 pt（略大于正文 8）。set_title 未显式给 fontsize 的
        # 全部走这里，避免 13 处逐个改还漏掉。基准字号按**最终排版宽度**定：
        # 图以 7.2 in 画布生成、在 IEEEtran 里跨双栏显示约 7.07 in，
        # 缩放比≈1.0，所以这里的 8 pt 就是页面上的 8 pt（正文约 10 pt 的 80%）。
        "axes.titlesize": 9.5,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.alpha": 0.28,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    return plt


def save_fig(fig, plt, stem, raster_ok=True):
    """把一张图同时写成矢量 PDF（给 LaTeX）与 300 dpi PNG（给预览/网页）。

    为什么必须双份：双栏排版里只有矢量图在任意缩放下都锐利；但整幅栅格底图
    （研究区晕渲）转矢量只会把 PDF 撑大而不增加清晰度，所以对那张图以
    300 dpi 的 PNG 为主，PDF 由 LaTeX 自动回退使用。
    返回：写入的 PDF 路径（若可用），否则 PNG 路径。
    """
    # 统一处理多子图的间距问题：截图反映出 (a)/(b) 标题会互相压、
    # 两行刻度标签会横向重叠。这里在保存前做一次 tight_layout，
    # 并把子图间距放宽（wspace 0.34 / hspace 0.42），比逐个调 set_title 可靠。
    try:
        n_ax = len(fig.axes)
        if n_ax > 1:
            fig.subplots_adjust(wspace=0.42, hspace=0.42)
        fig.tight_layout()
    except Exception:                                              # noqa: BLE001
        pass
    pdf = os.path.join(FIGS, stem + ".pdf")
    png = os.path.join(FIGS, stem + ".png")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")           # matplotlib 的 PDF 后端即矢量    plt.close(fig)
    return pdf if os.path.exists(pdf) else png


C_OBS, C_P, C_PU = "#4C72B0", "#C44E52", "#8172B2"


def fig_channel(plt):
    d = rd("信道模型对比.json")
    res = d.get("results") or {}
    names = ["observed", "p526", "p526ub"]
    labels = ["constant\npenalty", "P.526\nsingle edge", "P.526\nupper bound"]
    cols = [C_OBS, C_P, C_PU]
    inst = [(res.get(m, {}).get("transport") or {}).get("instances", 0) for m in names]
    cand = [res.get(m, {}).get("cand_pts", 0) for m in names]
    nstar = [res.get(m, {}).get("N_crit") or 0 for m in names]
    if not any(inst):
        print("  ! 缺 信道模型对比.json，跳过 fig_en_channel")
        return None
    fig, ax = plt.subplots(1, 3, figsize=(FIGW, round(FIGW * 0.2948, 2)))
    x = np.arange(3)
    ax[0].bar(x, inst, color=cols, width=0.62)
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels, rotation=30, ha="right",
                     rotation_mode="anchor")
    ax[0].set_ylabel("Outage incidences")
    for xi, v in zip(x, inst):
        ax[0].text(xi, v * 1.01, "%d" % v, ha="center", va="bottom", rotation=90, fontsize=9.5)
    ax[1].bar(x, cand, color=cols, width=0.62)
    ax[1].set_xticks(x); ax[1].set_xticklabels(labels, rotation=30, ha="right",
                     rotation_mode="anchor")
    ax[1].set_ylabel("Backhaul-feasible hover points")
    for xi, v in zip(x, cand):
        ax[1].text(xi, v * 1.01, "%d" % v, ha="center", va="bottom", rotation=90, fontsize=9.5)
    ax[2].bar(x, nstar, color=cols, width=0.62)
    ax[2].set_xticks(x); ax[2].set_xticklabels(labels, rotation=30, ha="right",
                     rotation_mode="anchor")
    ax[2].set_ylabel("Smallest $N$ with a schedule")
    ax[2].set_ylim(0, max(nstar + [3]) + 1.2)
    for xi, v in zip(x, nstar):
        ax[2].text(xi, v + 0.08, "%d" % v, ha="center", va="bottom", rotation=90, fontsize=9.5, weight="bold")
    ax[2].axhline(2, color="0.35", ls="--", lw=1.0)
    ax[2].text(2.42, 2.06, "inventory", fontsize=10.5, color="0.35", ha="right")
    fig.tight_layout()
    return save_fig(fig, plt, "fig_en_channel")


def fig_baseline(plt):
    d = rd("中继基线与下界.json")
    if not d:
        print("  ! 缺 中继基线与下界.json，跳过 fig_en_baseline")
        return None
    naive, lb, gr = d.get("N_naive"), d.get("LB_handover"), d.get("N_greedy")
    if gr is None:
        return None
    fig, ax = plt.subplots(1, 2, figsize=(FIGW, round(FIGW * 0.3480, 2)))
    names = ["coverage\nonly", "lower\nbound", "constructive\n(handover-aware)"]
    vals = [naive or 0, lb or 0, gr]
    cols = ["#B0B0B0", "#DD8452", "#55A868"]
    b = ax[0].bar(np.arange(3), vals, color=cols, width=0.6)
    ax[0].set_xticks(np.arange(3)); ax[0].set_xticklabels(names, rotation=30, ha="right",
                     rotation_mode="anchor", fontsize=9.5)
    ax[0].set_ylabel("Relay fleet size")
    # 留足余量：柱顶数值是竖排的，若 ylim 不够会顶进标题区（截图里
    # "19221953 <-> (a) Communication dema" 的重叠就是这么来的）
    ax[0].set_ylim(0, max(vals) * 1.32 + 0.5)
    for r, v in zip(b, vals):
        ax[0].text(r.get_x() + r.get_width() / 2, v + 0.07, "%d" % v,
                   ha="center", va="bottom", rotation=90, fontsize=9.5, weight="bold")
    lo = max([v for v in (naive, lb) if v is not None] or [0])
    ax[0].annotate("", xy=(2.32, lo), xytext=(2.32, gr),
                   arrowprops=dict(arrowstyle="<->", color="#C44E52", lw=1.4))
    ax[0].text(2.38, (lo + gr) / 2, "$N^*\\in[%d,%d]$" % (lo, gr),
               color="#C44E52", fontsize=10.5, va="center")
    ax[0].text(0.02, 0.96, "handover premium = %d" % (gr - (naive or 0)),
               transform=ax[0].transAxes, ha="left", va="top",
               fontsize=10.5, color="#333333")
    # (b) 相位并集的最小覆盖点数
    rows = d.get("LB_handover_rows") or []
    if rows:
        xs = np.arange(len(rows))
        ys = [r.get("min_points") or 0 for r in rows]
        ax[1].bar(xs, ys, color="#DD8452", width=0.55)
        ax[1].set_xticks(xs)
        ax[1].set_xticklabels(["%d$\\to$%d" % (r["i"], r["i"] + 1) for r in rows])
        ax[1].set_xlabel("adjacent phase pair")
        ax[1].set_ylabel("Minimum covering points")
        ax[1].set_ylim(0, max(ys + [1]) + 0.8)
        for xi, v in zip(xs, ys):
            ax[1].text(xi, v + 0.05, "%d" % v, ha="center", va="bottom", rotation=90, fontsize=9.5)
    fig.tight_layout()
    return save_fig(fig, plt, "fig_en_baseline")


def fig_feedback(plt):
    d = rd("协同再调度.json")
    res = d.get("results") or {}
    if not res:
        print("  ! 缺 协同再调度.json，跳过 fig_en_feedback")
        return None
    fig, ax = plt.subplots(1, 2, figsize=(FIGW, round(FIGW * 0.2948, 2)))
    modes = ["base", "air"]
    labs = ["M1 depot return", "M2 air transit"]
    xs = np.arange(2)
    d0 = [(res.get(m) or {}).get("baseline", {}).get("deficit_cells", 0) for m in modes]
    d1 = [(res.get(m) or {}).get("after", {}).get("deficit_cells", 0) for m in modes]
    w = 0.34
    ax[0].bar(xs - w * 0.62, d0, w, label="before co-design", color="#4C72B0")
    ax[0].bar(xs + w * 0.62, d1, w, label="after co-design", color="#DD8452")
    ax[0].set_xticks(xs)
    ax[0].set_ylabel("Handover deficiency $D$ (cells$\\cdot$windows)")
    ax[0].set_ylim(0, max(list(d0) + list(d1)) * 1.30)
    # 颜色含义写在图题里：左(蓝)=before co-design，右(橙)=after。
    # 每对柱只标一次：两柱高度**按构造相同**（这正是"赤字不变"这个结论本身），
    # 并排打两个 5 位数既冗余又必然挤在一起。标签放该对正上方居中。
    for xi, a_ in zip(xs, d0):
        ax[0].text(xi, a_ + max(list(d0) + list(d1)) * 0.05, "%d" % a_,
                   ha="center", va="bottom", fontsize=8.5, weight="bold")
    ax[0].set_xticklabels(labs, fontsize=8)
    # (b) span profile vs the required window: the direct visualisation of (★)
    sb = rd("跨度黑障不等式.json")
    ser = sb.get("span_series") or {}
    cells = ser.get("cells") or []
    span = ser.get("span") or []
    bm1 = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 1") or {}
    bm2 = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 2") or {}
    if cells and span:
        x = np.asarray(cells, dtype=float)
        s = np.asarray(span, dtype=float)
        # span 以格数给出；换算到时间轴便于与黑障窗口（秒）比较
        dt = float(np.median(np.diff(x))) if len(x) > 2 else 11.0
        ax[1].plot(x, s * dt, lw=1.2, color="#4C72B0",
                   label="span (M1 candidate set)")
        w1 = bm1.get("p50", {}).get("w_s")
        w2 = bm2.get("p50", {}).get("w_s")
        if w1:
            ax[1].axhline(w1, color="#4C72B0", ls="--", lw=1.1,
                          label="required window, M1 (%.0f s)" % w1)
        if w2:
            ax[1].axhline(w2, color="#C44E52", ls="--", lw=1.1,
                          label="required window, M2 (%.0f s)" % w2)
        ax[1].fill_between(x, 0, np.minimum(s * dt, w1 or 1e9),
                           color="#4C72B0", alpha=0.10)
        ax[1].set_xlabel("Demand cell time (s)")
        ax[1].set_ylabel("Span: longest single-point cover (s)")
        ax[1].legend(fontsize=7.5, loc="upper center", ncol=1, framealpha=0.92)
    else:
        # span 序列缺席时的退路：留空轴但标注原因，避免整张图崩掉。
        ax[1].text(0.5, 0.5, "span series unavailable",
                   transform=ax[1].transAxes, ha="center", va="center",
                   fontsize=8.5, color="0.4")
    fig.subplots_adjust(wspace=0.42)
    return save_fig(fig, plt, "fig_en_feedback")


def fig_modes(plt):
    sb = rd("跨度黑障不等式.json")
    mc = rd("换位模式对比.json")
    bm = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 1") or {}
    am = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 2") or {}
    if not bm or not am:
        print("  ! 缺 跨度黑障不等式.json，跳过 fig_en_modes")
        return None
    fig, ax = plt.subplots(1, 2, figsize=(FIGW, round(FIGW * 0.3480, 2)))
    xs = np.arange(2)
    wmed = [bm.get("p50", {}).get("w_s", 0), am.get("p50", {}).get("w_s", 0)]
    rate = [100 * bm.get("p50", {}).get("rate", 0), 100 * am.get("p50", {}).get("rate", 0)]
    b = ax[0].bar(xs, wmed, color=[C_OBS, C_P], width=0.55)
    ax[0].set_xticks(xs); ax[0].set_xticklabels(["M1 depot return", "M2 air transit"])
    ax[0].set_ylabel("Median blackout window (s)")
    for r, v in zip(b, wmed):
        ax[0].text(r.get_x() + r.get_width() / 2, v * 1.01, "%.0f" % v,
                   ha="center", va="bottom", fontsize=10.5, weight="bold")
    ax[0].set_ylim(0, max(wmed) * 1.22)
    b2 = ax[1].bar(xs, rate, color=[C_OBS, C_P], width=0.55)
    ax[1].set_xticks(xs); ax[1].set_xticklabels(["M1 depot return", "M2 air transit"])
    ax[1].set_ylabel("$(\\star)$ satisfied on cells (%)")
    ax[1].set_ylim(0, 108)
    ax[1].axhline(100, color="0.5", ls=":", lw=1.0)
    for r, v in zip(b2, rate):
        ax[1].text(r.get_x() + r.get_width() / 2, v + 1.2, "%.1f%%" % v,
                   ha="center", va="bottom", fontsize=10.5, weight="bold")
    # 注：早先这里有一个红框注释 "$N=2$ infeasible in both modes"，画在坐标区内会
    # 压住 72.0% 那根柱子；而且这个结论图题里已经写了。图内不再放散文注释——
    # 这是本轮"图内浮动文字互相压"的根因，统一规则：结论写图题，图里只留
    # 轴标签、刻度、图例与数据标签。
    fig.subplots_adjust(wspace=0.42, left=0.11)
    return save_fig(fig, plt, "fig_en_modes")


def fig_env(plt):
    """图 1：研究区 30 m DEM 晕渲（卫星式底图）+ 调度中心与 15 个服务区。

    英文版对应中文稿的 figs/fig_env.png（同一个 DEM 裁剪框、同一套节点坐标），
    因此中英两稿的"研究区图"是同一份数据、只是标注语言不同。
    节点坐标与高程来自附件，DEM 为 Copernicus GLO-30。
    """
    import math
    from matplotlib.colors import LightSource, Normalize
    from matplotlib.cm import ScalarMappable

    dem = D.get_dem()
    # 与中文稿 make_figs.py 完全相同的裁剪框
    box = dict(lon=(109.120, 109.330), lat=(22.975, 23.115))
    ii = np.where((dem.lat <= box["lat"][1]) & (dem.lat >= box["lat"][0]))[0]
    jj = np.where((dem.lon >= box["lon"][0]) & (dem.lon <= box["lon"][1]))[0]
    if len(ii) == 0 or len(jj) == 0:
        ii = np.arange(dem.ny); jj = np.arange(dem.nx)
    Z = dem.z[ii[0]:ii[-1] + 1, jj[0]:jj[-1] + 1].astype(float)
    lon = dem.lon[jj[0]:jj[-1] + 1]
    lat = dem.lat[ii[0]:ii[-1] + 1]

    # 节点表：从附件解析出的 q2.Instance 取，保证与建模口径一致
    import q2 as Q
    inst = Q.Instance()
    nodes = inst.nodes
    sids = list(inst.SIDS)

    fig, ax = plt.subplots(figsize=(FIGW, round(FIGW * 0.3685, 2)))
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(Z, cmap=plt.get_cmap("terrain"), blend_mode="soft",
                   vert_exag=1.6, dx=30.0, dy=30.0)
    ax.imshow(rgb, extent=(lon[0], lon[-1], lat[-1], lat[0]), origin="upper",
              interpolation="bilinear")
    cs = ax.contour(lon, lat, Z, levels=8, colors="k", linewidths=0.3, alpha=0.35)
    ax.clabel(cs, fmt="%.0f", fontsize=7.5, colors="k")
    # 等值距由裁剪框的高程范围决定（本算例 80 m）。图注里写的数字必须与这里一致，
    # 所以把它打印出来供核对，而不是靠手写。
    if len(cs.levels) > 1:
        print("  [fig_en_env] contour levels %s -> interval %.0f m"
              % ([int(round(float(v))) for v in cs.levels],
                 float(cs.levels[1] - cs.levels[0])))

    sm = ScalarMappable(norm=Normalize(vmin=float(Z.min()), vmax=float(Z.max())),
                        cmap=plt.get_cmap("terrain"))
    sm.set_array(Z)
    cb = fig.colorbar(sm, ax=ax, fraction=0.036, pad=0.02)
    cb.set_label("Ground elevation (m), Copernicus GLO-30, 30 m", fontsize=10.5)

    o = nodes["O01"]
    ax.plot(o.lon, o.lat, marker="*", ms=17, color="#d62728", mec="k", mew=0.6,
            ls="none", zorder=6, label="O01 depot")
    xs, ys, labs = [], [], []
    for sid in sids:
        nd = nodes[sid]
        xs.append(nd.lon); ys.append(nd.lat)
        labs.append(str(sid).lstrip("S") or str(sid))
    ax.scatter(xs, ys, s=34, c="#1f77b4", edgecolors="k", linewidths=0.5,
               zorder=5, label="S001-S015 demand areas")
    for x, y, t in zip(xs, ys, labs):
        ax.annotate(t, (x, y), textcoords="offset points", xytext=(6, 4),
                    fontsize=8.5, color="#08306b", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.62))

    ax.set_xlabel("Longitude ($^\\circ$E)")
    ax.set_ylabel("Latitude ($^\\circ$N)")
    ax.set_aspect(1.0 / math.cos(math.radians(0.5 * (lat[0] + lat[-1]))))
    ax.set_title("Study area: 30 m DEM hillshade, depot O01 and areas S001-S015",
                 fontsize=10.5)
    ax.legend(loc="upper left", fontsize=10.5, framealpha=0.85)
    ax.grid(alpha=0.18, ls=":")
    # 这一张的底是**栅格**晕渲图，转矢量只会把 PDF 撑大而不会更清晰；
    # 因此只写 300 dpi PNG（约 2950×2340 px），LaTeX 端在没有同名 PDF 时自动用它。
    # 清晰度来自像素密度，其余六张才是矢量 PDF。
    png = os.path.join(FIGS, "fig_en_env.png")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  [fig_en_env] 300 dpi raster %d x %d px"
          % tuple(int(round(v * 300)) for v in fig.get_size_inches()))
    return png


def fig_terrain(plt):
    """图 7：受控地形族——机队规模相变 与 失联需求随地形强度的增长。

    这是中文稿 figs/fig_terrain_phase.png 的**英文版**：数据源、分组、坐标量完全相同，
    只是把字体与标签换成英文（原图直接引用进英文稿会留下中文轴标，属硬伤）。
    中文原图保持不变，仍供国赛答卷使用。
    """
    d = rd("多地形基准.json")
    rows = [r for r in (d.get("rows") or []) if r.get("relay_ok")]
    if not rows:
        print("  ! 缺 多地形基准.json，跳过 fig_en_terrain")
        return None
    fam_lab = {"flat": "Relief-scaled family", "shift": "Translated family",
               "canyon": "Deep-canyon family"}
    marks = {"flat": "o", "shift": "^", "canyon": "s"}
    fig, ax = plt.subplots(1, 2, figsize=(FIGW, round(FIGW * 0.40, 2)))
    for fam in ("flat", "shift", "canyon"):
        rs = [r for r in rows if str(r.get("tag", "")).startswith(fam)]
        if not rs:
            continue
        rs.sort(key=lambda r: r["occlusion"]["ratio"])
        x = [100 * r["occlusion"]["ratio"] for r in rs]
        y = [(4 if r.get("N_crit") is None else r["N_crit"]) for r in rs]
        ax[0].plot(x, y, marker=marks[fam], lw=1.8, ms=6,
                   label=fam_lab[fam])
        ax[1].plot(x, [r["instances"] for r in rs], marker=marks[fam], lw=1.8,
                   ms=6, label=fam_lab[fam])
    ax[0].set_xlabel("Occlusion ratio (%)")
    ax[0].set_ylabel("Min. feasible relay fleet $N^{*}$   ($>$3 shown as 4)")
    ax[0].set_yticks([0, 1, 2, 3, 4])
    ax[0].set_yticklabels(["0", "1", "2", "3", "$>$3"])
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=10.5)
    ax[1].set_xlabel("Occlusion ratio (%)")
    ax[1].set_ylabel("Outage incidences")
    ax[1].grid(alpha=0.3)
    ax[1].legend(fontsize=10.5)
    fig.tight_layout()
    return save_fig(fig, plt, "fig_en_terrain")


def main():
    os.makedirs(FIGS, exist_ok=True)
    # 正文在 paper_en/ 下编译并引用 figs/xxx，因此英文插图必须落到编译器能找到的目录。
    # 输出目录可用 DTS_FIGDIR 覆盖：画布宽度必须≈目标版式的显示宽度，图内字号才不被
    # 缩放。elsarticle 单栏显示 ≈5.3 in、IEEEtran 跨栏显示 ≈7.07 in，两者需要不同
    # 画布宽度，故按版式各生成一套、互不覆盖（见 code/run_all_en.py 的调用处）。
    en = os.environ.get("DTS_FIGDIR") or os.path.join(D.BASE, "paper_en", "figs")
    os.makedirs(en, exist_ok=True)
    plt = _plt()
    out = []
    for fn in (fig_env, fig_channel, fig_baseline, fig_feedback, fig_modes,
               fig_terrain):
        p = fn(plt)
        if p:
            out.append(p)
            dst = os.path.join(en, os.path.basename(p))
            try:
                import shutil
                shutil.copy2(p, dst)
            except Exception:                                       # noqa: BLE001
                pass
            print("  [OK] %s" % os.path.basename(p))
    print("完成：%d 张英文稿插图" % len(out))
    for p in out:
        print("   ", p)


if __name__ == "__main__":
    main()
