# -*- coding: utf-8 -*-
"""exact_topk_sweep.py —— 候选集筛选是否是"N=2 不可行"的来源？

审稿意见（第 2 项）的实质：现有"两架不可行"结论在**每格 top-12** 的候选筛选下得到，
关闭状态剪枝不能消除候选筛选造成的遗漏，因此不能据此宣称全实例最小机队为 3。

本脚本只做一件事：把 top-k 从 12 逐步放大到"全部合格点（topk=0）"，看结论是否改变，
并如实区分三种结局：
    INFEASIBLE   在完整候选集上跑完，且仍无可行状态 → 不可行性不是筛选造成的
    FEASIBLE     找到可行状态 → 原结论错误，必须撤回
    UNFINISHED   状态数超出内存护栏 → 未跑完，**不得**据此宣称不可行

同时报告每一层的峰值状态数与失败位置，便于判断"失败位置是否随 k 增大而后移"
（若后移到某处停住，说明限制性的候选取尽已不改变结论）。

用法：
    python code/exact_topk_sweep.py --mode base --topks 12,24,48,96,0 --max-states 1500000
输出：results/候选集扫描.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback

import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def build_phase():
    """与 obstruction.py / recompute_relay.py 完全一致的 phase 构造，保证可比。"""
    inst = Q.Instance()
    sol = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"])
                for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]),
                         drone=r["drone"], battery=r["battery"],
                         chg=float(r.get("chg", 0.0)), soc=float(r.get("soc", 1.0)))
    return inst, Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette,
                                verbose=False, min_phase_s=1400.0,
                                max_phase_s=5400.0)


def hover_cap_s(inst):
    rt = inst.d["rtype"]
    return float(((1 - rt.rho) * rt.e_use - 0.35) / (rt.p_hover + rt.p_comm) * 3600.0)


def run_one(ph, inst, N, mode, topk, max_states, cap, enforce_cap):
    """跑一次 exact=True 的判定；topk=0 表示完整合格候选集。"""
    t0 = time.time()
    try:
        seq, cost, pb, diag = DN.solve(
            ph, N=N, topk=topk, exact=True, inst=inst, verbose=False,
            max_hover_s=(cap if enforce_cap else None), mode=mode,
            max_states=max_states)
    except DN.StateSpaceOverflow as e:
        return dict(verdict="UNFINISHED", detail=str(e)[:200],
                    sec=round(time.time() - t0, 1))
    except MemoryError:
        return dict(verdict="UNFINISHED", detail="MemoryError",
                    sec=round(time.time() - t0, 1))
    except Exception as e:                                   # noqa: BLE001
        return dict(verdict="ERROR", detail=repr(e)[:200] + traceback.format_exc()[-300:],
                    sec=round(time.time() - t0, 1))
    d = diag or {}
    if seq is not None:
        return dict(verdict="FEASIBLE", cost=int(cost), sec=round(time.time() - t0, 1),
                    max_state=int(d.get("n_state") or 0), n_cand=int(len(pb.useful)))
    return dict(verdict="INFEASIBLE", reason=str(cost),
                fail_k=d.get("k"), fail_t=d.get("t"),
                max_state=int(d.get("n_state") or 0), n_cand=int(len(pb.useful)),
                sec=round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="base")
    ap.add_argument("--N", type=int, default=2)
    ap.add_argument("--topks", default="12,24,48,96,192,0")
    ap.add_argument("--max-states", type=int, default=1500000)
    ap.add_argument("--enforce-cap", action="store_true",
                    help="施加 T^cap 能量上限；默认不施加（更宽松，结论更强）")
    a = ap.parse_args()

    inst, ph = build_phase()
    cap = hover_cap_s(inst)
    cells = np.asarray(ph["cells"], dtype=np.float64)
    T = float(cells[-1] - cells[0])
    topks = [int(x) for x in a.topks.split(",") if x.strip() != ""]
    print("需求格 %d，时长 %.0f s，T^cap=%.1f s，N=%d，Mode=%s，能量上限=%s"
          % (len(cells), T, cap, a.N, a.mode, "施加" if a.enforce_cap else "不施加"))
    print("逐档放大候选集：topk = %s（0 表示全部合格点）\n" % topks)

    out = dict(n_cells=int(len(cells)), T_s=round(T, 1), T_cap_s=round(cap, 1),
               N=int(a.N), mode=a.mode, energy_cap_enforced=bool(a.enforce_cap),
               max_states=int(a.max_states), sweep=[])
    for topk in topks:
        r = run_one(ph, inst, a.N, a.mode, topk, a.max_states, cap, a.enforce_cap)
        r["topk"] = topk
        out["sweep"].append(r)
        print("  topk=%-4d  %-11s 峰值状态=%-8s %6.1f s   %s"
              % (topk, r["verdict"], r.get("max_state", "-"), r.get("sec", -1),
                 ("失败于第 %s 格 t=%s s" % (r.get("fail_k"), r.get("fail_t")))
                 if r["verdict"] == "INFEASIBLE" else (r.get("reason") or r.get("detail") or "")))

    verdicts = {r["verdict"] for r in out["sweep"]}
    if "FEASIBLE" in verdicts:
        out["conclusion"] = "存在可行解：原'不可行'结论必须撤回"
    elif "UNFINISHED" in verdicts:
        out["conclusion"] = ("至少一档未跑完：不可行性只在已跑完的候选口径上成立，"
                             "必须如实标注搜索边界")
    else:
        out["conclusion"] = ("在完整合格候选集（topk=0）上跑完且仍不可行："
                             "不可行性不是候选筛选造成的")
    print("\n结论：%s" % out["conclusion"])

    p = os.path.join(OUT, "候选集扫描.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写出：%s" % p)


if __name__ == "__main__":
    main()
