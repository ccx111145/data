# -*- coding: utf-8 -*-
"""q3run.py —— 中继调度驱动：最少区间覆盖 → 双机接力 → 生成并校验中继架次。"""
from __future__ import annotations

import time
import numpy as np

import dcore as D
import comm as C
import relay as R
import q3plan as PL
import q3dp as DP
import q3sched as S


def build_dat(inst, sol, assign, spacing=0.0040, pad=0.020, agl=(100.0, 300.0),
              split=6, verbose=True):
    """split: 候选池按全局覆盖率取前 1/split（兼顾多样性与规模）。"""
    link = C.Link(inst)
    T, P, K, tmax = PL.build_instances(inst, sol, assign, link)
    if len(T) == 0:
        return None
    cand, meta = R.candidate_grid(inst, P[:, 0], P[:, 1], spacing=spacing, pad=pad, agl=agl)
    cov, bh, acc = R.coverage_matrix(link, P, cand)
    if cov.sum(axis=1).min() == 0:
        raise RuntimeError("存在无候选点可覆盖的需求实例，请增大 pad 或增加悬停高度档位")
    dat = DP.prepare(inst, T, P, cand, cov, meta, per_cell=200)
    dat["T"], dat["P"], dat["K"], dat["link"] = T, P, K, link
    dat["cand"], dat["cov_all"] = cand, cov
    return dat


def plan(inst, sol, assign, verbose=True, spacing=0.0040, pad=0.020, agl=(100.0, 300.0),
         max_multi=3):
    t0 = time.time()
    dat = build_dat(inst, sol, assign, spacing, pad, agl, verbose=verbose)
    if dat is None:
        return dict(ok=True, sorties=[], msg="无通信缺口", T=np.zeros(0), P=np.zeros((0, 3)),
                    K=np.zeros(0, int))
    T, P, K = dat["T"], dat["P"], dat["K"]
    cells = dat["cells"]
    n = len(cells)
    if verbose:
        conc = max(len(g) for g in dat["groups"])
        print("  需求实例 %d，时间格 %d（同格最多 %d 架同时失联），候选点 %d，候选池 %d"
              % (len(T), n, conc, len(dat["cand"]), len(dat["pool"])))
    runs = S.single_runs(dat["alone"])
    chosen, fail = S.greedy_cover(dat["alone"], runs)
    if verbose:
        print("  独立可用时段 %d 个；单点覆盖区间 %d 个%s"
              % (len(runs), len(chosen), "" if fail is None else "（cell %d 起需多点）" % fail))
    intervals = [tuple(r) for r in chosen]
    covered = np.zeros(n, dtype=bool)
    for (i0, i1, j) in intervals:
        covered[i0:i1 + 1] = True
    k = 0
    multi = 0
    while k < n:
        if covered[k]:
            k += 1
            continue
        js = S.cover_cell(dat, k, max_k=max_multi)
        if js is None:
            return dict(ok=False, msg="cell %d (t=%.0f s) 需 %d 个以上悬停点同时保障"
                                      % (k, cells[k], max_multi), dat=dat, T=T, P=P, K=K)
        run = S.max_run_with(dat, k, js)
        intervals.append(run)
        covered[run[0]:run[1] + 1] = True
        multi += 1
        k = run[1] + 1
    intervals.sort(key=lambda r: r[0])
    # 合并同点相邻区间
    merged = []
    for r in intervals:
        if merged and len(r) == 3 and len(merged[-1]) == 3 and merged[-1][2] == r[2] \
                and r[0] <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], r[1], r[2])
        else:
            merged.append(r)
    if verbose:
        print("  覆盖区间 %d 个（多点配置 %d 个，合并后 %d 个）" % (len(intervals), multi, len(merged)))
    ss, bad = S.schedule(inst, dat, merged, verbose=verbose)
    eb = S.check_relay_energy(inst, ss)
    v = PL.verify(inst, T, P, K,
                  [dict(t_link_done=s["t_link_done"], t_end=s["t_end"], lon=s["lon"],
                        lat=s["lat"], hover_alt=s["hover_alt"]) for s in ss], link=dat["link"])
    if verbose:
        print("  中继架次 %d 个；调度告警 %d，能量告警 %d；逐实例校验未覆盖 %d / %d"
              % (len(ss), len(bad), len(eb), v["miss"], v["n"]))
        for b in (bad + eb)[:8]:
            print("    !", b)
    return dict(ok=(v["miss"] == 0 and not eb), sorties=ss, dat=dat, T=T, P=P, K=K,
                intervals=merged, schedule_warn=bad, energy_warn=eb, verify=v,
                summary=S.relay_energy_summary(inst, ss))


if __name__ == "__main__":
    import q2 as Q
    import cscan
    inst = Q.Instance()
    sol, pol = cscan.build_solution(inst, tlimit=20.0)
    r = plan(inst, sol, pol["assign"])
    print("ok=%s msg=%s" % (r["ok"], r.get("msg")))
    if r.get("sorties"):
        print(r["summary"])
        for s in r["sorties"]:
            print("  #%02d %s %s (%.5f,%.5f) 海拔%.0f 离地%.0f 建链%.0f 结束%.0f 返回%.0f E=%.3f SOC=%.1f%%"
                  % (s["rid"], s["drone"], s["comp"], s["lon"], s["lat"], s["hover_alt"], s["agl"],
                     s["t_link_done"], s["t_end"], s["t_back"], s["e_total"], 100 * s["soc"]))
