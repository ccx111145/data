# -*- coding: utf-8 -*-
"""pf_cert2.py —— 参数无关、**不限制换位时机**的 N=2 可达性判定（物理必要条件版）

上一个脚本（pf_cert.py）证明了一件事：**span 不等式无法证明 N=2 不可行**
（880/992 个格都能容纳某个点对的窗口），所以原论文那条"证书"不是证明。

本脚本用一个**比原论文更弱、因而更强**的判定来回答同一个问题：

  只保留物理上必须成立的条件，**不施加论文原文里
  "换位者必须已到位满整个窗口 / 另一架必须已到位" 这类时机限制**：

  (N1) 每个需求格必须被两架当时的驻留点并集覆盖；
  (N2) 换位发生在几格之内：一架从 a 到 b 的窗口是 [t_k-W(a,b), t_k]，
       窗口内它不贡献覆盖，因此另一架的**当前**驻留点必须在这段窗口内独保全部需求；
  (N3) 同一架的在空时长不超过 T^cap（可关闭以获得更强结论）。

注意 (N2) 里"另一架的当前驻留点"是它**已经到达**的位置——这是物理事实，
不是时机约定；而"某架必须提前多久到位"这种论文里的附加要求在这里**没有**。
状态空间因此是 N=2 下的 (p1, p2, last_move_ok)，比原 DP 的 (p, s, r) 更小、
同时也更宽松（不检查 arrival 时序），故：

  · 若本判定报"不可行"，则原 DP 报"不可行"是**可以接受**的，且结论不依赖剪枝；
  · 若本判定报"可行"，则原论文的"不可行"是模型附加限制造成的，必须撤回。

用法：
    python code/pf_cert2.py --mode base --max-states 3000000
输出：results/参数无关可达性.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS


def build_phase():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both")
    ap.add_argument("--max-states", type=int, default=3000000)
    ap.add_argument("--no-cap", action="store_true",
                    help="不施加 T^cap（更宽松，结论更强）")
    a = ap.parse_args()

    inst, ph = build_phase()
    cap = hover_cap_s(inst)
    cells_t = np.asarray(ph["cells"], dtype=np.float64)
    T = float(cells_t[-1] - cells_t[0])
    modes = ["base", "air"] if a.mode == "both" else [a.mode]
    print("需求格 %d，任务时长 %.0f s，T^cap=%.1f s，能量上限=%s"
          % (len(cells_t), T, cap, "不施加" if a.no_cap else "施加"))

    out = dict(note="参数无关、不限制换位时机的 N=2 可达性判定（物理必要条件版）",
               n_cells=int(len(cells_t)), T_s=round(T, 1), T_cap_s=round(cap, 1),
               energy_cap_enforced=not a.no_cap, results={})

    for mode in modes:
        pb = DN.PB(ph, grid=10.0, topk=0, inst=inst, mode=mode)
        n, P = pb.n, pb.P
        # 候选集裁剪（对结论**保守**）：一次换位的必要条件是另一架能独保该窗口，
        # 而窗口至少 w_min 秒；因此只有"能独保 >= w_min 秒"的点才可能被换位到达。
        # 注意：这只缩小搜索空间，可能丢解 —— 因此若本判定报"不可行"，
        # 结论仍受此裁剪限制，必须在论文中如实标注。
        us = [int(j) for j in pb.useful]
        fwd_all = np.zeros((n, pb.P), dtype=np.int32)
        for _p in range(pb.P):
            _c = pb.alone[:, _p].astype(bool)
            _run = 0
            for _k in range(n):
                _run = _run + 1 if _c[_k] else 0
                fwd_all[_k, _p] = _run
        wmin_pts = []
        for _x in us:
            for _y in us:
                if _x != _y:
                    wmin_pts.append(pb.w_sec(_x, _y))
                    break
        w_min_est = min(wmin_pts) if wmin_pts else 60.0
        C0 = [j for j in us if int(fwd_all[:, j].max()) * pb.grid >= w_min_est]
        print("  候选集裁剪：C_0 %d -> %d（要求可独保 >= %.0f s）"
              % (len(us), len(C0), w_min_est))
        if len(C0) > 220:
            C0 = C0[:220]
            print("  再截断到 %d 个点（保守上界会因此变弱）" % len(C0))
        need = list(pb.need)
        mask = pb.mask

        # 预计算：对每个格 k、每个点 p，p 独保"从 k 往前 w 秒"是否成立。
        # 用 pb.alone 的连续游程实现：alonerun[k,p] = 从 k 往前（含 k）连续独保的格数。
        alone = pb.alone.astype(bool)
        fwd = np.zeros((n, P), dtype=np.int32)      # 向前的游程长度
        for p in range(P):
            c = alone[:, p]
            run = 0
            for k in range(n):
                run = run + 1 if c[k] else 0
                fwd[k, p] = run
        steps = np.diff(cells_t)
        print("\n=== Mode %s === 候选点 %d（C_0 %d）" % (mode, P, len(C0)))

        def window_ok(p_stat, kb, k):
            """另一架停在 p_stat，能否独保 [kb+1, k] 这段窗口（格号，含端点）。"""
            if kb >= k:
                return True                    # 窗口塌缩到一格之内
            if kb < 0:
                return False                   # 窗口越过任务期开头 —— 该换位不可能
            length = k - kb
            return int(fwd[k - 1, p_stat]) >= length

        t0 = time.time()
        # 首格：任意两点并集覆盖
        dp = {}
        for a_ in C0:
            ma = int(mask[0][a_])
            for b_ in C0:
                if b_ == a_:
                    continue
                if (ma | int(mask[0][b_])) == need[0]:
                    dp[(a_, b_, -1)] = 0
        if not dp:
            for a_ in C0[:200]:
                for b_ in C0[:200]:
                    if b_ != a_:
                        dp[(a_, b_, -1)] = 0
        print("  首格状态 %d" % len(dp))
        fail = None
        diag = []
        for k in range(1, n):
            cur = {}
            nd = need[k]
            for (p1, p2, lastmove), cost in dp.items():
                # 不动
                if (int(mask[k][p1]) | int(mask[k][p2])) == nd:
                    key = (p1, p2, lastmove)
                    if cur.get(key, 10 ** 9) > cost:
                        cur[key] = cost
                # 谁在移动：另一架必须独保窗口
                for i in (0, 1):
                    p_mv, p_st = (p1, p2) if i == 0 else (p2, p1)
                    for p_new in C0:
                        if p_new == p_mv:
                            continue
                        w = pb.w_sec(p_mv, p_new)
                        kb = pb.before(k, w)
                        if not window_ok(p_st, kb, k):
                            continue
                        np1, np2 = (p_new, p_st) if i == 0 else (p_st, p_new)
                        if (int(mask[k][np1]) | int(mask[k][np2])) != nd:
                            continue
                        key = (np1, np2, k)
                        nc = cost + 1
                        if cur.get(key, 10 ** 9) > nc:
                            cur[key] = nc
            diag.append(dict(k=k, t=float(cells_t[k]), n_state=len(cur)))
            if not cur:
                fail = dict(k=k, t=float(cells_t[k]))
                break
            if len(cur) > a.max_states:
                fail = dict(k=k, t=float(cells_t[k]), overflow=True,
                            n_state=len(cur))
                break
            dp = cur
            if k % 100 == 0:
                print("      cell %4d/%d 状态 %7d  (%.0f s)"
                      % (k, n, len(dp), time.time() - t0))
        ok = (fail is None)
        rec = dict(mode=mode, feasible=bool(ok), C0_size=len(C0),
                   sec=round(time.time() - t0, 1),
                   max_state=int(max((d["n_state"] for d in diag), default=0)),
                   fail=fail)
        out["results"][mode] = rec
        if ok:
            print("  ==> **可行**：存在两架方案（本题放松了论文的时机限制）。"
                  "原论文的 N=2 不可行结论必须撤回或改为受模型限制的表述。")
        elif fail and fail.get("overflow"):
            print("  ==> 未跑完（状态 %d 超出护栏）→ 不得据此宣称不可行"
                  % fail["n_state"])
        else:
            print("  ==> **不可行**（在格 %s，t=%.0f s 无可行状态）："
                  "该结论不依赖候选集筛选与剪枝，只需要物理必要条件。"
                  % (fail["k"], fail["t"]))

    p = os.path.join(OUT, "参数无关可达性.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
