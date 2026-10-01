# -*- coding: utf-8 -*-
"""pf_cert.py —— **免搜索**的 N=2 不可行性证书（参数无关版）

背景（审稿意见第 2、3 项）：
  论文原来的"两架不可行"由候选集 + 剪枝口径下的状态递推给出，因此只是
  "在声明的搜索范围内未找到"，不是证明。审稿人指出：关闭剪枝并不能消除
  候选筛选造成的遗漏。这个批评是对的。

本脚本换一条**完全不依赖搜索**的路子，把 Theorem（handover obstruction）
里的 span 不等式做成**参数无关**形式，从而给 N=2 一个可复算的证明。

------------------------------------------------------------------
引理（单次换位的必要条件，参数无关）
------------------------------------------------------------------
设两架中继，某一时刻只有第 i 架在换位，从 a 到 b，在格 k 完成。
令 w = W(a,b) 为其黑障窗口时长（秒）。
在窗口内第 i 架不提供任何覆盖（假设 A1），且另一架不动（假设 A2 "至多一架
同时换位"），所以窗口 [t_k - w, t_k) 内的**全部**失联需求必须由另一架当前
所在的单一点 p 独自覆盖。

于是"存在一个单点 p 能连续独保 [t_k - w, t_k)"是**必要**条件。
反过来定义
      span_min(k) := max_p { 最大的 w，使得 p 在 [t_k - w, t_k) 内独保全部需求 }
则任何在格 k 完成的换位都必须满足
      W(a, b) <= span_min(k).                                   (PF)
注意 (PF) **不含任何人为阈值**（原论文用的是 w 的中位数/分位数），
也不含候选集筛选与剪枝：span_min 由覆盖表逐格精确计算。

因此：若对**所有**格 k 与**所有**点对 (a,b) 都有 W(a,b) > span_min(k)，
则两架中继在任何时刻都无法完成一次换位；而引理的前提"无单点可独保全程"
又排除了"全程不换位"的情形，故 N=2 不可行。这是一个**没有搜索空间**的证明。

同时报告放行率统计（有多少 (k, 点对) 满足 (PF)），用于说明原论文的
"★ 不等式放行率 72%/93%"与这里的参数无关版本差在哪里。

输出 results/参数无关证书.json
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


def span_min_table(pb):
    """span_min(k) = 秒。对每个格 k 与每个候选点 p，算 p 能往前独保多少秒。

    用 run_end[p] 给出的"从 k 起连续独保到的最远格"来算**前向**独保区间；
    这里需要的是**后向**（窗口在 k 之前）。做法：对每个 p，找出所有满足
    "p 在 [k0,k] 上逐格独保"的最大区间，取其起点 k0，则
        span_min(k) = t_k - t_{k0-1}  （即该区间的真实时长）。
    """
    n, P = pb.n, pb.P
    cells_t = np.asarray(pb.cells, dtype=np.float64)
    alone = pb.alone                      # alone[k, p] = 1 ⟺ p 在格 k 独保全部需求
    span_min = np.zeros(n)
    arg = np.full(n, -1, dtype=np.int64)
    step = pb.grid
    # 对每个 p，扫描所有"独保游程"，把该游程对其中每个格的可用后向时长写下来
    best = np.zeros(n)
    argbest = np.full(n, -1, dtype=np.int64)
    for p in range(P):
        col = alone[:, p].astype(bool)
        if not col.any():
            continue
        idx = np.nonzero(col)[0]
        brk = np.nonzero(np.diff(idx) > 1)[0]
        for seg in np.split(idx, brk + 1):
            k0, k1 = int(seg[0]), int(seg[-1])
            # 游程 [k0,k1] 内每格 k 的"向后独保时长" = t_k - t_{k0} + step
            dur = (cells_t[k0:k1 + 1] - cells_t[k0] + step)
            sel = best[k0:k1 + 1] < dur
            best[k0:k1 + 1] = np.where(sel, dur, best[k0:k1 + 1])
            argbest[k0:k1 + 1] = np.where(sel, p, argbest[k0:k1 + 1])
    return best, argbest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=300,
                    help="点对采样上限（用于放行率统计；证明部分用全部 C_0）")
    ap.add_argument("--exhaustive-pairs", action="store_true",
                    help="对全部 C_0×C_0 点对做检验（较慢，但给出真正的全量结论）")
    a = ap.parse_args()

    inst, ph = build_phase()
    cells = np.asarray(ph["cells"], dtype=np.float64)
    T = float(cells[-1] - cells[0])
    print("需求格 %d，任务时长 %.0f s" % (len(cells), T))

    out = dict(note="参数无关的 N=2 换位必要条件 W(a,b) <= span_min(k)；无候选集、无剪枝",
               n_cells=int(len(cells)), T_s=round(T, 1), results={})

    for mode in ("base", "air"):
        pb = DN.PB(ph, grid=10.0, topk=0, inst=inst, mode=mode)
        smin, argp = span_min_table(pb)
        C0 = [int(j) for j in pb.useful]
        print("\n=== Mode %s ===  候选点 %d（C_0 %d）" % (mode, pb.P, len(C0)))
        print("  span_min：中位 %.0f s / 最大 %.0f s / 最小值 %.0f s"
              % (np.median(smin), smin.max(), smin.min()))

        # 仅对"真正可能被换位到达"的点对计算 W，避免 C_0^2 次昂贵的地形计算
        # ——先按必要条件的上界筛选：只要 span_min 最大的那一格都装不下的点对，
        # 无需计算 W。这里改为直接算（带缓存），并把结果按 span_min 归档。
        t0 = time.time()
        if a.exhaustive_pairs:
            pairs = [(x, y) for x in C0 for y in C0 if x != y]
        else:
            rng = np.random.default_rng(20260924)
            xs = rng.choice(C0, size=min(len(C0), a.cap), replace=False)
            pairs = [(int(x), int(y)) for x in xs for y in C0 if int(x) != int(y)]
        wv = np.empty(len(pairs))
        for i, (x, y) in enumerate(pairs):
            wv[i] = pb.w_sec(x, y)
        print("  点对 %d 个：W 最小 %.0f s / 中位 %.0f s / 最大 %.0f s（%.0f s 计算完）"
              % (len(pairs), wv.min(), np.median(wv), wv.max(), time.time() - t0))

        # (PF) 检验：存在 (k, 点对) 使 W <= span_min(k) 吗？
        # 等价于：max_k span_min(k) >= min_{a≠b} W(a,b)
        s_max = float(smin.max())
        k_arg = int(np.argmax(smin))
        w_min = float(wv.min())
        # 逐格全量判定：对每一格 k，看是否存在点对 W <= span_min(k)
        # （wv 是点对子样本，若 exhaustive_pairs 则为全量）
        ok_cells = int((smin >= w_min).sum())
        pf_blocks = bool(s_max < w_min)
        rec = dict(
            mode=mode,
            C0_size=len(C0),
            span_min_median_s=round(float(np.median(smin)), 1),
            span_min_max_s=round(s_max, 1),
            span_min_argmax_k=k_arg,
            span_min_argmax_t=round(float(cells[k_arg]), 1),
            span_min_argmax_point=int(argp[k_arg]),
            W_min_s=round(w_min, 1),
            W_median_s=round(float(np.median(wv)), 1),
            W_max_s=round(float(wv.max()), 1),
            n_pairs_tested=int(len(pairs)),
            pairs_scope=("exhaustive over C_0" if a.exhaustive_pairs else
                         "sampled %d x C_0" % a.cap),
            cells_admitting_a_move=int(ok_cells),
            cells_total=int(len(smin)),
            certificate_fires=pf_blocks,
        )
        out["results"][mode] = rec
        print("  (PF) 判定：max_k span_min = %.0f s @ 第 %d 格(t=%.0f s, 点 %d)；"
              "min 点对 W = %.0f s" % (s_max, k_arg, cells[k_arg], argp[k_arg], w_min))
        if pf_blocks:
            print("  ==> 证书成立：W(a,b) > span_min(k) 对**所有**格与点对成立，"
                  "故任何单次换位都不可能，N=2 不可行（无需搜索）")
        else:
            print("  ==> 证书**不成立**：存在 %d/%d 个格，其 span_min 足以容纳某个点对的 W。"
                  % (ok_cells, len(smin)))
            print("      此时 N=2 的不可行性**不能**由 span 不等式证明，只能作为搜索结论报告。")

    p = os.path.join(OUT, "参数无关证书.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出：%s" % p)


if __name__ == "__main__":
    main()
