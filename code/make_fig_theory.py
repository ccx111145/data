# -*- coding: utf-8 -*-
"""
make_fig_theory.py —— 理论图：span（单点独保时长）时间序列 + alibi 释放/赤字 + 机队规模区间

数据来源：results/局部阻塞证书.json + results/跨度黑障不等式.json
产出：
  figs/fig_theory_span.png        中文版
  paper_en/figs/fig_en_theory.png 英文版
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import dcore as D

CN = D.FIGS
EN = os.path.join(D.BASE, "paper_en", "figs")
os.makedirs(EN, exist_ok=True)


def _load(name):
    p = os.path.join(D.RESULTS, name)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def _cjk():
    for f in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"):
        try:
            matplotlib.font_manager.findfont(f, fallback_to_default=False)
            matplotlib.rcParams["font.sans-serif"] = [f]
            break
        except Exception:
            continue
    matplotlib.rcParams["axes.unicode_minus"] = False


def plot(lang="en"):
    ob = _load("局部阻塞证书.json")
    sb = _load("跨度黑障不等式.json")
    if ob is None or sb is None:
        raise SystemExit("缺少结果文件，请先运行 obstruction.py 与 span_blackout.py")
    if lang == "cn":
        _cjk()
    # 字号按**最终排版宽度**定：3 联图在双栏里只有约 8.8 cm 宽，
    # 8 pt 缩完不足 6 pt。统一提到 11/12.5。
    matplotlib.rcParams.update({
        "font.size": 11,
        "axes.titlesize": 12.5,
        "axes.labelsize": 11.5,
        "xtick.labelsize": 10.5,
        "ytick.labelsize": 10.5,
        "legend.fontsize": 10.5,
        "savefig.dpi": 300,
    })

    ser = sb["span_series"]
    tc = np.asarray(ser["cells"], dtype=float)
    ts = np.asarray(ser["span"], dtype=float) * 10.0
    R = ob["results"]
    m1, m2 = R["base"], R["air"]

    fig, ax = plt.subplots(1, 3, figsize=(15.2, 4.1))

    # --- (a) span 时间序列 ---
    a = ax[0]
    a.plot(tc, ts, lw=0.9, color="#2b6cb0")
    a.axhline(m1["span_median_s"], ls="--", lw=1.0, color="#c53030",
              label=(u"span 中位 %.0f s" % m1["span_median_s"]) if lang == "cn"
              else ("span median %.0f s" % m1["span_median_s"]))
    a.axhline(m1["w_median_s"], ls=":", lw=1.0, color="#2f855a",
              label=(u"Mode 1 w 中位 %.0f s" % m1["w_median_s"]) if lang == "cn"
              else ("Mode 1 $w$ median %.0f s" % m1["w_median_s"]))
    a.axhline(m2["w_median_s"], ls="-.", lw=1.0, color="#975a16",
              label=(u"Mode 2 w 中位 %.0f s" % m2["w_median_s"]) if lang == "cn"
              else ("Mode 2 $w$ median %.0f s" % m2["w_median_s"]))
    a.axvline(2420.0, color="#718096", lw=0.8, alpha=0.7,
              label=(u"2 架 DP 崩溃格 t=2420 s") if lang == "cn"
              else ("2-relay DP failure $t=2420$ s"))
    a.set_xlabel(u"时刻 t (s)" if lang == "cn" else "time $t$ (s)")
    a.set_ylabel(u"span (s)" if lang == "cn" else "span (s)")
    a.set_title(u"(a) 单点独保时长 span(t)" if lang == "cn"
                else "(a) Solo-coverage span $\\mathrm{span}(t)$")
    a.legend(fontsize=10.5, loc="upper right")
    a.grid(alpha=0.25)

    # --- (b) 放行率 vs 阈值 ---
    b = ax[1]
    ths = np.arange(0, 4200, 20)
    rel = np.array([(ts >= th).mean() for th in ths])
    b.plot(ths, 100 * rel, lw=1.6, color="#2b6cb0")
    for st, c, lb in ((m1, "#c53030", "Mode 1"), (m2, "#975a16", "Mode 2")):
        b.axvline(st["w_median_s"], ls="--", lw=1.0, color=c,
                  label=(u"%s: w 中位 %.0f s → %.1f%%" % (lb, st["w_median_s"],
                                                         100 * st["release_at_wmed"]))
                  if lang == "cn" else
                  (u"%s: $w$ median %.0f s → %.1f%%" % (lb, st["w_median_s"],
                                                         100 * st["release_at_wmed"])))
    b.set_xlabel(u"黑障窗口阈值 w (s)" if lang == "cn" else "blackout threshold $w$ (s)")
    b.set_ylabel(u"可换位格占比 (%)" if lang == "cn" else "cells admitting a handover (%)")
    b.set_title(u"(b) alibi 窗口放行率" if lang == "cn"
                else "(b) Alibi-window release rate")
    b.legend(fontsize=10.5)
    b.grid(alpha=0.25)

    # --- (c) 机队规模下界 vs 构造性上界 ---
    c = ax[2]
    lo = max(ob["bound_energy"], m1["bound_by_w"], m2["bound_by_w"])
    up = 3
    labels = ([u"能量下界", u"能量+结构下界", u"构造性可行"]
              if lang == "cn" else
              ["energy bound", "energy + structural", "constructive feasible"])
    vals = [ob["bound_energy"], lo, up]
    cols = ["#a0aec0", "#2b6cb0", "#2f855a"]
    c.bar(labels, vals, color=cols, width=0.55)
    c.axhline(up, ls="--", lw=1.0, color="#2f855a")
    for i, v in enumerate(vals):
        c.text(i, v + 0.05, str(v), ha="center", fontsize=10.5)
    c.set_ylim(0, max(vals) + 1.0)
    c.set_ylabel(u"中继架数 N" if lang == "cn" else "relay fleet size $N$")
    c.set_title(u"(c) 机队规模的界" if lang == "cn"
                else "(c) Bounds on the fleet size")
    c.grid(alpha=0.25, axis="y")

    fig.tight_layout()
    # 英文版额外写矢量 PDF：双栏排版里 3 联图会被缩到约 8.8 cm 宽，
    # 只有矢量输出 + 放大后的字号才能在 100% 缩放下保持锐利。
    # 中文版仍只写 PNG（供国赛答卷，不改动既有交付物）。
    if lang == "cn":
        out = os.path.join(CN, "fig_theory_span.png")
        fig.savefig(out, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print("已写出：%s" % out)
    else:
        out = os.path.join(EN, "fig_en_theory.png")
        fig.savefig(out, dpi=300, bbox_inches="tight")
        fig.savefig(os.path.join(EN, "fig_en_theory.pdf"), bbox_inches="tight")
        plt.close(fig)
        print("已写出：%s（含矢量 PDF）" % out)
    return dict(bound_energy=ob["bound_energy"], bound_structural=lo, upper=up,
                release_mode1=round(100 * m1["release_at_wmed"], 1),
                release_mode2=round(100 * m2["release_at_wmed"], 1),
                span_median=m1["span_median_s"], span_max=m1["span_max_s"])


if __name__ == "__main__":
    r = plot("cn")
    r = plot("en")
    print(json.dumps(r, ensure_ascii=False))
