# -*- coding: utf-8 -*-
"""rdiag.py —— 通信需求结构诊断：并发度、时段可覆盖性、每 300 s 槽位所需最少悬停点数。"""
from __future__ import annotations

import os, time
import numpy as np
import pandas as pd

import dcore as D
import comm as C
import q2 as Q
import relay as R
import cscan


def main():
    t0 = time.time()
    inst = Q.Instance()
    sol, pol = cscan.build_solution(inst)
    assign = pol["assign"]
    tracks = {k: C.sortie_track(inst, s, assign[k]["start"]) for k, s in enumerate(sol)}
    link = C.Link(inst)
    T, P, K, PH = [], [], [], []
    for k, tr in tracks.items():
        ok, lp, bl = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        for i in np.nonzero(~ok)[0]:
            T.append(tr["t"][i]); P.append((tr["lon"][i], tr["lat"][i], tr["alt"][i]))
            K.append(k); PH.append(tr["phase"][i])
    o = np.argsort(T)
    T = np.array(T)[o]; P = np.array(P)[o]; K = np.array(K)[o]; PH = np.array(PH)[o]
    print("需求点数 %d，并发峰值 %d" % (len(T), np.unique(T, return_counts=True)[1].max()))

    # 相邻需求点的时间间隔分布
    dt = np.diff(T)
    print("相邻需求时间间隔：中位数 %.1f s，<=2s 占 %.1f%%，<=10s 占 %.1f%%"
          % (np.median(dt), 100 * (dt <= 2).mean(), 100 * (dt <= 10).mean()))

    # 同一时刻的需求来自哪些架次
    uq, cnt = np.unique(T, return_counts=True)
    print("同一时刻并发需求数分布：", dict(zip(*np.unique(cnt, return_counts=True))))

    # 相邻时刻的需求是否来自同一架次
    same = (K[1:] == K[:-1])
    print("相邻需求样本同架次比例 %.1f%%" % (100 * same.mean()))
    close = dt <= 10
    print("间隔<=10s 的相邻对中，同架次比例 %.1f%%" % (100 * same[close].mean()))

    # 候选点
    cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=0.0040, pad=0.018,
                                 agl=(100.0, 300.0))
    cov, bh_ok, acc = R.coverage_matrix(link, P, cand)
    print("候选点 %d，回传可用 %d" % (len(cand), int(bh_ok.sum())))

    # 按 300 s 槽位：每槽最少需要几个候选点覆盖全部需求（贪心集合覆盖）
    slot = np.floor(T / 300.0).astype(int)
    rows = []
    total_sets = 0
    for s in np.unique(slot):
        idx = np.nonzero(slot == s)[0]
        need = cov[idx].all(axis=0)          # 能单独覆盖整槽的候选点
        if need.any():
            k = 1
        else:
            # 贪心集合覆盖
            rem = np.ones(len(idx), dtype=bool)
            k = 0
            while rem.any() and k < 5:
                sub = np.nonzero(rem)[0]
                gains = cov[idx[sub]].sum(axis=0)
                c = int(np.argmax(gains))
                if gains[c] == 0:
                    k = 99
                    break
                hit = cov[idx[sub]][:, c]
                rem[sub[hit]] = False
                k += 1
        total_sets += k if k < 99 else 0
        rows.append(dict(槽=s, 时段="%d-%d" % (s * 300, (s + 1) * 300), 需求点=int(len(idx)),
                         独立可覆盖点=int(need.sum()), 最少悬停点数=k,
                         涉及架次=len(set(K[idx].tolist()))))
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("\n合计最少悬停点数（按槽独立计算，未计转移代价）= %d" % total_sets)
    df.to_excel(os.path.join(D.BASE, "results", "Q3_槽位诊断.xlsx"), index=False)
    print("耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
