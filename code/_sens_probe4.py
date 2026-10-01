# -*- coding: utf-8 -*-
"""_sens_probe4.py —— 测量正式预算下单次配置的耗时（不产出正式结果）。"""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import q2 as Q
import sensitivity as S

print("hashseed:", os.environ.get("PYTHONHASHSEED"))
inst = Q.Instance()
for iters, restarts in ((150, 1), (300, 2), (400, 2), (400, 1)):
    Q._FEAS_CACHE.clear()
    t0 = time.time()
    sol, pol, it = S.q2_solve(inst, iters=iters, restarts=restarts, tlimit=120.0,
                              cpsat=6.0, ls=2000)
    el = time.time() - t0
    m = pol["met"]
    print("iters=%3d restarts=%d -> %6.1fs  架次=%2d 能耗=%6.2f 完工=%7.0f 延误=%9.0f 硬违反=%8.1f tag=%s"
          % (iters, restarts, el, m["count"], m["energy"], m["makespan"], m["tardiness"],
             m["hard_violation"], pol["tag"]), flush=True)
print("done")
