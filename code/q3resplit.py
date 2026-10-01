# -*- coding: utf-8 -*-
"""
q3resplit.py —— 对已求出的中继航迹做"换组件再拆分"，使每个架次的悬停与能耗都满足
                能源组件容量与返航电量下限，且拆分窗口内其余中继可联合保障。

输入：results/solution.json（relay = 2 架折中方案；relay3 = 3 架增配方案）
输出：把拆分后的方案写回 solution.json（relay / relay3），并打印对比。
"""
from __future__ import annotations

import os
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import solution_io as SIO

OUT = D.RESULTS


def build_ph(solj):
    inst = Q.Instance()
    sorties, assign = [], {}
    for i, r in enumerate(solj["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"]) for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=float(r.get("chg", 0.0)),
                         soc=float(r.get("soc", 1.0)))
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    return inst, ph


def union_covers(inst, ph, positions, k, halfw_cells):
    """positions（(lon,lat,alt) 列表）的覆盖并集能否覆盖 cell 区间 [k-h, k+h] 的全部需求。"""
    link = ph["link"]
    cells = ph["cells"]
    n = len(cells)
    k0 = max(0, k - halfw_cells); k1 = min(n - 1, k + halfw_cells)
    for kk in range(k0, k1 + 1):
        g = ph["groups"][kk]
        pts = ph["P"][g]
        m = np.zeros(len(g), dtype=bool)
        for p in positions:
            a_ok, _, _ = link.access_ok(pts, p)
            b_ok, _, _ = link.backhaul_ok(np.array([p]))
            m |= (a_ok & bool(b_ok[0]))
        if not m.all():
            return False
    return True


def active_positions(records, slot, t, exclude_rid=None):
    out = []
    for r in records:
        if r["drone"].startswith("R%02d" % (slot + 1)) is False and r.get("slot") != slot:
            pass
    return out


def resplit(inst, ph, records, cap_s=None, halfw_cells=110, verbose=True):
    rtype = inst.d["rtype"]
    dem = D.get_dem()
    cells = ph["cells"]
    n = len(cells)
    tp = np.array([float(c) for c in cells])

    def pos_of(r):
        return (float(r["lon"]), float(r["lat"]), float(r["hover_alt"]))

    def cap(r):
        e_fly = r["e_fly"]
        return max(60.0, ((1 - rtype.rho) * rtype.e_use - e_fly) / (rtype.p_hover + rtype.p_comm) * 3600.0)

    out = []
    for r in records:
        lim = cap(r) if cap_s is None else cap_s
        t0, t1 = float(r["link_done"]), float(r["end"])
        if t1 - t0 <= lim:
            out.append(dict(r)); continue
        others = [x for x in records if x["drone"] != r["drone"] or x is not r]
        others = [x for x in records if not (x["drone"] == r["drone"] and
                                             abs(x["link_done"] - r["link_done"]) < 1e-6
                                             and abs(x["end"] - r["end"]) < 1e-6)]
        cuts = []
        cur = t0
        while t1 - cur > lim:
            tgt = cur + lim
            kt = int(np.searchsorted(tp, tgt))
            found = None
            for dk in range(0, 60):
                for kk in (kt - dk, kt + dk):
                    if kk <= 0 or kk >= n:
                        continue
                    kk = int(np.clip(kk, 1, n - 1))
                    tk = float(cells[kk])
                    if tk <= cur + 60 or tk >= t1:
                        continue
                    act = [pos_of(x) for x in others
                           if float(x["link_done"]) - 1e-6 <= tk <= float(x["end"]) + 1e-6]
                    if len(act) < 1:
                        continue
                    if union_covers(inst, ph, act, kk, halfw_cells):
                        found = tk
                        break
                if found is not None:
                    break
            if found is None:
                break
            cuts.append(found)
            cur = found
        if not cuts:
            out.append(dict(r))
            if verbose:
                print("    ! %s 悬停 %.0f s 超容量 %.0f s 且无可拆分窗口" % (r["sid"], t1 - t0, lim))
            continue
        prev = t0
        for c in cuts + [t1]:
            q = dict(r)
            q["link_done"] = prev
            q["end"] = c
            out.append(q)
            prev = c
        if verbose:
            print("    · %s（%.0f s）拆为 %d 段：%s" % (r["sid"], t1 - t0, len(cuts) + 1,
                  ", ".join("%.0f" % (x - y) for x, y in zip(cuts + [t1], [t0] + cuts))))
    # 重算物理量
    for q in out:
        lo, la, alt = float(q["lon"]), float(q["lat"]), float(q["hover_alt"])
        agl = alt - float(dem.at(lo, la))
        rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
        q["hover"] = max(0.0, float(q["end"]) - float(q["link_done"]))
        q["e_fly"] = rf["e_fly"]; q["t_out"] = rf["t_out"]; q["t_back"] = rf["t_back"]
        q["e_hover"] = (rtype.p_hover + rtype.p_comm) * q["hover"] / 3600.0
        q["e_total"] = q["e_fly"] + q["e_hover"]
        q["soc"] = 1.0 - q["e_total"] / rtype.e_use
        q["chg"] = float(D.charge_time(q["soc"], inst.d["rbatt"][1]))
        q["depart"] = max(0.0, float(q["link_done"]) - rf["t_out"] - rtype.t_link)
        q["back"] = float(q["end"]) + rf["t_back"]
    out.sort(key=lambda s: (float(s["link_done"]), s["drone"]))
    for i, s in enumerate(out, 1):
        s["sid"] = s["sid"].split("-")[0] + "-%02d" % i
    return out


def report(inst, ph, records, tag):
    bad = [s for s in records if s["soc"] < inst.d["rtype"].rho - 1e-9]
    over = [s for s in records if s["hover"] > 0 and
            s["e_total"] > (1 - inst.d["rtype"].rho) * inst.d["rtype"].e_use]
    conf = 0
    for dr in sorted({s["drone"] for s in records}):
        seq = sorted([s for s in records if s["drone"] == dr], key=lambda s: float(s["link_done"]))
        free = 0.0
        for s in seq:
            if float(s["depart"]) < free - 1e-6:
                conf += 1
            free = max(free, float(s["back"]) + inst.d["rtype"].t_turn)
    print("  %s：架次 %d | 无人机 %d | 时序冲突 %d | 电量不足 %d | 最大悬停 %.0f s | 能耗 %.3f kWh | SOC 最低 %.1f%%"
          % (tag, len(records), len({s["drone"] for s in records}), conf, len(bad),
             max(s["hover"] for s in records), sum(s["e_total"] for s in records),
             100 * min(s["soc"] for s in records)))
    return dict(n=len(records), drones=len({s["drone"] for s in records}), conflicts=conf,
                soc_bad=len(bad), max_hover=max(s["hover"] for s in records),
                energy=sum(s["e_total"] for s in records),
                soc_min=min(s["soc"] for s in records))


def main():
    solj = SIO.load()
    inst, ph = build_ph(solj)
    summary = {}
    for key, tag in (("relay", "2架折中"), ("relay3", "3架增配")):
        recs = solj.get(key) or []
        if not recs:
            continue
        print("\n=== %s 原始 ===" % tag)
        report(inst, ph, recs, tag + "-原始")
        new = resplit(inst, ph, recs)
        print("=== %s 再拆分后 ===" % tag)
        summary[key] = report(inst, ph, new, tag + "-拆分后")
        solj[key] = new
    solj.setdefault("meta", {})["relay_resplit"] = summary
    SIO.save(solj)
    print("\n已写回 solution.json")


if __name__ == "__main__":
    main()
