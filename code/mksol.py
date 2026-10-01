# -*- coding: utf-8 -*-
"""mksol.py —— 生成标准解文件 results/solution.json（供 Q3/Q4/导出/校验/论文共用）。"""
from __future__ import annotations

import os, sys, time, json, random
import numpy as np

import dcore as D
import q2 as Q
import solution_io as SIO


def build(inst, tlimit=25.0, seed=3, comm_w=8.0, cpsat=25.0, ls_iters=3000):
    w = dict(count=1.5, energy=2.0, makespan=2.0, tardy=2.0, comm=comm_w)
    rng = random.Random(seed)
    sol = Q.compact(inst, Q.construct(inst, rng, noise=1.0, w=w))
    sol, obj, met, it = Q.alns(inst, w, seed=seed, iters=6000, tlimit=tlimit, init=sol)
    pol = Q.polish(inst, sol, cpsat_limit=cpsat, ls_iters=ls_iters)
    return sol, pol


def portfolio(inst, budget=110.0, verbose=True):
    """多权重多随机种子组合，取"硬约束可行 → 延误小 → 完工早 → 能耗低"的解。"""
    t0 = time.time()
    best = None
    trials = []
    for w in Q.WEIGHTS:
        w = dict(w)
        w["comm"] = 8.0
        trials.append(w)
    trials.append(dict(name="P6-通信优先", count=1.5, energy=2.0, makespan=2.0, tardy=2.0, comm=25.0))
    for k, w in enumerate(trials):
        sol, obj, met, it = Q.alns(inst, w, seed=11 + 7 * k, iters=20000,
                                   tlimit=max(10.0, budget / len(trials) - 3))
        pol = Q.polish(inst, sol, cpsat_limit=20.0, ls_iters=2500)
        m = pol["met"]
        key = (round(m["hard_violation"], 3), m["tardiness"], m["makespan"], m["energy"])
        if verbose:
            print("  %-14s 架次=%2d 能耗=%6.2f 完工=%6.0f 延误=%8.0f 及时率=%.3f 硬违反=%.0f [%s]"
                  % (w["name"], m["count"], m["energy"], m["makespan"], m["tardiness"],
                     m["ontime_rate"], m["hard_violation"], pol["tag"]))
        if best is None or key < best[0]:
            best = (key, sol, pol, w["name"])
    if verbose:
        print("最优方案：%s  %s  用时 %.0f s" % (best[3], best[0], time.time() - t0))
    return best[1], best[2], best[3]


def main(tlimit=25.0, portfolio_mode=True):
    t0 = time.time()
    inst = Q.Instance()
    if portfolio_mode:
        sol, pol, tag = portfolio(inst, budget=max(60.0, tlimit * 5))
    else:
        sol, pol = build(inst, tlimit=tlimit)
        tag = "single"
    tr = SIO.transport_from_sorties(inst, sol, pol["assign"], code_prefix="Q2")
    solj = dict(meta=dict(rho=inst.rho, makespan=pol["makespan"], energy=sum(s.E for s in sol),
                          n_transport=len(sol), polish=pol["tag"], scheme=tag,
                          tardiness=pol["met"]["tardiness"],
                          ontime_rate=pol["met"]["ontime_rate"],
                          hard_violation=pol["met"]["hard_violation"],
                          nbox=len(inst.boxes)),
                transport=tr, relay=[], coverage=[])
    SIO.save(solj)
    print("transport sorties %d, makespan %.0f, energy %.2f, tard %.0f, ontime %.3f, hard %.0f (%.0f s)"
          % (len(tr), solj["meta"]["makespan"], solj["meta"]["energy"],
             solj["meta"]["tardiness"], solj["meta"]["ontime_rate"],
             solj["meta"]["hard_violation"], time.time() - t0))
    return solj


if __name__ == "__main__":
    tl = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    main(tl)
