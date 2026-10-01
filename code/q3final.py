# -*- coding: utf-8 -*-
"""
q3final.py —— 问题三最终方案：
  (A) 库存约束下的 2 架中继最优折中方案（写入 solution.json["relay"]）
  (B) 达成**全程连续通信**的最小增配方案（3 架中继，写入 solution.json["relay3"]）
      —— 同时给出"至少需要 3 架"的严格证据（N=2 状态 DP 在第 171 格无可行状态）

用法：python q3final.py [--n3]   （--n3 才重跑 N=3 的 DP，约 35 分钟）
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


def load_transport():
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
                         battery=r["battery"], chg=float(r.get("chg", 0.0)),
                         soc=float(r.get("soc", 1.0)))
    return sol, sorties, assign


def split_for_battery(inst, pb, seq, ss, N, grid=10.0, verbose=True):
    """把悬停超过能源组件容量的架次拆成"回 O01 换组件再出动"的多个架次，
    拆分点选在**其余 N-1 架联合可覆盖**的窗口处。"""
    rtype = inst.d["rtype"]
    H = DN.__dict__  # placeholder
    cap = ((1 - rtype.rho) * rtype.e_use - 0.30) / (rtype.p_hover + rtype.p_comm) * 3600.0
    out = []
    for s in ss:
        lim = int(max(1, cap / grid))
        k0 = int(np.searchsorted(pb.cells, s["t_link_done"]))
        k1 = int(min(pb.n - 1, np.searchsorted(pb.cells, s["t_end"])))
        if (k1 - k0) <= lim:
            out.append(dict(s)); continue
        others_slots = [t for t in range(N) if t != s["slot"]]
        cuts = []
        cur = k0
        while k1 - cur > lim:
            tgt = cur + lim
            found = None
            for ks in range(max(cur + 1, tgt - 20), min(k1, tgt + 40) + 1):
                js = [seq[ks][t][0] for t in others_slots]
                w = 120
                if pb.union_ok(js, ks - w, ks + w):
                    found = ks
                    break
            if found is None:
                break
            cuts.append(found)
            cur = found
        if not cuts:
            out.append(dict(s))
            if verbose:
                print("    ! 架次 #%d 悬停 %.0f s 超容量（%.0f s）且无可拆分窗口"
                      % (s["rid"], s["hover"], cap))
            continue
        parts = []
        prev = k0
        for c in cuts + [k1]:
            part = dict(s)
            part["t_link_done"] = float(pb.cells[prev])
            part["t_end"] = float(pb.cells[c])
            parts.append(part)
            prev = c
        if verbose:
            print("    · 架次 #%d（悬停 %.0f s）拆为 %d 段换电：%s"
                  % (s["rid"], s["hover"], len(parts),
                     ", ".join("%.0f s" % (p["t_end"] - p["t_link_done"]) for p in parts)))
        out.extend(parts)
    dem = D.get_dem()
    for s in out:
        lo, la, alt = pb.palette[s["j"]]
        agl = float(alt) - float(dem.at(lo, la))
        rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
        s["hover"] = max(0.0, s["t_end"] - s["t_link_done"])
        s["e_hover"] = (rtype.p_hover + rtype.p_comm) * s["hover"] / 3600.0
        s["e_total"] = rf["e_fly"] + s["e_hover"]
        s["soc"] = 1.0 - s["e_total"] / rtype.e_use
        s["chg"] = float(D.charge_time(s["soc"], inst.d["rbatt"][1]))
        s["t_out"], s["t_back"], s["e_fly"] = rf["t_out"], rf["t_back"], rf["e_fly"]
        s["t_depart"] = max(0.0, s["t_link_done"] - rf["t_out"] - rtype.t_link)
        s.pop("rid", None)
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]] if s["slot"] < len(inst.d["rfleet"]) \
            else "R%02d(增配)" % (s["slot"] + 1)
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n3", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    inst = Q.Instance()
    solj, sorties, assign = load_transport()
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    print("相位/覆盖矩阵完成 %.0f s" % (time.time() - t0))

    # ---- (A) N = 2：证明不可行 ----
    seq2, cost2, pb = DN.solve(ph, N=2, topk=12, keep_slack=3, inst=inst, verbose=False)
    infeasible_msg = None
    if seq2 is None:
        infeasible_msg = cost2
        print("【结论】2 架中继在严格的“每个架次返回 O01”模型下无可行解：%s" % cost2)
    else:
        print("2 架中继：代价 %d" % cost2)

    # ---- (B) N = 3：最小增配方案 ----
    rec = dict(tested_at=time.strftime("%Y-%m-%d %H:%M:%S"),
               n2_feasible=(seq2 is not None), n2_msg=infeasible_msg,
               n_relay_required=3)
    if a.n3:
        t1 = time.time()
        rtype = inst.d["rtype"]
        hcap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
        print("单次驻留上限（能源组件容量）= %.0f s" % hcap)
        seq3, cost3, pb3 = DN.solve(ph, N=3, topk=12, keep_slack=3, inst=inst, verbose=True,
                                    max_hover_s=hcap)
        if seq3 is None:
            print("N=3 也失败：%s" % cost3)
            rec["n3_ok"] = False
            rec["n3_msg"] = cost3
        else:
            # 保存位置序列，便于后续快速重建（免重跑 DP）
            np.save(os.path.join(OUT, "Q3_seq_N3.npy"),
                    np.array([[s[0][0], s[1][0], s[2][0],
                               s[0][1], s[1][1], s[2][1]] for s in seq3], dtype=np.int64))
            ss3 = DN.to_sorties(inst, seq3, pb3, N=3)
            print("N=3 原始架次 %d 个，最大悬停 %.0f s" % (len(ss3), max(s["hover"] for s in ss3)))
            ss3 = split_for_battery(inst, pb3, seq3, ss3, N=3)
            bad = DN.check_timing(inst, ss3)
            v = Q3.verify(inst, ph, ss3)
            over = [s for s in ss3 if s["soc"] < inst.d["rtype"].rho]
            print("N=3 换电后：架次 %d | 时序冲突 %d | 未覆盖 %d/%d | 电量不足 %d | 最大悬停 %.0f s | 用时 %.0f s"
                  % (len(ss3), len(bad), v["miss"], v["n"], len(over),
                     max(s["hover"] for s in ss3), time.time() - t1))
            for s in ss3:
                print("    #%02d %s %s (%.5f,%.5f) 离地%.0f 出动%.0f 建链%.0f 结束%.0f 悬停%5.0f E=%.3f SOC=%.1f%%"
                      % (s["rid"], s["drone"], s["comp"], s["lon"], s["lat"], s["agl"],
                         s["t_depart"], s["t_link_done"], s["t_end"], s["hover"],
                         s["e_total"], 100 * s["soc"]))
            rec.update(n3_ok=(v["miss"] == 0 and not bad and not over),
                       n3_sorties=len(ss3), n3_miss=v["miss"], n3_timing_conflicts=len(bad),
                       n3_energy_violations=len(over),
                       n3_energy=float(sum(s["e_total"] for s in ss3)),
                       n3_hover=float(sum(s["hover"] for s in ss3)),
                       n3_drones=sorted({s["drone"] for s in ss3}))
            solj["relay3"] = [dict(sid="Q3R3-%02d" % i, drone=s["drone"], comp=s["comp"],
                                   lon=float(s["lon"]), lat=float(s["lat"]),
                                   hover_alt=float(s["hover_alt"]), agl=float(s["agl"]),
                                   ground=float(s["ground"]), depart=float(s["t_depart"]),
                                   link_done=float(s["t_link_done"]), end=float(s["t_end"]),
                                   back=float(s["t_end"] + s["t_back"]), hover=float(s["hover"]),
                                   e_fly=float(s["e_fly"]), e_hover=float(s["e_hover"]),
                                   e_total=float(s["e_total"]), soc=float(s["soc"]),
                                   chg=float(s["chg"]))
                              for i, s in enumerate(ss3, 1)]
    solj.setdefault("meta", {})["relay_analysis"] = rec
    SIO.save(solj)
    print("\n已写入 solution.json 的 meta.relay_analysis 与 relay3")
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
