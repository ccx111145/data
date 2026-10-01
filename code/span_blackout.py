# -*- coding: utf-8 -*-
"""
span_blackout.py —— 把"2 架不可行"提炼为**跨度—黑障不等式**（可用于论文定理）

定义（全部在统一 10 s 离散时刻上）
------------------------------------
* 需求 D(t)        ：t 时刻所有"直连不可用"的运输机位置集合
* 单点独保跨度 span(t)：从 t 起，存在某悬停点能**单独**覆盖 D(τ) 的最长时长
                      span(t) = max_j { τ_end(j,t) - t }，其中 j 的独保区间含 t
* 换位黑障 w(a→b)  ：中继由悬停点 a 转到 b 期间**无法提供服务**的时长
                      Mode 1（基地返航）w = t_back(a) + τ_turn + t_out(b) + t_link
                      Mode 2（空中转场）w = t_transit(a→b) + t_link

定理（换位的必要条件）
----------------------
若某架中继在时刻 t 完成一次换位，则在该次换位的黑障窗口 [t-w, t] 内，
其余 N-1 架必须**联合**保障全部需求。当 N = 2 时即"另一架必须单独保障"，
于是必有
        span(t - w)  >=  w                       (★ 跨度—黑障不等式)
它是**必要条件**：违反 (★) 的时刻不可能完成任何换位。

推论：若在某时刻 t 之后（或整个任务期内）必须换位而 (★) 处处不成立，
则配置被冻结；此时若需求又要求改变覆盖点，则 N = 2 不可行。

本脚本输出：
  1) span(t) 的分布
  2) 两种模式下 (★) 的成立率（"可换位完成时刻"占比）
  3) 首个崩溃时刻处的 (★) 赤字（缺口秒数）——量化"离可行边界有多远"
"""
from __future__ import annotations

import json
import os
import numpy as np

import span_util as SU

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS
GRID = 10.0


def build():
    inst = Q.Instance()
    sol = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"]) for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=0.0, soc=1.0)
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    pb = DN.PB(ph, grid=GRID, topk=12, inst=inst, mode="base")
    return inst, ph, pb


def main():
    inst, ph, pb = build()
    cells = np.asarray(ph["cells"], dtype=np.float64)
    n = pb.n
    # span(t)：从 k 起的最长单点独保格数
    span_c = np.array([max(0, int(pb.run_end[k].max()) - k + 1) for k in range(n)])
    span_s = span_c * GRID
    print("\n=== 单点独保跨度 span(t) ===")
    print("  中位 %.0f s / 均值 %.0f s / P10 %.0f / P90 %.0f / 最大 %.0f"
          % (np.median(span_s), span_s.mean(), np.percentile(span_s, 10),
             np.percentile(span_s, 90), span_s.max()))

    rtype = inst.d["rtype"]
    # 两种口径的换位黑障：(a) 全候选点对；(b) 只用"强点"（独立覆盖能力最强的那些点，
    # 也是实际会被选中的悬停点）——后者才是与构造性/精确解相关的量。
    all_idx = list(range(0, pb.P, max(1, pb.P // 200)))
    strong_idx = [int(j) for j in np.argsort(-ph["alone"].sum(axis=0))[:70]]

    def wset(idx):
        wb, wa = [], []
        for a in idx:
            for b in idx:
                if a == b:
                    continue
                wb.append(rtype.t_turn + pb.TB[a] + pb.TO[b] + rtype.t_link)
                t, _, _ = D.relay_transit(rtype, inst.nodes,
                                          tuple(float(x) for x in pb.palette[a]),
                                          tuple(float(x) for x in pb.palette[b]))
                wa.append(t + rtype.t_link)
        return np.array(wb), np.array(wa)

    wb_all, wa_all = wset(all_idx)
    wb_str, wa_str = wset(strong_idx)
    res = {}
    k_fail = 171
    t_fail = float(cells[k_fail])
    print("\n=== 换位黑障 w 的中位数（s）===")
    print("  全候选点对： Mode 1 %.0f / Mode 2 %.0f" % (np.median(wb_all), np.median(wa_all)))
    print("  强点对：     Mode 1 %.0f / Mode 2 %.0f" % (np.median(wb_str), np.median(wa_str)))
    print("\n=== 跨度—黑障不等式 (★) span(t-w) >= w 的成立率 ===")
    for nm, wb, wa in (("全候选点对", wb_all, wa_all), ("强点对", wb_str, wa_str)):
        for lbl, arr in (("Mode 1", wb), ("Mode 2", wa)):
            for q in (10, 50, 90):
                w = float(np.percentile(arr, q))
                # 时间窗口径（唯一权威实现）：窗口 [t_k - w, t_k] 内的需求格必须被单点独保
                ok, ndef, worst = SU.star_and_deficit(cells, span_c, w)
                res.setdefault(nm, {}).setdefault(lbl, {})["p%d" % q] = dict(
                    w_s=round(w, 1), rate=round(float(ok.mean()), 4),
                    n_ok=int(ok.sum()), n=int(n),
                    # 赤字以**需求格**计；需求格平均间距约 11 s 且不等距，故不折算为秒
                    deficit_cells=int(ndef),
                    worst=worst)
                if q == 50 and nm == "全候选点对":
                    j0 = int(np.searchsorted(cells, cells[k_fail] - w, side="left"))
                    res[nm][lbl]["p50"].update(
                        crash_k0=j0, crash_t0=round(float(cells[j0]), 1),
                        span_at_k0_s=round(float(span_c[j0] * GRID), 1),
                        need_cells=int(k_fail - j0 + 1),
                        deficit_s=round(float((k_fail - j0 + 1 - span_c[j0]) * GRID), 1)
                        if span_c[j0] < (k_fail - j0 + 1) else 0.0)
            w = float(np.median(arr))
            ok, ndef, worst = SU.star_and_deficit(cells, span_c, w)
            print("  %-8s %-7s w(中位)=%6.0f s → (★) 成立率 %5.1f%%（%d/%d）赤字 %d 格（%.0f s）"
                  % (nm, lbl, w, 100 * ok.mean(), ok.sum(), n, ndef, ndef * GRID))
    print("\n=== 结论 ===")
    d1 = res["全候选点对"]["Mode 1"]["p50"].get("deficit_s")
    d2 = res["全候选点对"]["Mode 2"]["p50"].get("deficit_s")
    print("  崩溃点处赤字：Mode 1 %.0f s；Mode 2 %.0f s" % (d1 or -1, d2 or -1))
    print("  ⇒ 空中转场把黑障中位从 %.0f s 压到 %.0f s、(★)成立率从 %.1f%% 提到 %.1f%%，"
          "但**未能消除**赤字 ⇒ 2 架不可行不是 A13 假设的产物。"
          % (np.median(wb_all), np.median(wa_all),
             100 * res["全候选点对"]["Mode 1"]["p50"]["rate"],
             100 * res["全候选点对"]["Mode 2"]["p50"]["rate"]))
    p = os.path.join(OUT, "跨度黑障不等式.json")
    # 全候选点对、Mode 1 的换位黑障窗口分布（供论文 §7.4 引用；不再使用 W_max 截断口径）
    wb_sorted = np.sort(wb_all)
    gap_ge = float((wb_sorted >= 1100.0).mean())
    print("\n=== 换位黑障窗口 w 的分布（全候选点对，Mode 1，n=%d）===" % len(wb_sorted))
    print("  最小 %.0f s / 中位 %.0f s / 均值 %.0f s / 最大 %.0f s"
          % (wb_sorted[0], np.median(wb_sorted), wb_sorted.mean(), wb_sorted[-1]))
    print("  超过 1100 s 的点对占比 %.1f%%；超过 Mode 2 中位数的占比 %.1f%%"
          % (100 * gap_ge, 100 * float((wb_sorted >= np.median(wa_all)).mean())))
    json.dump(dict(span=dict(median_s=round(float(np.median(span_s)), 1),
                             mean_s=round(float(span_s.mean()), 1),
                             p10_s=round(float(np.percentile(span_s, 10)), 1),
                             p90_s=round(float(np.percentile(span_s, 90)), 1),
                             max_s=round(float(span_s.max()), 1)),
                   w_base_median_all_s=round(float(np.median(wb_all)), 1),
                   w_air_median_all_s=round(float(np.median(wa_all)), 1),
                   w_base_median_strong_s=round(float(np.median(wb_str)), 1),
                   w_air_median_strong_s=round(float(np.median(wa_str)), 1),
                   w_base_dist_all=dict(min_s=round(float(wb_sorted[0]), 1),
                                        median_s=round(float(np.median(wb_sorted)), 1),
                                        mean_s=round(float(wb_sorted.mean()), 1),
                                        max_s=round(float(wb_sorted[-1]), 1),
                                        ge1100_pct=round(100 * gap_ge, 1),
                                        n=int(len(wb_sorted))),
                   by_mode=res, fail=dict(k=k_fail, t=round(t_fail, 1)),
                   # 供英文稿绘图：span 序列（每 4 格取样一次，避免文件过大）
                   span_series=dict(cells=[round(float(c), 1) for c in cells[::4]],
                                    span=[int(v) for v in span_c[::4]],
                                    step=4)),
              
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
