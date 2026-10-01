# -*- coding: utf-8 -*-
"""dump_p526_traj.py —— 把 P.526 模型下 N=4 的**完整中继轨迹**落盘

审稿意见第 4 项指出：论文主张 P.526 下"最小机队为 4"，但只有构造性贪心在 N=3
的失败记录，审稿人无法检视那条 7 架次方案。`results/信道模型对比.json` 里只有
聚合量（sorties/miss/energy/soc_min），没有逐架次的位置与时刻。

本脚本重跑 P.526 口径下的构造性判定，把 N=4 的可行方案**逐架次**写出：
位置、悬停高度、到位时刻、离站时刻、出动/返航、悬停时长、能耗、SOC，
并附上独立的校验结果（`check_timing` 与 `Q3.verify`），使正半部分可被检视。

输出：results/P526_N4_轨迹.json
用法：python code/dump_p526_traj.py
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import channel_compare as CC          # 复用其覆盖模型构造，保证与论文口径一致
import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import greedy_relay as GR
import solution_io as SIO

OUT = D.RESULTS


def build_instance(model="p526"):
    """按 channel_compare.run_one 的**同一套口径**构造 (inst, ph, link)，
    以便这里落盘的轨迹与论文里报告的聚合量出自同一条流水线。"""
    import channel_compare as CC
    inst = Q.Instance()
    sol, sorties, assign = CC.build_transport()
    link = CC.C.Link(inst, channel_model=model)
    import cover_model as CM
    cm = CM.CoverModel(inst, channel_model=model, verbose=False)
    ph = Q3.relay_phases(inst, sorties, assign, cm.palette, link=link, verbose=False,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    assert ph.get("ok"), "relay_phases 失败：%s" % ph.get("msg")
    return inst, ph, link


def main():
    inst, ph, link = build_instance("p526")
    rtype = inst.d["rtype"]
    cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
    cells = np.asarray(ph["cells"], dtype=np.float64)
    print("P.526 口径：需求格 %d，任务时长 %.0f s，T^cap=%.1f s"
          % (len(cells), float(cells[-1] - cells[0]), cap))

    out = dict(model="p526", note="ITU-R P.526 单刃峰绕射；N=4 的完整中继轨迹（逐架次）",
               n_cells=int(len(cells)), T_s=round(float(cells[-1] - cells[0]), 1),
               T_cap_s=round(cap, 1), N=4, runs=[])

    for topk in (200, 400, 600):
        for pre in (True, False):
            t0 = time.time()
            g = GR.greedy(inst, ph, N=4, mode="base", cap_s=cap, topk=topk,
                          verbose=False, preposition=pre)
            if not g["ok"]:
                out["runs"].append(dict(topk=topk, preposition=bool(pre),
                                        feasible=False,
                                        reached=int(g["reached_cell"]),
                                        fail=dict(k=int(g["fail"][0]), t=float(g["fail"][1]),
                                                  reason=g["fail"][2])))
                continue
            ss = GR.actions_to_sorties(inst, ph, g["actions"], 4, "base")
            bad = DN.check_timing(inst, ss, mode="base")
            v = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                          lon=s["lon"], lat=s["lat"],
                                          hover_alt=s["hover_alt"]) for s in ss], link=link)
            traj = []
            for s in ss:
                traj.append(dict(
                    rid=int(s["rid"]), slot=int(s["slot"]), drone=s.get("drone"),
                    comp=s.get("comp"),
                    lon=round(float(s["lon"]), 6), lat=round(float(s["lat"]), 6),
                    ground_m=round(float(s["ground"]), 1), agl_m=round(float(s["agl"]), 1),
                    hover_alt_m=round(float(s["hover_alt"]), 1),
                    t_depart_s=round(float(s["t_depart"]), 1),
                    t_link_done_s=round(float(s["t_link_done"]), 1),
                    t_end_s=round(float(s["t_end"]), 1),
                    hover_s=round(float(s["hover"]), 1),
                    e_fly_kWh=round(float(s["e_fly"]), 4),
                    e_hover_kWh=round(float(s["e_hover"]), 4),
                    e_total_kWh=round(float(s["e_total"]), 4),
                    soc_end=round(float(s["soc"]), 4),
                    charge_s=round(float(s.get("chg") or 0.0), 1)))
            out["runs"].append(dict(
                topk=topk, preposition=bool(pre), feasible=True,
                n_sorties=len(ss), timing_conflicts=len(bad), miss=int(v["miss"]),
                n_incidences=int(v.get("n", 0) or len(cells)),
                energy_kWh=round(float(sum(s["e_total"] for s in ss)), 3),
                soc_min=round(100 * float(min(s["soc"] for s in ss)), 1),
                max_hover_s=round(float(max(s["hover"] for s in ss)), 1),
                sec=round(time.time() - t0, 1), trajectory=traj))
            print("  topk=%-4d pre=%-5s 可行：%d 架次，未覆盖 %d，能耗 %.3f kWh，SOCmin %.1f%%，"
                  "时长冲突 %d，最大悬停 %.0f s"
                  % (topk, pre, len(ss), int(v["miss"]),
                     sum(s["e_total"] for s in ss),
                     100 * min(s["soc"] for s in ss), len(bad),
                     max(s["hover"] for s in ss)))
            break                      # 一种前置策略成功即可，不必重复

    p = os.path.join(OUT, "P526_N4_轨迹.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_ok = sum(1 for r in out["runs"] if r.get("feasible"))
    print("\n可行记录 %d 条，已写出：%s" % (n_ok, p))


if __name__ == "__main__":
    main()
