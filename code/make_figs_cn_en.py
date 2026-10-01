# -*- coding: utf-8 -*-
"""make_figs_cn_en.py —— 把中文竞赛稿里"运输侧与协同"的图改成英文，供 TR-C 稿使用。

背景：中文稿 9 张图，英文 TR-C 稿只覆盖了通信/中继侧的 8 张，
运输侧（Pareto 前沿、架次甘特图、分区方案）**一张都没有**——而正文反复
引用 N_naive / ALNS / Clarke-Wright / K=2,3 分区代价这些运输结论，
读者却看不到任何运输侧的图。本脚本补这一块。

图中文字全部英文；配色与布局沿用中文稿，保证两稿视觉一致。

数据来源（全部为已随稿的结果文件，不新增实验）：
  Q1_前沿.json      -> fig_en_q1_pareto  (架次数 / 能耗 / 工时)
  solution.json     -> fig_en_q2_gantt   (运输架次 + 电池充电周转)
  Q4 分区文件       -> fig_en_q4_partition（若在场）

用法：DTS_FIGW=5.4 DTS_FIGDIR=figs_els python make_figs_cn_en.py
"""
from __future__ import annotations

import json
import os
import re

import numpy as np
from matplotlib.patches import Patch

import dcore as D

OUT = D.RESULTS
FIGS = D.FIGS
FIGW = float(os.environ.get("DTS_FIGW", "5.4"))


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                # noqa: BLE001
        return None


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 9.5,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    return plt


def save_fig(fig, plt, stem):
    en = os.environ.get("DTS_FIGDIR") or os.path.join(D.BASE, "paper_en", "figs")
    os.makedirs(en, exist_ok=True)
    pdf = os.path.join(FIGS, stem + ".pdf")
    try:
        fig.tight_layout()
    except Exception:                                                # noqa: BLE001
        pass
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(os.path.join(FIGS, stem + ".png"), dpi=300, bbox_inches="tight")
    import shutil
    for d in (en, os.path.join(D.BASE, "paper_en", "figs")):
        try:
            shutil.copy2(pdf, os.path.join(d, stem + ".pdf"))
        except Exception:                                            # noqa: BLE001
            pass
    plt.close(fig)
    return pdf


def fig_q1_pareto(plt):
    """Q1 Pareto frontier, with the named transport plans overlaid.

    只有前沿点（本实例 2 个）会很空、也讲不出故事；把基线与消融里的 18 个
    具名方案（贪心 / ALNS / CP-SAT 打磨等）一起画上，才能看出
    "前沿在哪、我们选的方案离前沿多远"。数字全部来自随稿结果文件。
    """
    pts = rd("Q1_前沿.json")
    if not pts:
        return None
    E = np.array([float(q["E"]) for q in pts])
    T = np.array([float(q["T"]) / 3600.0 for q in pts])
    C = np.array([int(q["count"]) for q in pts])
    fig, ax = plt.subplots(figsize=(FIGW, round(FIGW * 0.44, 2)))
    # 具名方案（灰点）：给前沿提供参照系
    rows = ((rd("基线与消融.json") or {}).get("A_transport_methods") or {}).get("rows") or []
    gx, gy = [], []
    for r in rows:
        try:
            gx.append(float(r["总能耗_kWh"]))
            gy.append(float(r["全部任务完成时间_s"]) / 3600.0)
        except (KeyError, TypeError, ValueError):
            continue
    if gx:
        ax.scatter(gx, gy, s=26, facecolors="none", edgecolors="0.55",
                   linewidths=0.9, zorder=2,
                   label="named plans (baselines and ablations, $n=%d$)" % len(gx))
    sc = ax.scatter(E, T, c=C, cmap="viridis", s=95, edgecolors="k",
                    linewidths=0.7, zorder=4, label="Pareto frontier")
    for q in pts:
        ax.annotate("%d sorties" % int(q["count"]),
                    (float(q["E"]), float(q["T"]) / 3600.0),
                    textcoords="offset points", xytext=(7, 4), fontsize=7.5)
    cb = fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.02)
    cb.set_label("Sorties", fontsize=8)
    cb.ax.tick_params(labelsize=7.5)
    ax.set_xlabel("Total transport energy (kWh)")
    ax.set_ylabel("Cumulative operation time (h)")
    ax.legend(fontsize=7.5, loc="lower right", framealpha=0.92)
    ax.grid(alpha=0.25, ls=":")
    return save_fig(fig, plt, "fig_en_q1_pareto")


def fig_q2_gantt(plt):
    """Transport sortie Gantt chart, with battery recharge turnaround hatched."""
    sol = rd("solution.json") or {}
    recs = sol.get("transport") or []
    if not recs:
        return None
    drones = []
    for r in recs:
        u = str(r.get("drone", ""))
        if u and u not in drones:
            drones.append(u)
    if not drones:
        return None
    drones.sort()
    ymap = {u: i for i, u in enumerate(drones)}
    colors = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
    fig, ax = plt.subplots(figsize=(FIGW, round(FIGW * 0.52, 2)))
    tmax = 0.0
    for r in recs:
        g = str(r.get("type", "")).upper()
        c = colors.get(g, "#7f7f7f")
        y = ymap.get(str(r.get("drone", "")))
        if y is None:
            continue
        s0, e0 = float(r.get("start", 0.0)), float(r.get("end", 0.0))
        tmax = max(tmax, e0)
        ax.broken_barh([(s0, max(1.0, e0 - s0))], (y - 0.34, 0.68),
                       facecolors=c, edgecolor="k", linewidth=0.5, alpha=0.9, zorder=3)
        chg = float(r.get("chg", 0.0) or 0.0)
        if chg > 1.0:
            ax.broken_barh([(e0, chg)], (y - 0.34, 0.68), facecolors="none",
                           edgecolor=c, hatch="////", linewidth=0.4, alpha=0.75, zorder=2)
            tmax = max(tmax, e0 + chg)
    # hard deadlines as vertical guides
    for dl, txt in ((3600, "3600 s"), (7200, "7200 s"), (10800, "10800 s")):
        if tmax > dl * 0.35:
            ax.axvline(dl, color="#c0392b", ls="--", lw=0.9, alpha=0.7)
            ax.annotate(txt, (dl, len(drones) - 0.4), fontsize=7, color="#c0392b",
                        rotation=90, va="top", ha="right")
    ax.set_yticks(range(len(drones)))
    ax.set_yticklabels(drones, fontsize=7.5)
    ax.set_ylim(-0.7, len(drones) - 0.3)
    ax.set_xlabel("Time (s, 0 = scheduling start)")
    ax.set_ylabel("Transport drone")
    used = {str(r.get("type", "")).upper() for r in recs}
    handles = [Patch(facecolor=colors[g], edgecolor="k", label="Type %s" % g)
               for g in ("A", "B", "C") if g in used]
    handles.append(Patch(facecolor="none", edgecolor="k", hatch="////",
                         label="Battery turnaround"))
    ax.legend(handles=handles, fontsize=7.5, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.14), frameon=False)
    ax.grid(axis="x", alpha=0.25, ls=":")
    return save_fig(fig, plt, "fig_en_q2_gantt")


def fig_q3_comm(plt):
    """Communication assurance over the mission: time in each link state.

    中文稿的对应图是"航迹按直连/中继/中断着色"的地图；这里改成**时间轴上的
    保障占比**，信息量相同且更适合英文单栏：数据来自结果提交.xlsx 的
    Q3_通信保障 表（236 段，逐段标注 直连/中继/其他）。

    为什么值得单列一张：全文的核心论点是"通信约束会改写运输可行性"，
    而这张图是唯一**直接**展示"哪些时段真的失联"的证据。
    """
    import pandas as pd
    x = os.path.join(OUT, "结果提交.xlsx")
    if not os.path.exists(x):
        return None
    try:
        df = pd.read_excel(x, sheet_name="Q3_通信保障")
    except Exception:                                                # noqa: BLE001
        return None
    cols = {str(c): c for c in df.columns}
    c0 = next((cols[k] for k in cols if "开始" in k), None)
    c1 = next((cols[k] for k in cols if "结束" in k), None)
    cm = next((cols[k] for k in cols if "保障方式" in k), None)
    cs = next((cols[k] for k in cols if "运输架次" in k), None)
    if None in (c0, c1, cm, cs):
        return None
    fig, ax = plt.subplots(figsize=(FIGW, round(FIGW * 0.42, 2)))
    ymap = {"direct": 0, "relay": 1, "none": 2}
    colour = {"direct": "#4c72b0", "relay": "#55a868", "none": "#c0392b"}
    label = {"direct": "direct link", "relay": "via relay", "none": "no coverage"}
    sids = []
    for _, r in df.iterrows():
        sid = str(r[cs])
        if sid not in sids:
            sids.append(sid)
    sids.sort()
    ypos = {s: i for i, s in enumerate(sids)}
    drawn = set()
    for _, r in df.iterrows():
        raw = str(r[cm]).strip()
        st = ("direct" if raw.startswith("直") else
              "relay" if raw.startswith("中继") else "none")
        y = ypos.get(str(r[cs]))
        if y is None:
            continue
        try:
            a, b = float(r[c0]), float(r[c1])
        except (TypeError, ValueError):
            continue
        if b <= a:
            continue
        ax.broken_barh([(a, b - a)], (y - 0.36, 0.72),
                       facecolors=colour[st], edgecolor="white", linewidth=0.3)
        drawn.add(st)
    ax.set_yticks(range(len(sids)))
    ax.set_yticklabels(sids, fontsize=6.5)
    ax.set_ylim(-0.7, len(sids) - 0.3)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Transport sortie")
    handles = [Patch(facecolor=colour[k], label=label[k])
               for k in ("direct", "relay", "none") if k in drawn]
    ax.legend(handles=handles, fontsize=7.5, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.20), frameon=False)
    return save_fig(fig, plt, "fig_en_q3_comm")


def main():
    os.makedirs(FIGS, exist_ok=True)
    plt = _plt()
    for fn in (fig_q1_pareto, fig_q2_gantt, fig_q3_comm):
        try:
            p = fn(plt)
        except Exception as e:                                       # noqa: BLE001
            print("  [!!] %s 失败：%s" % (fn.__name__, str(e)[:90]))
            continue
        print("  [%s] %s" % ("OK" if p else "--", os.path.basename(p) if p else fn.__name__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
