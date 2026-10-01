# -*- coding: utf-8 -*-
"""
fail_diag.py —— 定位状态 DP 的**阻塞原因**：把"不可行"从经验结论推进到机理结论

对给定 (N, mode, topk) 运行 DP；失败时打印该格的拒绝计数器：
  cand_empty       候选点位为空（没有任何点能补足剩余需求）
  rej_old_arrival  被换的那架尚未到位足够久（换位离站早于其到位）
  rej_other_arrival其余各架尚未到位足够久
  rej_union        黑障窗口内其余各架**无法联合覆盖**全部需求  ← 一般就是这一项
  rej_age          在空/驻留超时
  accepted         通过全部条件的转移数（若为 0 则 dp 为空）
"""
from __future__ import annotations

import argparse
import json
import os
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=2)
    ap.add_argument("--mode", default="base")
    ap.add_argument("--topk", type=int, default=40)
    ap.add_argument("--perkey", type=int, default=3)
    ap.add_argument("--slack", type=int, default=8)
    a = ap.parse_args()
    inst = Q.Instance()
    sol = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {x: list(r["boxes"][x]) for x in areas}
        offs = {x: float(r["deliver"][b]) - float(r["start"]) for x in areas for b in r["boxes"][x]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=0.0, soc=1.0)
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=False,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    cap = ((1 - inst.d["rtype"].rho) * inst.d["rtype"].e_use - 0.35) \
        / (inst.d["rtype"].p_hover + inst.d["rtype"].p_comm) * 3600.0
    seq, cost, pb, diag = DN.solve(ph, N=a.N, topk=a.topk, keep_slack=a.slack,
                                   max_states=200000, inst=inst, verbose=False,
                                   max_hover_s=cap, mode=a.mode, per_key=a.perkey)
    print("=" * 78)
    print("N=%d  mode=%s  topk=%d  per_key=%d  keep_slack=%d" % (a.N, a.mode, a.topk, a.perkey, a.slack))
    print("=" * 78)
    if seq is None:
        print("结论：**不可行** —— %s" % cost)
        if diag:
            print("\n阻塞格诊断（该格 k=%d, t=%.0f s）：" % (diag["k"], diag["t"]))
            print("  进入该格前的 DP 状态数 : %d" % diag["n_state"])
            for kk in ("cand_empty", "rej_old_arrival", "rej_other_arrival",
                       "rej_union", "rej_age", "rej_pnew_eq", "accepted"):
                print("  %-18s : %d" % (kk, diag[kk]))
            tot = sum(diag[x] for x in ("cand_empty", "rej_old_arrival", "rej_other_arrival",
                                        "rej_union", "rej_age"))
            if tot:
                main_rej = max(("cand_empty", "rej_old_arrival", "rej_other_arrival",
                                "rej_union", "rej_age"), key=lambda x: diag[x])
                print("\n  主导阻塞原因：**%s**（占 %.1f%%）"
                      % (main_rej, 100 * diag[main_rej] / tot))
                kk = diag["k"]
                cells = np.asarray(ph["cells"], dtype=float)
                if main_rej == "rej_union":
                    w = 104 if a.mode == "base" else 47
                    k0 = max(0, kk - w)
                    print("  ⇒ 黑障窗口 [k=%d, %d]（t=%.0f–%.0f s，%d 格）内，"
                          "无法由其余 %d 架联合覆盖全部需求。"
                          % (k0, kk, cells[k0], cells[kk], kk - k0 + 1, a.N - 1))
    else:
        ss = DN.to_sorties(inst, seq, pb, N=a.N, mode=a.mode)
        bad = DN.check_timing(inst, ss, mode=a.mode)
        v = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                      lon=s["lon"], lat=s["lat"], hover_alt=s["hover_alt"])
                                 for s in ss], link=ph["link"])
        print("结论：**可行** —— 架次 %d，时序冲突 %d，未覆盖 %d/%d，能耗 %.3f kWh，SOC 最低 %.1f%%"
              % (len(ss), len(bad), v["miss"], v["n"],
                 sum(s["e_total"] for s in ss), 100 * min(s["soc"] for s in ss)))
    out = dict(N=a.N, mode=a.mode, topk=a.topk, per_key=a.perkey, feasible=(seq is not None),
               reason=cost if seq is None else None, diag=diag)
    p = os.path.join(OUT, "DP阻塞诊断_N%d_%s_topk%d.json" % (a.N, a.mode, a.topk))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
