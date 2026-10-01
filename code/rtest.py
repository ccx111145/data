# -*- coding: utf-8 -*-
"""rtest.py —— 中继覆盖可行性试算：需要几个中继位置/架次才能补全通信。"""
from __future__ import annotations

import os, time, json
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
    print("运输基准解：架次=%d 能耗=%.1f 完工=%.0f 硬违反=%.0f [%s]"
          % (len(sol), pol["met"]["energy"], pol["met"]["makespan"],
             pol["met"]["hard_violation"], pol["tag"]))
    assign = pol["assign"]
    tracks = {k: C.sortie_track(inst, s, assign[k]["start"]) for k, s in enumerate(sol)}
    link = C.Link(inst)

    # 汇总需求点
    T, P, K = [], [], []
    for k, tr in tracks.items():
        ok, lp, blocked = link.direct_ok(np.c_[tr["lon"], tr["lat"], tr["alt"]])
        idx = np.nonzero(~ok)[0]
        for i in idx:
            T.append(tr["t"][i]); P.append((tr["lon"][i], tr["lat"][i], tr["alt"][i])); K.append(k)
    order = np.argsort(T)
    T = np.array(T)[order]; P = np.array(P)[order]; K = np.array(K)[order]
    print("通信需求采样点 %d 个，时间 %.0f–%.0f s，涉及 %d 个架次"
          % (len(T), T.min(), T.max(), len(set(K.tolist()))))
    # 并发度
    uq, cnt = np.unique(T, return_counts=True)
    print("最大并发失联运输机数 = %d（%d 个不同时刻）" % (cnt.max(), len(uq)))

    cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=0.0040, pad=0.018,
                                 agl=(100.0, 300.0))
    print("中继候选悬停点 %d 个（网格 0.004° ≈ 440 m × 2 个离地高度），耗时 %.0f s"
          % (len(cand), time.time() - t0))
    cov, bh_ok, acc = R.coverage_matrix(link, P, cand)
    print("回传可用候选点 %d / %d；覆盖矩阵耗时 %.0f s" % (int(bh_ok.sum()), len(cand), time.time() - t0))
    print("单个需求点平均可被 %d 个候选点覆盖" % cov.sum(axis=1).mean())

    runs = R.fully_covering_runs(T, cov, meta)
    print("极大完全覆盖时段 %d 个" % len(runs))
    chosen, fail = R.cover_schedule(T, runs)
    if chosen is None:
        print("！存在无法被任何单点完全覆盖的需求时刻 t=%.0f" % fail)
        return
    ch = R.merge_runs(chosen)
    print("最小覆盖时段数 = %d（合并后 %d）" % (len(chosen), len(ch)))
    for r in ch:
        lo, la, g, h = meta[r[2]]
        print("   时段 %7.0f–%7.0f s (%6.0f s) @ (%.5f, %.5f) 离地 %.0f m 覆盖 %d 个时刻"
              % (r[0], r[1], r[1] - r[0], lo, la, h, r[3]))
    # 同时占用数
    ev = []
    for r in ch:
        ev.append((r[0], 1)); ev.append((r[1], -1))
    ev.sort()
    cur = mx = 0
    for _, d in ev:
        cur += d; mx = max(mx, cur)
    print("同时占用的中继时段峰值 = %d（中继无人机 %d 架）" % (mx, len(inst.d["rfleet"])))

    ss, bad = R.build_relay_sorties(inst, ch, meta, cand, inst.d["rtype"], 0.0)
    print("\n生成中继架次 %d 个，不可行项 %d" % (len(ss), len(bad)))
    for b in bad[:5]:
        print("   !", b)
    if ss:
        df = pd.DataFrame([dict(序号=s.rid, 无人机=s.drone, 能源组件=s.comp,
                                经度=round(s.lon, 6), 纬度=round(s.lat, 6),
                                悬停海拔_m=round(s.hover_alt, 1), 离地_m=round(s.agl, 1),
                                开始_s=round(s.t_start, 1), 建链完成_s=round(s.t_link, 1),
                                服务结束_s=round(s.t_end, 1), 返回_s=round(s.t_back, 1),
                                飞行能耗_kWh=round(s.e_fly, 4), 悬停通信能耗_kWh=round(s.e_hover, 4),
                                总能耗_kWh=round(s.e_total, 4), 返航SOC=round(100 * s.soc_end, 2),
                                充电_s=round(s.chg, 1)) for s in ss])
        print(df.to_string(index=False))
        df.to_excel(os.path.join(D.BASE, "results", "Q3_中继试算.xlsx"), index=False)
    print("\n总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
