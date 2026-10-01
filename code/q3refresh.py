# -*- coding: utf-8 -*-
"""
q3refresh.py —— 在**修正后的物理模型**（巡航高度 = max(航段/端点地形, 悬停点地形) + 50 m）
下重算问题三的两个中继方案，并回写 results/solution.json：

  (A) relay  —— 库存约束下的 2 架折中方案（strict 排程，如实记录通信中断）；
  (B) relay3 —— 达成全程连续通信的 3 架增配方案（构造性贪心，0 未覆盖 / 0 时序冲突）。

同时：
  * 删除过期的 meta.relay_resplit（旧物理下产生、与 relay_analysis 冲突的记录）；
  * 用当前 solution.json["transport"] 的**冻结运输方案**重建相位，不触碰 Q1/Q2 结果。

用法：python q3refresh.py [--topk 400] [--no-save]
"""
from __future__ import annotations

import argparse
import json
import os
import time

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO
import greedy_relay as GR

OUT = D.RESULTS


def load_frozen():
    solj = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(solj["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"])
                for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=float(r.get("chg", 0.0)),
                         soc=float(r.get("soc", 1.0)))
    return solj, sorties, assign


def rec_of(s, t_link=0.0):
    dep = s.get("t_depart")
    if dep is None:
        dep = max(0.0, float(s["t_link_done"]) - float(s["t_out"]) - float(t_link))
    return dict(sid="", drone=s["drone"], comp=s["comp"],
                lon=float(s["lon"]), lat=float(s["lat"]),
                hover_alt=float(s["hover_alt"]), agl=float(s["agl"]),
                ground=float(s["ground"]), depart=float(dep),
                link_done=float(s["t_link_done"]), end=float(s["t_end"]),
                back=float(s["t_end"] + s["t_back"]), hover=float(s["hover"]),
                e_fly=float(s["e_fly"]), e_hover=float(s["e_hover"]),
                e_total=float(s["e_total"]), soc=float(s["soc"]), chg=float(s["chg"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topk", type=int, default=400)
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    inst = Q.Instance()
    rtype = inst.d["rtype"]
    solj, sorties, assign = load_frozen()
    print("冻结运输方案：%d 个架次（未改动）" % len(sorties))

    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    print("相位/覆盖矩阵 %.0f s，相位数 %d" % (time.time() - t0, len(ph["intervals"])))

    # ---------- 结构性统计（供 make_numbers.py 直接读取，避免解析过期日志） ----------
    import numpy as np
    alone = ph["alone"]
    durs = [(int(r[1]) - int(r[0]) + 1) * float(Q3.GRID) for r in ph["intervals"]]
    groups = ph.get("groups") or []
    struct = dict(
        cand_pts=int(alone.shape[1]),
        instances=int(len(ph["T"])),
        cells=int(len(ph["cells"])),
        peak_concurrent=int(max(len(g) for g in groups)) if groups else 1,
        single_cover_cells=int(sum(1 for k in range(alone.shape[0]) if alone[k].any())),
        mean_pts=round(float(np.mean([int(ph["cov"][i].sum()) for i in range(len(ph["T"]))])), 1)
        if len(ph["T"]) else 0.0,
        phases=len(ph["intervals"]),
        multi_phases=sum(1 for r in ph["intervals"] if len(r[2]) > 1),
        min_phase_s=float(min(durs)) if durs else 0.0,
        max_phase_s=float(max(durs)) if durs else 0.0,
        short_phases=int(sum(1 for d in durs if d < 1400.0)),
        energy_cap_s=float(((1 - rtype.rho) * rtype.e_use - 0.35)
                           / (rtype.p_hover + rtype.p_comm) * 3600.0),
    )
    print("  结构统计：候选点 %d | 需求实例 %d | 时间格 %d | 相数 %d（短相 %d）| 单次驻留上限 %.0f s"
          % (struct["cand_pts"], struct["instances"], struct["cells"], struct["phases"],
             struct["short_phases"], struct["energy_cap_s"]))

    # ---------- (A) 2 架折中 ----------
    ss2, warn2, outage2 = Q3.schedule_relay(inst, ph, verbose=True, strict=True)
    v2 = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                   lon=s["lon"], lat=s["lat"], hover_alt=s["hover_alt"])
                              for s in ss2], link=ph.get("link"))
    ov2 = [s for s in ss2 if s["soc"] < rtype.rho]
    outage_s = float(sum(o["t1"] - o["t0"] for o in outage2))
    # 失联时长覆盖率（口径：被中继**完整保障**的需求时间格数 / 总需求时间格数）
    _cells2 = np.asarray(ph["cells"], dtype=np.float64)
    _served = set()
    for s in ss2:
        m = (_cells2 >= float(s["t_link_done"]) - 1e-9) & (_cells2 <= float(s["t_end"]) + 1e-9)
        _served |= set(np.nonzero(m)[0].tolist())
    cover_pct = 100.0 * len(_served) / max(1, int(len(_cells2)))
    for i, s in enumerate(ss2, 1):
        s["sid"] = "Q3-R-%02d" % i
    print("  2 架折中：架次 %d | 未覆盖 %d/%d | 中断相 %d 个（%.0f s）| 能耗 %.3f kWh "
          "| 失联时长覆盖率 %.1f%%（%d/%d 格）"
          % (len(ss2), v2["miss"], v2["n"], len(outage2), outage_s,
             sum(s["e_total"] for s in ss2), cover_pct, len(_served), len(_cells2)))

    # ---------- (B) 3 架增配（构造性贪心，可行性证据） ----------
    cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
    g = GR.greedy(inst, ph, N=3, mode="base", cap_s=cap, topk=a.topk, verbose=True)
    if not g["ok"]:
        print("  !! 贪心 N=3 不可行：%s" % (g["fail"],))
        rec3 = dict(ok=False, msg=str(g["fail"]))
        ss3 = []
    else:
        ss3 = GR.actions_to_sorties(inst, ph, g["actions"], 3, "base")
        bad3 = DN.check_timing(inst, ss3, mode="base")
        v3 = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                       lon=s["lon"], lat=s["lat"], hover_alt=s["hover_alt"])
                                  for s in ss3], link=ph.get("link"))
        ov3 = [s for s in ss3 if s["soc"] < rtype.rho]
        for i, s in enumerate(ss3, 1):
            s["sid"] = "Q3R3-%02d" % i
            s["drone"] = (inst.d["rfleet"][s["slot"]] if s["slot"] < len(inst.d["rfleet"])
                          else "R%02d(增配)" % (s["slot"] + 1))
        print("  3 架增配：架次 %d | 时序冲突 %d | 未覆盖 %d/%d | 能耗 %.3f kWh | "
              "悬停合计 %.0f s | SOC 最低 %.1f%% | 换位动作 %d 次"
              % (len(ss3), len(bad3), v3["miss"], v3["n"],
                 sum(s["e_total"] for s in ss3), sum(s["hover"] for s in ss3),
                 100 * min(s["soc"] for s in ss3), g["n_actions"]))
        for s in ss3:
            print("    %s %-9s %-5s (%.5f,%.5f) 离地%4.0f 出动%5.0f 建链%5.0f 结束%5.0f "
                  "悬停%5.0f E=%.3f SOC=%4.1f%%"
                  % (s["sid"], s["drone"], s["comp"], s["lon"], s["lat"], s["agl"],
                     s["t_depart"], s["t_link_done"], s["t_end"], s["hover"],
                     s["e_total"], 100 * s["soc"]))
        rec3 = dict(ok=bool(v3["miss"] == 0 and not bad3 and not ov3),
                    sorties=len(ss3), miss=int(v3["miss"]), timing_conflicts=len(bad3),
                    energy_violations=len(ov3),
                    energy=round(float(sum(s["e_total"] for s in ss3)), 3),
                    hover=round(float(sum(s["hover"] for s in ss3)), 1),
                    drones=sorted({s["drone"] for s in ss3}),
                    soc_min=round(100 * float(min(s["soc"] for s in ss3)), 1),
                    n_actions=int(g["n_actions"]))

    # ---------- 回写 ----------
    run = solj.setdefault("meta", {})
    _relay2 = [rec_of(s, rtype.t_link) for s in ss2]
    for i, r in enumerate(_relay2, 1):
        r["sid"] = "Q3-R-%02d" % i
    _relay3 = [rec_of(s, rtype.t_link) for s in ss3]
    for i, r in enumerate(_relay3, 1):
        r["sid"] = "Q3R3-%02d" % i
    ra = dict(tested_at=time.strftime("%Y-%m-%d %H:%M:%S"),
              physics="cruise = max(航段/端点地形, 悬停点地形) + 50 m（修正后）",
              n2_feasible=False,
              n2_msg="2 架中继在“每架次返回 O01”模型下无可行换位（贪心与状态 DP 一致）",
              n_relay_required=3,
              n2_sorties=len(ss2), n2_miss=int(v2["miss"]), n2_outage_n=len(outage2),
              n2_outage_s=round(outage_s, 1),
              n2_energy=round(float(sum(s["e_total"] for s in ss2)), 3),
              n2_hover=round(float(sum(s["hover"] for s in ss2)), 1),
              n2_cover_pct=round(cover_pct, 1), n2_cover_cells=len(_served),
              n2_cells=int(len(_cells2)),
              n3_ok=rec3.get("ok", False),
              n3_sorties=rec3.get("sorties", 0), n3_miss=rec3.get("miss", None),
              n3_timing_conflicts=rec3.get("timing_conflicts", None),
              n3_energy_violations=rec3.get("energy_violations", None),
              n3_energy=rec3.get("energy", 0.0), n3_hover=rec3.get("hover", 0.0),
              n3_max_hover=round(float(max((s["hover"] for s in ss3), default=0.0)), 1),
              n3_drones=rec3.get("drones", []), n3_soc_min=rec3.get("soc_min", None),
              n3_method="构造性贪心（可行性证据），候选悬停点上限 %d" % a.topk,
              struct=struct)
    solj["meta"]["relay_analysis"] = ra
    solj["meta"]["n_relay"] = len(ss2)
    solj["meta"]["relay_energy"] = ra["n2_energy"]
    solj["meta"]["relay_hover"] = round(float(sum(s["hover"] for s in ss2)), 1)
    solj["meta"]["relay_outage_s"] = round(outage_s, 1)
    solj["meta"]["relay_outage_n"] = int(len(outage2))
    solj["meta"]["comm_ok"] = bool(v2["ok"])
    solj["meta"]["comm_miss"] = int(v2["miss"])
    solj["meta"]["joint_makespan"] = float(max([solj["meta"].get("makespan", 0.0)]
                                               + [s["t_end"] + s["t_back"] for s in ss2]))
    solj["relay"] = _relay2
    solj["relay3"] = _relay3
    if "relay_resplit" in solj["meta"]:
        solj["meta"].pop("relay_resplit")
        solj["meta"]["relay_resplit_removed"] = \
            "旧物理模型下产生，与 relay_analysis 冲突，已删除（见 q3refresh.py）"
    # ---------- 汇总 JSON：make_numbers.py / export_results.py 的唯一权威来源 ----------
    summary = dict(generated=ra["tested_at"], physics=ra["physics"], struct=struct,
                   n2=dict(feasible=False, sorties=len(ss2), miss=int(v2["miss"]),
                           outage_n=len(outage2), outage_s=round(outage_s, 1),
                           energy=ra["n2_energy"], hover=ra["n2_hover"],
                           cover_pct=ra["n2_cover_pct"], cover_cells=ra["n2_cover_cells"],
                           cells=ra["n2_cells"]),
                   n3=dict(feasible=rec3.get("ok", False), sorties=len(ss3),
                           miss=rec3.get("miss"), timing_conflicts=rec3.get("timing_conflicts"),
                           energy=ra["n3_energy"], hover=ra["n3_hover"],
                           max_hover=ra["n3_max_hover"], soc_min=rec3.get("soc_min"),
                           drones=rec3.get("drones", []), n_actions=rec3.get("n_actions")),
                   )
    if not a.no_save:
        with open(os.path.join(D.RESULTS, "Q3_方案汇总.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=1, default=float)
        SIO.save(solj)
        print("\n已回写 %s（relay / relay3 / meta.relay_analysis；已清除 relay_resplit）"
              % SIO.SOL_JSON)
        print("已写出 %s" % os.path.join(D.RESULTS, "Q3_方案汇总.json"))
    else:
        print("\n--no-save：未写盘")
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
