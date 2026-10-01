# -*- coding: utf-8 -*-
"""cscan.py —— 用当前解扫描通信直连可用性，定位通信缺口。"""
from __future__ import annotations

import os, sys, json, time
import numpy as np
import pandas as pd

import dcore as D
import comm as C
import q2 as Q


def build_solution(inst, tlimit=25.0, seed=0):
    import random
    rng = random.Random(seed)
    w = dict(count=1.5, energy=2.0, makespan=2.0, tardy=2.0)
    sol = Q.compact(inst, Q.construct(inst, rng, noise=1.0, w=w))
    sol, obj, met, it = Q.alns(inst, w, seed=seed, iters=4000, tlimit=tlimit, init=sol)
    pol = Q.polish(inst, sol, cpsat_limit=25.0)
    return sol, pol


def main():
    t0 = time.time()
    inst = Q.Instance()
    sol, pol = build_solution(inst)
    print("Q2 基准解：架次=%d 能耗=%.2f 完工=%.0f 硬违反=%.0f [%s] (%.0fs)"
          % (pol["met"]["count"], pol["met"]["energy"], pol["met"]["makespan"],
             pol["met"]["hard_violation"], pol["tag"], time.time() - t0))

    assign = pol["assign"]
    tracks = {}
    for k, s in enumerate(sol):
        tracks[k] = C.sortie_track(inst, s, assign[k]["start"])
    link = C.Link(inst)
    res, stat = C.scan_direct(inst, tracks, link)
    print("直连扫描：采样点 %d，不可用 %d（%.1f%%）"
          % (stat["n_sample"], stat["n_uncov"], 100 * stat["uncov_rate"]))

    rows = []
    for k in sorted(res):
        tr = res[k]["track"]
        unc = res[k]["uncov"]
        if len(unc):
            rows.append(dict(k=k, g=sol[k].g, areas=";".join(sol[k].areas), n_unc=len(unc),
                             n=len(tr["t"]), t0=float(tr["t"][unc[0]]), t1=float(tr["t"][unc[-1]]),
                             maxblock=int(res[k]["blocked"].sum())))
    df = pd.DataFrame(rows)
    print("\n有通信缺口的架次：")
    print(df.to_string(index=False) if len(df) else "  （无）")

    # 缺口按时间分布
    allunc = []
    for k in res:
        tr = res[k]["track"]
        for i in res[k]["uncov"]:
            allunc.append((float(tr["t"][i]), k, float(tr["lon"][i]), float(tr["lat"][i]), float(tr["alt"][i]), tr["phase"][i]))
    allunc.sort()
    print("\n缺口时间跨度：%.0f – %.0f s，共 %d 个采样点" %
          (allunc[0][0] if allunc else 0, allunc[-1][0] if allunc else 0, len(allunc)))
    # 并发缺口（同一时刻有多少架运输机失去直连）
    if allunc:
        tt = np.array([a[0] for a in allunc])
        bins = np.arange(0, max(tt.max() + 600, 3600), 300)
        h, _ = np.histogram(tt, bins=bins)
        print("\n缺口采样点数按 300 s 分箱：")
        for i, c in enumerate(h):
            if c:
                print("  %5.0f-%5.0f s : %d" % (bins[i], bins[i + 1], c))
    np.save(os.path.join(D.BASE, "results", "Q3_uncov_points.npy"),
            np.array([[a[0], a[1], a[2], a[3], a[4]] for a in allunc]) if allunc else np.zeros((0, 5)))
    # 保存基准解
    Q.export(inst, "B", sol, pol, path=os.path.join(D.BASE, "results", "Q3_基准运输方案.xlsx"))
    print("\n输出：Q3_基准运输方案.xlsx, Q3_uncov_points.npy  总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
