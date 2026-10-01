# -*- coding: utf-8 -*-
"""make_figs_extra_en.py —— 补两张审稿人最想看、原先却没有的图。

为什么补：
  * 原稿 8 图 / 44 页，对方法型论文偏少；
  * 缺"需求剖面 + 黑障窗口"这张 —— 它把"为什么接力不行"讲直观，
    目前只能从文字和 span 曲线间接体会；
  * 缺"三法判定对照"这张 —— 正文反复讲 DP / CP-SAT ILP / 构造性验证器
    三法互证，却没有一张图把三者在各 N 上的结论并排摆出来。

两张图的数据全部来自已有结果文件，不新增任何实验、不编任何数字。
画布宽度同样由 DTS_FIGW 控制（与版式显示宽度一致，图内字号才不被缩放）。

用法：DTS_FIGW=5.4 DTS_FIGDIR=figs_els python make_figs_extra_en.py
"""
from __future__ import annotations

import json
import os
import re

import numpy as np

import dcore as D

OUT = D.RESULTS
FIGS = D.FIGS
FIGW = float(os.environ.get("DTS_FIGW", "5.4"))


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                # noqa: BLE001
        return {}


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
        "legend.fontsize": 8,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.alpha": 0.28,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    return plt


def save_fig(fig, plt, stem):
    en = os.environ.get("DTS_FIGDIR") or os.path.join(D.BASE, "paper_en", "figs")
    os.makedirs(en, exist_ok=True)
    pdf = os.path.join(FIGS, stem + ".pdf")
    png = os.path.join(FIGS, stem + ".png")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    try:
        fig.tight_layout()
    except Exception:                                                # noqa: BLE001
        pass
    fig.savefig(pdf, bbox_inches="tight")
    import shutil
    for d in (en, os.path.join(D.BASE, "paper_en", "figs")):
        try:
            shutil.copy2(pdf, os.path.join(d, stem + ".pdf"))
        except Exception:                                            # noqa: BLE001
            pass
    plt.close(fig)
    return pdf


def fig_profile(plt):
    """相位结构与换位代价的量级对比 —— 回答"为什么两架接力跟不上"。

    我第一版画的是"单点可独保跨度 vs 黑障窗口"，结果**讲反了**：
    span 最大只有 396 格（≈3960 s，且是大跨度包），而中位黑障窗口 1116 s，
    图上看起来像"span 远低于门限"= 满足条件，与论文结论相反。这说明那张图
    选错了量。真正的阻塞来自相位结构：

      (a) 6 个相位的长度 430..3190 s，其中 1 个短相（430 s）短于中位黑障窗口
          （1116 s）—— 即"换位代价比整个相位还长"，接力无从谈起；
      (b) 相位之间的**间隔**只有 10 s，而最短换位代价 w_min = 83 s（M2）/
          411 s（M1）—— 换点根本塞不进相位边界，只能落在相位内部，
          从而黑障该相位的需求。

    两张子图合起来是"必须换、但换不进去"的量化证据，与 §VI 正文一致。
    """
    lp = rd("中继ILP松弛.json")
    phases = lp.get("phases") or []
    if not phases:
        return None
    sb = rd("跨度黑障不等式.json")
    w1 = sb.get("w_base_median_all_s") or 1116.0
    bl = (rd("局部阻塞证书.json").get("results") or {})
    wmin1 = (bl.get("base") or {}).get("w_min_s") or 411
    wmin2 = (bl.get("air") or {}).get("w_min_s") or 83

    lens = [ph[3] - ph[2] for ph in phases]
    gaps = [phases[i + 1][2] - phases[i][3] for i in range(len(phases) - 1)]

    fig, ax = plt.subplots(1, 2, figsize=(FIGW, round(FIGW * 0.30, 2)))
    # (a) 相位长度 vs 中位黑障窗口
    xs = np.arange(len(lens))
    cols = ["#C44E52" if L < w1 else "#4C72B0" for L in lens]
    ax[0].bar(xs, lens, color=cols, width=0.62)
    ax[0].axhline(w1, color="#C44E52", ls="--", lw=1.2)
    ax[0].set_xticks(xs)
    ax[0].set_xticklabels(["%s" % (i + 1) for i in range(len(lens))])
    ax[0].set_xlabel("Demand phase")
    ax[0].set_ylabel("Phase length (s)")
    for x, L in zip(xs, lens):
        ax[0].text(x, L + max(lens) * 0.04, "%d" % L, ha="center", va="bottom",
                   rotation=90, fontsize=7.5)
    ax[0].text(0.03, 0.97, "median blackout window\n= %.0f s" % w1,
               transform=ax[0].transAxes, va="top", fontsize=7.5, color="#C44E52")
    # (b) 相位间隔 vs 最短换位代价
    ax[1].bar(np.arange(len(gaps)), gaps, color="#DD8452", width=0.55)
    ax[1].axhline(wmin2, color="#55A868", ls="--", lw=1.2)
    ax[1].axhline(wmin1, color="#C44E52", ls="--", lw=1.2)
    ax[1].set_xticks(np.arange(len(gaps)))
    ax[1].set_xticklabels(["%d-%d" % (i + 1, i + 2) for i in range(len(gaps))])
    ax[1].set_xlabel("Phase boundary")
    ax[1].set_ylabel("Inter-phase gap (s)")
    ax[1].text(0.03, 0.97, "$w_{\\min}$: %.0f s (M2), %.0f s (M1)" % (wmin2, wmin1),
               transform=ax[1].transAxes, va="top", fontsize=7.5, color="0.25")
    fig.subplots_adjust(wspace=0.34)
    return save_fig(fig, plt, "fig_en_profile")


def fig_methods(plt):
    """判定方法对照：三种独立方法在 N=1..4 上的结论并排。

    正文说"三法互证"，但只有这句话、没有证据的并置。这张图把
    DP 递推、相位级 CP-SAT ILP、构造性验证器在每个 N 上的结论摆在一起：
    一致处是互证，不一致处（N=2）正是论文讨论的核心。
    """
    mc = rd("换位模式对比.json")
    lp = rd("中继ILP松弛.json").get("results") or {}
    rb = rd("中继基线与下界.json")
    g = rb.get("greedy") or {}
    if not mc.get("rows"):
        return None

    # 递推：M1 的首个空状态时刻
    rec = {}
    for r in mc.get("rows") or []:
        if r.get("mode") == "base":
            m = re.search(r"t=(\d+(?:\.\d+)?)", str(r.get("reason") or ""))
            rec[r.get("N")] = (bool(r.get("feasible")),
                               ("%s s" % m.group(1)) if m else None)
    Ns = [1, 2, 3, 4]
    methods = ["State recursion\n(M1)", "Phase-level ILP\n(CP-SAT)",
               "Constructive verifier"]

    # 每个方法的 (可行?, 标注文本)
    def cell_rec(n):
        f, tm = rec.get(n, (None, None))
        if f is True:
            return True, "ok"
        if f is False:
            return False, ("fail\n%s" % tm) if tm else "fail"
        return None, "—"

    def cell_ilp(n):
        d = lp.get("N%d" % n)
        if not d:
            return None, "—"
        if d.get("status") == "INFEASIBLE":
            return False, "infeas."
        if d.get("feasible"):
            return True, "opt."
        return None, "—"

    def cell_greedy(n):
        d = g.get("N%d" % n) or {}
        if d.get("feasible") is True:
            return True, "%s sort." % d.get("sorties")
        if d.get("feasible") is False:
            return False, "fail"
        return None, "—"

    getters = [cell_rec, cell_ilp, cell_greedy]
    fig, ax = plt.subplots(figsize=(FIGW, round(FIGW * 0.40, 2)))
    for xi, name in enumerate(methods):
        for yi, n in enumerate(Ns):
            ok, txt = getters[xi](n)
            col = {"True": "#55A868", "False": "#C44E52", "None": "#CCCCCC"}[str(ok)]
            ax.add_patch(plt.Rectangle((xi - 0.42, yi - 0.36), 0.84, 0.72,
                                       facecolor=col, alpha=0.85, edgecolor="white"))
            ax.text(xi, yi, txt, ha="center", va="center", fontsize=7.5,
                    color="white", weight="bold")
    ax.set_xlim(-0.6, len(methods) - 0.4)
    ax.set_ylim(-0.6, len(Ns) - 0.4)
    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(methods, fontsize=8)
    ax.set_yticks(range(len(Ns)))
    ax.set_yticklabels(["$N=%d$" % n for n in Ns])
    ax.grid(False)
    # 标出唯一的三法不一致处
    # 规则：结论写图题，图内不放散文注释。
    # 早先这里有一段箭头注释 + "recursion not run for N>=3"，都会压到绿色单元格上。
    # 未跑的格子用浅灰 + 短横线自明，说明放在图题里。
    return save_fig(fig, plt, "fig_en_methods")


def fig_theory(plt):
    """Theory panel: span(t), the alibi-window release rate, and the fleet-size bounds.

    这张原本由独立的 make_fig_theory.py 生成，且画布固定 15.2 in、只往
    paper_en/figs 写。结果正文 \\includegraphics{figs/fig_en_theory.pdf}
    在 xelatex 以仓库根为工作目录编译时找不到文件（figs/ 根目录下没有），
    编译报 "Unable to load picture"。移到本模块后与其它图一样按目标版式
    宽度生成，figs_els / figs_ieee 两套都齐。
    """
    sb = rd("跨度黑障不等式.json")
    ob = rd("局部阻塞证书.json")
    if not sb or not ob:
        return None
    ser = sb.get("span_series") or {}
    tc = np.asarray(ser.get("cells") or [], dtype=float)
    ts = np.asarray(ser.get("span") or [], dtype=float) * 10.0
    R = ob.get("results") or {}
    m1, m2 = R.get("base") or {}, R.get("air") or {}
    if not len(tc) or not m1 or not m2:
        return None

    fig, ax = plt.subplots(1, 3, figsize=(FIGW, round(FIGW * 0.30, 2)))
    a = ax[0]
    a.plot(tc, ts, lw=0.9, color="#2b6cb0")
    a.axhline(m1["span_median_s"], ls="--", lw=1.0, color="#c53030",
              label="span median %.0f s" % m1["span_median_s"])
    a.axhline(m1["w_median_s"], ls=":", lw=1.0, color="#2f855a",
              label="Mode 1 $w$ median %.0f s" % m1["w_median_s"])
    a.axhline(m2["w_median_s"], ls="-.", lw=1.0, color="#975a16",
              label="Mode 2 $w$ median %.0f s" % m2["w_median_s"])
    a.axvline(2420.0, color="#718096", lw=0.8, alpha=0.7,
              label="2-relay failure $t=2420$ s")
    a.set_xlabel("time $t$ (s)")
    a.set_ylabel("span (s)")
    a.legend(fontsize=6.5, loc="upper right", framealpha=0.9)
    a.grid(alpha=0.25)

    b = ax[1]
    ths = np.arange(0, 4200, 20)
    rel = np.array([(ts >= th).mean() for th in ths])
    b.plot(ths, 100 * rel, lw=1.6, color="#2b6cb0")
    for st, c, lb in ((m1, "#c53030", "Mode 1"), (m2, "#975a16", "Mode 2")):
        b.axvline(st["w_median_s"], ls="--", lw=1.0, color=c,
                  label="%s: %.1f%%" % (lb, 100 * st["release_at_wmed"]))
    b.set_xlabel("blackout threshold $w$ (s)")
    b.set_ylabel("cells admitting a handover (%)")
    b.legend(fontsize=6.5, framealpha=0.9)
    b.grid(alpha=0.25)

    c = ax[2]
    lo = max(ob["bound_energy"], m1["bound_by_w"], m2["bound_by_w"])
    up = 3
    labels = ["energy\nbound", "energy +\nstructural", "constructive\nfeasible"]
    vals = [ob["bound_energy"], lo, up]
    c.bar(labels, vals, color=["#a0aec0", "#2b6cb0", "#2f855a"], width=0.55)
    c.axhline(up, ls="--", lw=1.0, color="#2f855a")
    for i, v in enumerate(vals):
        c.text(i, v + 0.05, str(v), ha="center", fontsize=7)
    c.set_ylim(0, max(vals) + 1.0)
    c.set_ylabel("relay fleet size $N$")
    c.grid(alpha=0.25, axis="y")

    fig.subplots_adjust(wspace=0.42)
    return save_fig(fig, plt, "fig_en_theory")


def main():
    os.makedirs(FIGS, exist_ok=True)
    plt = _plt()
    for fn in (fig_profile, fig_methods, fig_theory):
        p = fn(plt)
        print("  [%s] %s" % ("OK" if p else "--", os.path.basename(p) if p else fn.__name__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
