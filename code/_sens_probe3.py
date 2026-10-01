# -*- coding: utf-8 -*-
"""_sens_probe3.py —— 验证 q2.alns 在固定种子下是否可复现（不产出正式结果）。"""
from __future__ import annotations
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q2 as Q

SEED = 20260419
W = dict(count=1.5, energy=2.0, makespan=2.0, tardy=2.0)
inst = Q.Instance()


def mk():
    rng = random.Random(SEED)
    return Q.compact(inst, Q.construct(inst, rng, noise=1.0, w=W))


for iters in (400, 400, 800, 400, 800):
    Q._FEAS_CACHE.clear()
    sol, obj, met, it = Q.alns(inst, W, seed=SEED, iters=iters, tlimit=300.0, init=mk())
    print("iters=%4d 实际=%4d 架次=%2d 能耗=%6.2f 完工=%7.0f 延误=%9.0f 硬违反=%9.1f obj=%.4f"
          % (iters, it, met["count"], met["energy"], met["makespan"], met["tardiness"],
             met["hard_violation"], obj), flush=True)
print("done")
