# -*- coding: utf-8 -*-
"""
recompute_relay.py —— 物理修正后的中继侧全面重算

触发原因：`dcore.relay_flight` 原先存在"负下降高度"缺陷（巡航海拔未考虑悬停海拔本身），
已修正为 cruise = max(沿线地形+50, O01地面+50, 悬停海拔)。
本脚本在**修正后的物理**下重算中继侧全部结论：
  1) 换位黑障窗口 w 的分布（Mode 1 / Mode 2，逐点对精确、不截断）
  2) 跨度—黑障不等式 (★) 的成立率
  3) 构造性判定（贪心）：N=2/3 × Mode 1/2
  4) 精确 DP（可选 exact 模式：候选集完备 + 无状态剪枝）
输出 results/重算_物理修正后.json，并把关键结论打印出来。
"""
from __future__ import annotations

import argparse
import json
import os
import time
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


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
    return inst, sol, ph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exact", action="store_true", help="追加精确 DP 尝试（完备候选集 + 无剪枝）")
    ap.add_argument("--exact-cap", type=int, default=400000, help="精确模式下允许的状态上限，超过即中止")
    a = ap.parse_args()
    t0 = time.time()
    inst, sol, ph = build()
    rtype = inst.d["rtype"]
    cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
    res = dict(hover_cap_s=round(cap, 1), note="dcore.relay_flight 负下降高度修正后重算")
    print("覆盖矩阵完成 %.0f s；单次在空上限 %.0f s" % (time.time() - t0, cap))

    # ---- 1) 黑障窗口 ----
    pb_b = DN.PB(ph, grid=10.0, topk=12, inst=inst, mode="base")
    pb_a = DN.PB(ph, grid=10.0, topk=12, inst=inst, mode="air")
    idx = list(range(0, pb_b.P, max(1, pb_b.P // 120)))
    wb = np.array([pb_b.w_sec(x, y) for x in idx for y in idx if x != y])
    wa = np.array([pb_a.w_sec(x, y) for x in idx for y in idx if x != y])
    res["blackout"] = dict(base_med=round(float(np.median(wb)), 1),
                           base_p10=round(float(np.percentile(wb, 10)), 1),
                           base_p90=round(float(np.percentile(wb, 90)), 1),
                           base_max=round(float(wb.max()), 1),
                           air_med=round(float(np.median(wa)), 1),
                           air_p10=round(float(np.percentile(wa, 10)), 1),
                           air_p90=round(float(np.percentile(wa, 90)), 1),
                           air_max=round(float(wa.max()), 1))
    print("黑障(修正后) Mode1 中位 %.0f s P90 %.0f 最大 %.0f | Mode2 中位 %.0f s P90 %.0f 最大 %.0f"
          % (np.median(wb), np.percentile(wb, 90), wb.max(),
             np.median(wa), np.percentile(wa, 90), wa.max()))

    # ---- 2) 跨度—黑障不等式（时间窗口径，见 span_util.py） ----
    import span_util as SU
    cells_t = np.asarray(ph["cells"], dtype=np.float64)
    # span 必须由「同一点连续可独保」给出（不能用 run_end 的逐格最大值再取 max，
    # 那隐含允许逐格换点）。这里直接用 pb.mask 构造 (格 × 点) 的独保矩阵。
    ok_mat = np.zeros((pb_b.n, pb_b.P), dtype=bool)
    for k in range(pb_b.n):
        nd = pb_b.need[k]
        ok_mat[k] = [(int(pb_b.mask[k][j]) & nd) == nd for j in range(pb_b.P)]
    span_c = SU.span_cells(ok_mat)

    def star_rate(ws):
        ok, ndef, worst = SU.star_and_deficit(cells_t, span_c, ws)
        return float(ok.mean()), int(ok.sum()), int(ndef), worst

    rb, nb_, db, _wb = star_rate(float(np.median(wb)))
    ra, na_, da, _wa = star_rate(float(np.median(wa)))
    res["star"] = dict(base_rate=round(rb, 4), base_ok=nb_, base_deficit_cells=db,
                       air_rate=round(ra, 4), air_ok=na_, air_deficit_cells=da,
                       n_cells=int(pb_b.n),
                       span_med_cells=int(np.median(span_c)),
                       span_p90_cells=int(np.percentile(span_c, 90)))
    print("(★) 成立率(修正后，时间窗)：Mode1 %.1f%% (%d/%d) 赤字 %d 格 | Mode2 %.1f%% (%d/%d) 赤字 %d 格"
          % (100 * rb, nb_, pb_b.n, db, 100 * ra, na_, pb_b.n, da))

    # ---- 3) 构造性贪心 ----
    import greedy_relay as GR
    res["greedy"] = {}
    for N in (2, 3):
        for mode in ("base", "air"):
            t1 = time.time()
            try:
                g = GR.greedy(inst, ph, N=N, mode=mode, cap_s=cap, topk=400, verbose=False)
                rec = dict(ok=bool(g["ok"]), reached=int(g["reached_cell"]), n=int(g["n_cells"]),
                           actions=int(g["n_actions"]),
                           fail=(None if g["ok"] else dict(k=g["fail"][0], t=g["fail"][1],
                                                           reason=g["fail"][2])),
                           sec=round(time.time() - t1, 1))
                if g["ok"]:
                    ss = GR.actions_to_sorties(inst, ph, g["actions"], N, mode)
                    bad = DN.check_timing(inst, ss, mode=mode)
                    v = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                                  lon=s["lon"], lat=s["lat"],
                                                  hover_alt=s["hover_alt"]) for s in ss],
                                  link=ph.get("link"))
                    rec.update(sorties=len(ss), timing=len(bad), miss=int(v["miss"]),
                               energy=round(float(sum(s["e_total"] for s in ss)), 3),
                               soc_min=round(100 * min(s["soc"] for s in ss), 1))
            except Exception as e:
                rec = dict(ok=False, error=str(e))
            res["greedy"]["N%d_%s" % (N, mode)] = rec
            print("  贪心 N=%d %-4s -> %s" % (N, mode,
                  ("可行 架次=%d 冲突=%d 未覆盖=%d/%d 能耗=%.2f SOCmin=%.1f%%"
                   % (rec.get("sorties", -1), rec.get("timing", -1), rec.get("miss", -1),
                      rec.get("n", -1), rec.get("energy", -1), rec.get("soc_min", -1)))
                  if rec.get("ok") else
                  ("不可行：%s" % (rec.get("fail") or rec.get("error")))))

    # ---- 4) 精确 DP ----
    if a.exact:
        res["exact_dp"] = {}
        for N, mode in ((2, "base"), (2, "air")):
            t1 = time.time()
            try:
                seq, cost, pb, diag = DN.solve(ph, N=N, topk=0, exact=True, inst=inst,
                                               verbose=True, max_hover_s=cap, mode=mode,
                                               max_states=a.exact_cap)
                ok = seq is not None
                res["exact_dp"]["N%d_%s" % (N, mode)] = dict(
                    feasible=ok, reason=(None if ok else str(cost)),
                    sec=round(time.time() - t1, 1))
                print("  精确 DP N=%d %-4s -> %s (%.0f s)"
                      % (N, mode, "可行" if ok else ("不可行:" + str(cost)), time.time() - t1))
            except MemoryError:
                res["exact_dp"]["N%d_%s" % (N, mode)] = dict(feasible=None, reason="状态爆炸",
                                                              sec=round(time.time() - t1, 1))
                print("  精确 DP N=%d %-4s -> 状态爆炸（%.0f s）" % (N, mode, time.time() - t1))

    p = os.path.join(OUT, "重算_物理修正后.json")
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s\n总耗时 %.0f s" % (p, time.time() - t0))


if __name__ == "__main__":
    main()
