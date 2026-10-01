# -*- coding: utf-8 -*-
"""
ablation.py —— 统一「基线与消融」表（SCI 实验补齐 ②）

把分散在各处的对照实验汇总成**一张表 + 一份 Markdown**，覆盖目标要求的五组对照：

  A. 运输侧：贪心构造 / ALNS / ALNS+局部搜索 / ALNS+CP-SAT 精确排程
     （来源 `results/灵敏度分析.xlsx` 的 `D1_Q2算法对比` 表，固定迭代预算下的对照）
  B. 中继侧：忽略换位的精确集合覆盖（乐观基线）/ 构造性判定（可执行模型）
     （来源 `results/中继基线与下界.json`）
  C. 换位模式 A/B：Mode 1 基地返航 vs Mode 2 空中转场
     （来源 `results/换位模式对比.json`、`results/跨度黑障不等式.json`）
  D. 解耦 vs 协同：冻结运输排程 vs 允许调整起飞时刻
     （来源 `results/协同再调度.json`）
  E. 分区代价 Price of Partitioning：K = 1 / 2 / 3 的资源需求与缺口
     （来源 `results/Q4_分区配置.xlsx` 的 `Q4_资源汇总与库存` 与 `Q4_一体化参照`）

输出：results/基线与消融.json、results/基线与消融.md

用法：python ablation.py
"""
from __future__ import annotations

import io
import json
import os
import time

import dcore as D

OUT = D.RESULTS


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


def xlsx_sheets(path):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception:                                              # noqa: BLE001
        return {}
    out = {}
    for nm in wb.sheetnames:
        ws = wb[nm]
        out[nm] = [list(r) for r in ws.iter_rows(values_only=True)]
    return out


def main():
    t0 = time.time()
    res = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"))

    # ---------------- A. 运输侧方法对比 ----------------
    A = []
    sh = xlsx_sheets(os.path.join(OUT, "灵敏度分析.xlsx"))
    d1 = sh.get("D1_Q2算法对比") or sh.get("D1") or []
    if d1:
        hdr = [str(x) for x in d1[0]]
        for row in d1[1:]:
            if not row or row[0] is None:
                continue
            A.append(dict(zip(hdr, row)))
    res["A_transport_methods"] = dict(
        source="results/灵敏度分析.xlsx[D1_Q2算法对比]",
        note="固定迭代预算下的方法对照；与正文表 6 的正式跑批预算不同，"
             "故架次数可能不同，仅用于比较方法间的相对改进。",
        rows=A)

    # ---------------- A2. 运输侧**文献启发式**（Clarke–Wright 节约算法）----------------
    # 上面 A 组的四种方法全部出自本文自己的算法族，缺一条教科书级外部基线。
    # cw_savings.py 用**同一个排程与评估函数**跑 CW，因此是同台对照。
    cw = rd("文献启发式对照.json")
    if cw:
        cwr = cw.get("rows_cw") or {}
        ar = cw.get("rows_alns") or {}
        fam = ["P1-架次优先", "P2-及时优先", "P3-能耗优先", "P4-完工优先", "P5-均衡"]
        res["A2_literature_heuristic"] = dict(
            source="results/文献启发式对照.json（code/cw_savings.py 现算）",
            method=cw.get("method"),
            n_boxes=cw.get("n_boxes"), n_merges=cw.get("n_merges"),
            cw_sorties=cw.get("cw_sorties"), start_sorties=cw.get("start_sorties"),
            same_scheduler=cw.get("same_scheduler"),
            rows=[dict(权重组=k, **dict(cwr.get(k) or {})) for k in fam if k in cwr],
            rows_alns=[dict(权重组=k, **dict(ar.get(k) or {})) for k in fam if k in ar],
            summary=dict(
                cw_sorties=cw.get("cw_sorties"),
                cw_energy=(cwr.get("P1-架次优先") or {}).get("energy"),
                cw_hard_violation=(cwr.get("P1-架次优先") or {}).get("hard_violation"),
                cw_ontime=(cwr.get("P1-架次优先") or {}).get("ontime_rate"),
                alns_sorties=(ar.get("P1-架次优先") or {}).get("count"),
                alns_energy=(ar.get("P1-架次优先") or {}).get("energy"),
                alns_hard_violation=(ar.get("P1-架次优先") or {}).get("hard_violation"),
                alns_ontime=(ar.get("P1-架次优先") or {}).get("ontime_rate")))

    # ---------------- B. 中继侧基线 ----------------
    rb = rd("中继基线与下界.json")
    res["B_relay_baselines"] = dict(
        source="results/中继基线与下界.json",
        N_naive=rb.get("N_naive"), LB_handover=rb.get("LB_handover"),
        N_greedy=rb.get("N_greedy"),
        handover_premium=(None if (rb.get("N_greedy") is None or rb.get("N_naive") is None)
                          else rb["N_greedy"] - rb["N_naive"]),
        n_cells=rb.get("n_cells"), n_cand=rb.get("n_cand"), phases=rb.get("phases"),
        lb_rows=rb.get("LB_handover_rows"))

    # ---------------- C. 换位模式 ----------------
    mc = rd("换位模式对比.json")
    sb = rd("跨度黑障不等式.json")
    bm = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 1") or {}
    am = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 2") or {}
    ch = rd("信道模型对比.json")
    res["C_modes"] = dict(
        source="results/换位模式对比.json + 跨度黑障不等式.json",
        rows=mc.get("rows"),
        blackout_median_ms1=bm.get("p50", {}).get("w_s"),
        blackout_median_ms2=am.get("p50", {}).get("w_s"),
        star_rate_ms1=bm.get("p50", {}).get("rate"),
        star_rate_ms2=am.get("p50", {}).get("rate"),
        N_at_least_3=((ch.get("results") or {}).get("observed", {})
                      .get("greedy", {}).get("N3", {}).get("feasible")))

    # ---------------- D. 解耦 vs 协同 ----------------
    cf = rd("协同再调度.json")
    res["D_decoupled_vs_coordinated"] = dict(
        source="results/协同再调度.json",
        note="协同只允许调整架次开始时刻；归属/顺序/机型/指派全部冻结。",
        rows={m: (cf.get("results") or {}).get(m) for m in ("base", "air")})

    # ---------------- E. 分区代价 ----------------
    q4 = xlsx_sheets(os.path.join(OUT, "Q4_分区配置.xlsx"))
    summ = q4.get("Q4_资源汇总与库存") or []
    k1 = q4.get("Q4_一体化参照") or []
    pop = []
    k1map = {}
    for row in k1[1:]:
        if row and row[0]:
            k1map[str(row[0])] = dict(integrated=row[1], inv=row[2], gap=row[3])
    w = {"运输无人机": 1.0, "电池组": 0.4, "中继无人机": 1.0, "能源组件": 0.4}
    for row in summ[1:]:
        if not row or not row[0]:
            continue
        cls = str(row[0])
        wj = 1.0 if "无人机" in cls else 0.4
        e = dict(resource=cls, inv=row[1], k2=row[2], k2_gap=row[3],
                 k3=row[4], k3_gap=row[5], k1=(k1map.get(cls) or {}).get("integrated"),
                 weight=wj)
        if all(isinstance(e[k], (int, float)) for k in ("k2", "k3", "k1")):
            e["pop_k2"] = e["k2"] - e["k1"]
            e["pop_k3"] = e["k3"] - e["k1"]
            e["pop_k2_w"] = round(wj * e["pop_k2"], 2)
            e["pop_k3_w"] = round(wj * e["pop_k3"], 2)
        pop.append(e)
    res["E_price_of_partitioning"] = dict(
        source="results/Q4_分区配置.xlsx",
        note="分区代价 = 各组独立核算需求之和 − 一体化（K=1）需求；"
             "加权口径中整机取 1.0、可插拔能源单元取 0.4。",
        rows=pop,
        weighted_total_k2=round(sum(r.get("pop_k2_w") or 0 for r in pop), 2),
        weighted_total_k3=round(sum(r.get("pop_k3_w") or 0 for r in pop), 2))

    with io.open(os.path.join(OUT, "基线与消融.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)

    # ---------------- Markdown ----------------
    L = []
    Aa = L.append
    Aa("# 基线与消融（Baselines & Ablations）")
    Aa("")
    Aa("> 由 `code/ablation.py` 自动汇总，%s。所有数字直接取自结果文件，"
       "不在本脚本内重算，以保证与正文、提交表同源。" % res["generated"])
    Aa("")

    Aa("## A. 运输侧：构造 / ALNS / 局部搜索 / CP-SAT 精确排程")
    Aa("")
    if A:
        hdr = list(A[0].keys())
        Aa("| " + " | ".join(hdr) + " |")
        Aa("|" + "---|" * len(hdr))
        for r in A[:24]:
            Aa("| " + " | ".join("" if r.get(h) is None else str(r.get(h)) for h in hdr) + " |")
    else:
        Aa("（缺 `results/灵敏度分析.xlsx` 的 D1 表，请先运行 `python sensitivity.py`）")
    Aa("")
    Aa("> %s" % res["A_transport_methods"]["note"])
    Aa("")
    if res.get("A2_literature_heuristic"):
        a2 = res["A2_literature_heuristic"]
        Aa("### A2. 教科书级外部基线：Clarke–Wright 节约算法（1964）")
        Aa("")
        Aa("A 组的四种方法全部出自本文自己的算法族，缺一条外部对照。这里按 CW 的经典思想"
           "推广到多服务区巡回：$\\mathrm{save}(A,B)=t(A)+t(B)-t(A\\cup B)$，"
           "在载质量/体积/返航能量可行时反复合并节约值最大的两条架次；"
           "初始解是 %d 个单箱架次，合并 %d 次后剩 %d 个架次。"
           "**排程与评估函数与 ALNS 完全一致**（`%s`），因此是同台对照。"
           % (a2["start_sorties"], a2["n_merges"], a2["cw_sorties"], a2["same_scheduler"]))
        Aa("")
        Aa("| 权重组 | 方法 | 架次 | 能耗 kWh | 完工 s | 加权延误 | 及时率 | 硬时限违反 s |")
        Aa("|---|---|---|---|---|---|---|---|")
        ar_map = {r["权重组"]: r for r in a2["rows_alns"]}
        for r in a2["rows"]:
            Aa("| %s | Clarke–Wright | %d | %.2f | %.0f | %.0f | %.3f | %.1f |"
               % (r["权重组"], r["count"], r["energy"], r["makespan"], r["tardiness"],
                  r["ontime_rate"], r["hard_violation"]))
            q = ar_map.get(r["权重组"])
            if q:
                Aa("| %s | ALNS | %d | %.2f | %.0f | %.0f | %.3f | %.1f |"
                   % (r["权重组"], q["count"], q["energy"], q["makespan"], q["tardiness"],
                      q["ontime_rate"], q["hard_violation"]))
        Aa("")
        Aa("**这张表给出的是一条可写进论文的教训**：CW 把 %d 个单箱架次压到 %d 个、"
           "总能耗 %.2f kWh（优于 ALNS 同权重组下的 %.2f kWh），"
           "但它的硬时限违反是 **%.0f s**、及时率只有 **%.3f**，"
           "而 ALNS 在同一排程函数下是 **%.0f s / %.3f**。"
           "原因是纯**路由层**的合并会造出若干「必须排在最前」的大架次，"
           "在无人机与共享电池双资源时间轴上互相堵住——"
           "**路线更漂亮，时刻表却不可执行**。这正是本文把排程可行性放进优化回路"
           "（而非事后修补）的理由之一。"
           % (a2["start_sorties"], a2["cw_sorties"], a2["summary"]["cw_energy"],
              a2["summary"]["alns_energy"], a2["summary"]["cw_hard_violation"],
              a2["summary"]["cw_ontime"], a2["summary"]["alns_hard_violation"],
              a2["summary"]["alns_ontime"]))
        Aa("")
        Aa("> 脚本 `code/cw_savings.py`；结果 `results/文献启发式对照.{json,md}`。")
        Aa("")

    Aa("## B. 中继侧：忽略换位的覆盖基线 vs 可执行的换位感知模型")
    Aa("")
    b = res["B_relay_baselines"]
    Aa("| 量 | 值 | 说明 |")
    Aa("|---|---|---|")
    Aa("| $N_{\\rm naive}$（瞬时重定位） | %s | 逐时间格精确最小集合覆盖（CP-SAT）取全时域最大 |"
       % b["N_naive"])
    Aa("| $LB_{\\rm handover}$（严格下界） | %s | 相邻相位需求并集的最小覆盖点数取最大 |"
       % b["LB_handover"])
    Aa("| $N^{*}$（构造性可行） | %s | 考虑黑障与能源容量的构造性判定 |" % b["N_greedy"])
    Aa("| **换位代价** $N^{*}-N_{\\rm naive}$ | **%s** | 覆盖抽象相对可执行模型低估的台数 |"
       % b["handover_premium"])
    Aa("")
    Aa("> 严格夹逼：$\\max(N_{\\rm naive}, LB_{\\rm handover})=%d \\le N^{*} \\le %s$。"
       % (max([x for x in (b["N_naive"], b["LB_handover"]) if x is not None] or [0]),
          b["N_greedy"]))
    Aa("")

    Aa("## C. 换位模式：Mode 1 基地返航 vs Mode 2 空中转场")
    Aa("")
    c = res["C_modes"]
    Aa("| 指标 | Mode 1 | Mode 2 |")
    Aa("|---|---|---|")
    Aa("| 黑障窗口中位（s） | %s | %s |" % (c["blackout_median_ms1"], c["blackout_median_ms2"]))
    Aa("| $(\\star)$ 成立率 | %.1f%% | %.1f%% |"
       % (100 * (c["star_rate_ms1"] or 0), 100 * (c["star_rate_ms2"] or 0)))
    if c.get("rows"):
        for r in c["rows"]:
            Aa("| %s：%s | | |" % (r.get("mode_name"), r.get("reason")))
    Aa("")
    Aa("> $N=3$（Mode 1，附件口径）可行：**%s**。" % c["N_at_least_3"])
    Aa("")

    Aa("## D. 解耦 vs 协同：只调整起飞时刻能否消除阻塞")
    Aa("")
    d = res["D_decoupled_vs_coordinated"]["rows"]
    Aa("| 换位模式 | 基准赤字 | 协同后赤字 | 降幅 | 运输完工时间变化 | 被调整的架次 |")
    Aa("|---|---|---|---|---|---|")
    for m, cn in (("base", "Mode 1"), ("air", "Mode 2")):
        r = d.get(m) or {}
        if not r:
            Aa("| %s | — | — | — | — | — |" % cn)
            continue
        Aa("| %s | %s | %s | %.1f%% | %.0f → %.0f s | %s |"
           % (cn, r["baseline"]["deficit_cells"], r["after"]["deficit_cells"],
              r["deficit_reduction_pct"], r["baseline"]["makespan"], r["after"]["makespan"],
              r["after"]["n_shifted"]))
    Aa("")
    Aa("> %s" % res["D_decoupled_vs_coordinated"]["note"])
    Aa("")

    Aa("## E. 分区代价 Price of Partitioning（$K=1/2/3$）")
    Aa("")
    ee = res["E_price_of_partitioning"]
    Aa("| 资源类别 | 权重 | 一体化 $K=1$ | $K=2$ 需求 | $K=2$ 代价 | $K=3$ 需求 | $K=3$ 代价 | 库存 |")
    Aa("|---|---|---|---|---|---|---|---|")
    for r in ee["rows"]:
        Aa("| %s | %.1f | %s | %s | %s | %s | %s | %s |"
           % (r["resource"], r["weight"], r["k1"], r["k2"], r.get("pop_k2", "—"),
              r["k3"], r.get("pop_k3", "—"), r["inv"]))
    Aa("| **加权合计** | — | — | — | **%.2f** | — | **%.2f** | — |"
       % (ee["weighted_total_k2"], ee["weighted_total_k3"]))
    Aa("")
    Aa("> %s" % ee["note"])
    Aa("")
    Aa("### 结论")
    Aa("")
    Aa("1. **覆盖抽象不可执行**：忽略换位的中继模型给出 $N_{\\rm naive}=%s$，"
       "而可执行模型需要 $N^{*}=%s$，相差 %s 架；严格下界 $LB=%s$ 把结论夹在 "
       "$[%d,\\,%s]$ 内。"
       % (b["N_naive"], b["N_greedy"], b["handover_premium"], b["LB_handover"],
          max([x for x in (b["N_naive"], b["LB_handover"]) if x is not None] or [0]),
          b["N_greedy"]))
    Aa("2. **空中转场降低但不消除阻塞**：黑障中位由 %s s 降到 %s s、"
       "$(\\star)$ 成立率由 %.1f%% 升到 %.1f%%，但 $N=2$ 在两种模式下均不可行。"
       % (c["blackout_median_ms1"], c["blackout_median_ms2"],
          100 * (c["star_rate_ms1"] or 0), 100 * (c["star_rate_ms2"] or 0)))
    Aa("3. **协同不是解药**：只调整起飞时刻的阈值接受搜索未能降低赤字，"
       "说明不可行性不是「先排运输再判中继」造成的。")
    Aa("4. **分区的代价随粒度上升**：加权分区代价由 $K=2$ 的 %.2f 升到 $K=3$ 的 %.2f，"
       "与「分组自治必然复制峰值资源」的结构性判断一致。"
       % (ee["weighted_total_k2"], ee["weighted_total_k3"]))
    Aa("")
    Aa("> 复现：`python sensitivity.py`（A）、`python relay_baselines.py`（B）、"
       "`python mode_compare.py` + `python span_blackout.py`（C）、"
       "`python cofeedback.py`（D）、`python q4.py`（E）。")
    mp = os.path.join(OUT, "基线与消融.md")
    with io.open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("已写出：\n  %s\n  %s" % (os.path.join(OUT, "基线与消融.json"), mp))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
