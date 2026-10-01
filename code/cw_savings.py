# -*- coding: utf-8 -*-
"""
cw_savings.py —— 运输侧**文献启发式**基线：Clarke–Wright 节约算法（CW, 1964）

为什么需要它
------------
`results/基线与消融.json` 的 A 组目前只有「贪心构造 / ALNS / ALNS+局部搜索 /
ALNS+CP-SAT」四种，全部出自本文自己的算法族。审稿人会问：**换成教科书里那条
最经典的构造式启发式，结论还成立吗？** 本脚本补上这一格。

经典定义与本算例的对接
----------------------
Clarke–Wright 的节约值 $s_{ij}=d(0,i)+d(0,j)-d(i,j)$ 依赖「点对点 + 三角形」结构；
本问题的一架次是**多服务区巡回**（O01→若干服务区→O01）且含载重/体积/返航能量约束，
因此按 v1 的思路把它推广为**集合型节约**：

    save(A, B) = t(A) + t(B) − t(A ∪ B)

其中 $t(\\cdot)$ 是 `q2.route_metrics` 算出的作业时长（含装卸、绕行、爬升），
$A\\cup B$ 指两个架次的货箱合并后**重新求最优访问顺序**（`q2.best_route` 精确枚举）。
这与 CW 的「合并两条路线的端点到端点」是同一思想，只是把"端点距离"换成了
"整条巡回的时长"，因为本问题的成本函数就是时长。

算法
----
1. 初始解：每个货箱各自一架次（80 个单箱架次），机型取**能耗最低的可行者**；
2. 反复选取节约值最大、且合并后仍满足 载质量/体积/返航能量 的 (A, B, 机型) 组合；
3. 合并后把新架次放回池中，直到再无可行合并；
4. 逐权重组用**同一个** `q2.schedule_greedy` 排程，再用 `q2._metrics` 取同口径指标。

关键点：排程与评估函数与 ALNS 完全一致，因此这是**同台对照**，不是另一套口径。

输出：results/文献启发式对照.json + .md

用法：python cw_savings.py [--limit 80] [--alns-iters 600] [--alns-restarts 4]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time

import dcore as D
import q2 as Q

OUT = D.RESULTS


def singleton_sorties(inst, boxes):
    """初始解：每个货箱一架次，机型取能耗最低的可行机型（并列取载重裕度大的）。"""
    out = []
    for b in boxes:
        bx = inst.bidx[b]
        best = None
        for g in inst.types:
            s = Q.make_sortie(inst, g, {bx.sid: [b]})
            if s is None:
                continue
            key = (s.E, -inst.types[g].q_max)
            if best is None or key < best[0]:
                best = (key, s)
        if best is None:
            return None, b
        out.append(best[1])
    return out, None


def merge(sol, i, j, g):
    """把 sol[i] 与 sol[j] 的货箱并到机型 g 的同一架次；不可行返回 None。"""
    ab = {}
    for s in (sol[i], sol[j]):
        for a, bs in s.load.items():
            ab.setdefault(a, [])
            ab[a] = ab[a] + list(bs)
    m = Q.make_sortie(inst_global[0], g, ab)
    return m


def evaluate(inst, sol, w):
    """用与 ALNS 完全相同的排程与评估函数取指标。"""
    _, met, _, _ = Q.eval_solution(inst, sol, w, order_key="hs")
    return met


def cw(inst, boxes, verbose=True):
    """Clarke–Wright 节约算法（集合型），返回 (sol, n_merges, elapsed_s)。"""
    sol, bad = singleton_sorties(inst, boxes)
    if sol is None:
        raise RuntimeError("货箱 %s 连单箱架次都不可行" % bad)
    n0 = len(sol)
    merges = 0
    t0 = time.time()
    while True:
        best = None
        for i in range(len(sol)):
            for j in range(i + 1, len(sol)):
                ti, tj = sol[i].dur, sol[j].dur
                for g in inst.types:
                    m = merge(sol, i, j, g)
                    if m is None:
                        continue
                    save = ti + tj - m.dur
                    if save <= 1e-9:
                        continue
                    key = (-save, m.E)
                    if best is None or key < best[0]:
                        best = (key, save, i, j, m)
        if best is None:
            break
        _, save, i, j, m = best
        sol = [s for k, s in enumerate(sol) if k not in (i, j)] + [m]
        merges += 1
        if verbose and merges % 10 == 0:
            print("    已合并 %2d 次：架次 %d → %d" % (merges, n0, len(sol)))
    return sol, merges, time.time() - t0


inst_global = [None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alns-iters", type=int, default=600)
    ap.add_argument("--alns-restarts", type=int, default=4)
    ap.add_argument("--alns-tlimit", type=float, default=120.0)
    ap.add_argument("--no-alns", action="store_true",
                    help="只跑 CW，不重跑 ALNS 对照（默认两者都跑，保证同台同预算）")
    a = ap.parse_args()
    t0 = time.time()

    inst = Q.Instance()
    inst_global[0] = inst
    boxes = sorted(inst.bidx)
    print("货箱 %d 个，服务区 %d 个，机型 %d 种" % (len(boxes), len(inst.SIDS), len(inst.types)))

    print("\n=== Clarke–Wright 节约算法（集合型）===")
    sol_cw, n_m, el = cw(inst, boxes)
    print("  合并 %d 次：%d 个单箱架次 → %d 个架次（%.0f s）"
          % (n_m, len(boxes), len(sol_cw), el))

    rows = {}
    for w in Q.WEIGHTS:
        met = evaluate(inst, sol_cw, w)
        rows[w["name"]] = dict(met)
        print("  %-14s 架次=%2d 能耗=%7.2f kWh 完工=%7.0f s 加权延误=%9.0f 及时率=%.3f 硬违反=%.0f"
              % (w["name"], met["count"], met["energy"], met["makespan"],
                 met["tardiness"], met["ontime_rate"], met["hard_violation"]))

    alns_rows = {}
    if not a.no_alns:
        print("\n=== 同台对照：ALNS（同排程函数、同权重组）===")
        for w in Q.WEIGHTS:
            best = None
            for r in range(a.alns_restarts):
                s, obj, met, it = Q.alns(inst, w, seed=17 * r, iters=a.alns_iters,
                                         tlimit=a.alns_tlimit)
                if best is None or obj < best[0]:
                    best = (obj, met)
            obj, met = best
            alns_rows[w["name"]] = dict(met)
            print("  %-14s 架次=%2d 能耗=%7.2f kWh 完工=%7.0f s 加权延误=%9.0f 及时率=%.3f 硬违反=%.0f"
                  % (w["name"], met["count"], met["energy"], met["makespan"],
                     met["tardiness"], met["ontime_rate"], met["hard_violation"]))

    out = dict(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"),
        method=("Clarke–Wright savings, set-valued generalisation: "
                "save(A,B)=t(A)+t(B)-t(A∪B) on sortie durations, "
                "labels merged while capacity/volume/return-energy stay feasible"),
        n_boxes=len(boxes), n_merges=int(n_m),
        cw_sorties=len(sol_cw), start_sorties=len(boxes),
        cw_elapsed_s=round(el, 1),
        alns_budget=dict(iters=int(a.alns_iters), restarts=int(a.alns_restarts),
                         tlimit_s=float(a.alns_tlimit)),
        same_scheduler="q2.schedule_greedy + q2._metrics (identical to the ALNS runs)",
        rows_cw=rows, rows_alns=alns_rows,
        elapsed_s=round(time.time() - t0, 1))

    p = os.path.join(OUT, "文献启发式对照.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # Markdown 摘要
    L = []
    A = L.append
    A("# 运输侧文献启发式对照：Clarke–Wright 节约算法")
    A("")
    A("> 生成时间：%s。本表所有数字由 `code/cw_savings.py` 现算，"
      "排程与评估函数（`q2.schedule_greedy` + `q2._metrics`）与 ALNS 完全一致，"
      "因此是**同台对照**。" % out["generated"])
    A("")
    A("## 为什么用它")
    A("")
    A("此前的运输侧基线全部出自本文自己的算法族（贪心构造 / ALNS / 局部搜索 / CP-SAT），"
      "审稿人会问「换成教科书里最经典的构造式启发式还成立吗」。"
      "Clarke–Wright（1964）是该问题族最常被引用的构造式启发式，"
      "这里按其思想推广到多服务区巡回：`save(A,B)=t(A)+t(B)-t(A∪B)`。")
    A("")
    A("## 结果")
    A("")
    A("| 权重组 | 方法 | 架次 | 能耗 kWh | 完工 s | 加权延误 | 及时率 | 硬时限违反 s |")
    A("|---|---|---|---|---|---|---|---|")
    for w in Q.WEIGHTS:
        c = rows[w["name"]]
        A("| %s | Clarke–Wright | %d | %.2f | %.0f | %.0f | %.3f | %.1f |"
          % (w["name"], c["count"], c["energy"], c["makespan"], c["tardiness"],
             c["ontime_rate"], c["hard_violation"]))
        if w["name"] in alns_rows:
            r = alns_rows[w["name"]]
            A("| %s | ALNS | %d | %.2f | %.0f | %.0f | %.3f | %.1f |"
              % (w["name"], r["count"], r["energy"], r["makespan"], r["tardiness"],
                 r["ontime_rate"], r["hard_violation"]))
    A("")
    A("CW 的初始解是 %d 个单箱架次，合并 %d 次后得到 %d 个架次。" % (len(boxes), n_m, len(sol_cw)))
    A("")
    A("> ALNS 预算：%d 次迭代 × %d 次重启，时限 %.0f s/次；机器可复现见"
      "`results/文献启发式对照.json` 的 `alns_budget`。"
      % (a.alns_iters, a.alns_restarts, a.alns_tlimit))
    A("")
    p2 = os.path.join(OUT, "文献启发式对照.md")
    open(p2, "w", encoding="utf-8").write("\n".join(L))
    print("\n已写出：%s\n        %s（%.0f s）" % (p, p2, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
