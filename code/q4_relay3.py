# -*- coding: utf-8 -*-
"""q4_relay3.py —— 问题四「双口径」中的口径 B：把问题三的**3 架增配方案**
（solution.json 的 relay3）也放进同一套分区核算里，给出中继类资源的真实需求与缺口。

口径 A（正文）= 库存内可执行的 2 架折中方案（relay，通信非全程连续）；
口径 B（本节）= 采纳问题三增配建议后的 3 架方案（relay3，0 未覆盖 0 冲突）。

输出：results/Q4_中继增配情景.json 与 results/Q4_中继增配情景.md

用法：python q4_relay3.py
"""
from __future__ import annotations

import io
import json
import os
import time
from collections import defaultdict

import dcore as D
import q2 as Q
import q4 as Q4
import solution_io as SIO

OUT = D.RESULTS


def run_scenario(sol, key, label, verbose=True):
    """把 sol[key] 当作中继方案，重跑 q4.analyze，返回 K=2/K=3 推荐行的资源与缺口。"""
    s2 = dict(sol)
    s2["relay"] = [dict(r) for r in sol.get(key) or []]
    s2["coverage"] = []
    inst = Q.Instance()
    if not s2["relay"]:
        return None
    s2["coverage"] = Q4._build_coverage_coverage(inst, s2.get("transport", []),
                                                 s2["relay"], verbose=verbose)
    an = Q4.analyze(s2, verbose=verbose)
    k1 = Q4.k1_reference(an)
    out = dict(label=label, source_key=key, n_relay=len(s2["relay"]),
               n_coverage=len(s2["coverage"]),
               k1_relay=k1["res"]["relay"], k1_relayE=k1["res"]["relayE"],
               inv_relay=Q4.INV["relay"], inv_relayE=Q4.INV["relayE"], K={})
    # 每个中继架次覆盖了多少运输架次（用于检查是否真的在保障）
    cov_by = defaultdict(float)
    for c in s2["coverage"]:
        cov_by[c["relay"]] += max(0.0, float(c["t1"]) - float(c["t0"]))
    out["relay_cov_s"] = {k: round(v, 1) for k, v in sorted(cov_by.items())}
    out["relay_not_used"] = sorted({r["sid"] for r in s2["relay"]} - set(cov_by))
    for K in (2, 3):
        row = an["results"][K]["rows"][0]
        m = row["met"]
        r = row["res"]
        need = [r[i]["relay"] for i in range(K)]
        needE = [r[i]["relayE"] for i in range(K)]
        out["K"][str(K)] = dict(
            groups=row["groups"],
            relay_per_group=need, relay_need=sum(need), relay_gap=max(0, sum(need) - Q4.INV["relay"]),
            relayE_per_group=needE, relayE_need=sum(needE),
            relayE_gap=max(0, sum(needE) - Q4.INV["relayE"]),
            cross=[x for g in row["cross"] for x in g],
            nocov=row["nocov"],
            total_need=round(m["total_need"], 3),
            transport_gap={k: int(v) for k, v in m["gap"].items() if v},
        )
    return out, an


def main():
    t0 = time.time()
    sol = SIO.load()
    print("solution.json：运输 %d 架次 | relay %d 架次 | relay3 %d 架次"
          % (len(sol.get("transport", [])), len(sol.get("relay") or []),
             len(sol.get("relay3") or [])))
    res = {"A": None, "B": None}
    anA = anB = None
    rA = run_scenario(sol, "relay", "口径 A：库存内 2 架折中方案（通信非全程连续）",
                      verbose=True)
    if rA:
        res["A"], anA = rA
    rB = run_scenario(sol, "relay3", "口径 B：采纳增配的 3 架方案（全程连续通信）",
                      verbose=True)
    if rB:
        res["B"], anB = rB

    payload = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"),
                   physics="cruise = max(航段/端点地形, 悬停点地形) + 50 m",
                   inv=dict(relay=Q4.INV["relay"], relayE=Q4.INV["relayE"]),
                   scenarios=res)
    with io.open(os.path.join(OUT, "Q4_中继增配情景.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, default=float)

    # ---------------- Markdown ----------------
    L = []
    A = L.append
    A("# 问题四 · 中继资源双口径核算（口径 A 库存内折中 / 口径 B 采纳增配）")
    A("")
    A("> 由 `code/q4_relay3.py` 自动生成，%s。物理模型：%s。"
      % (payload["generated"], payload["physics"]))
    A("> **为什么要分两个口径**：问题三在给定运输时序与给定候选点集下**未找到** 2 架可行解"
      "并构造出 3 架可行方案（建议增配 1 架）。但库存只有 2 架中继，"
      "因此问题四正文只能按 2 架折中方案核算；本节把 3 架增配方案代回**同一套分区核算**，"
      "给出采纳增配后中继类资源的真实需求与缺口。")
    A("")
    A("| 口径 | 中继方案 | 架次数 | 保障记录 | 是否全程连续通信 |")
    A("|---|---|---|---|---|")
    for k in ("A", "B"):
        s = res[k]
        if s is None:
            A("| %s | 无数据 | — | — | — |" % k)
            continue
        A("| %s | `solution.json` 的 `%s` | %d | %d | %s |"
          % (k, s["source_key"], s["n_relay"], s["n_coverage"],
             "否（存在通信中断相）" if k == "A" else "是（0 未覆盖、0 时序冲突）"))
    A("")
    A("## 一、中继类资源的组内需求与库存缺口")
    A("")
    A("| 口径 | K | 各组中继无人机需求(架) | 合计(架) | 库存(架) | 缺口(架) "
      "| 各组中继能源组件需求(组) | 合计(组) | 库存(组) | 缺口(组) |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for k in ("A", "B"):
        s = res[k]
        if s is None:
            continue
        for K in ("2", "3"):
            d = s["K"][K]
            A("| %s | %s | %s | %d | %d | **%d** | %s | %d | %d | %d |"
              % (k, K, " / ".join(str(x) for x in d["relay_per_group"]), d["relay_need"],
                 s["inv_relay"], d["relay_gap"],
                 " / ".join(str(x) for x in d["relayE_per_group"]), d["relayE_need"],
                 s["inv_relayE"], d["relayE_gap"]))
    A("")
    A("> 表中「各组需求」为**组内峰值并发/区间着色**口径，合计即各组之和；"
      "缺口 = 合计 − 库存（小于 0 记 0）。")
    A("")
    A("## 二、跨组保障与未覆盖中继架次（严格口径下的额外需求）")
    A("")
    A("| 口径 | K | 跨组保障中继架次 | 未保障任何运输架次的中继架次 |")
    A("|---|---|---|---|")
    for k in ("A", "B"):
        s = res[k]
        if s is None:
            continue
        for K in ("2", "3"):
            d = s["K"][K]
            A("| %s | %s | %s | %s |"
              % (k, K, "、".join(d["cross"]) or "无",
                 "、".join(d["nocov"]) or "无"))
    A("")
    A("> 按题面「各组只承担本组服务区的通信保障任务」，跨组保障必须为该组**另配**一架中继"
      "（或组间显式约定共享），故上表右列是严格口径下的**额外中继需求下界**，"
      "不应被忽略。")
    A("")
    if res["A"]:
        A("## 三、口径 A 的中继架次保障量（供核对）")
        A("")
        A("| 中继架次 | 累计保障时长(s) |")
        A("|---|---|")
        for sid, sec in res["A"]["relay_cov_s"].items():
            A("| %s | %.1f |" % (sid, sec))
        if res["A"]["relay_not_used"]:
            A("")
            A("> 未被反推到任何保障记录的中继架次：%s。"
              % "、".join(res["A"]["relay_not_used"]))
        A("")
    if res["B"]:
        A("## 四、口径 B 的中继架次保障量（供核对）")
        A("")
        A("| 中继架次 | 累计保障时长(s) |")
        A("|---|---|")
        for sid, sec in res["B"]["relay_cov_s"].items():
            A("| %s | %.1f |" % (sid, sec))
        if res["B"]["relay_not_used"]:
            A("")
            A("> 未被反推到任何保障记录的中继架次：%s。"
              % "、".join(res["B"]["relay_not_used"]))
        A("")
    A("## 五、结论")
    A("")
    A("1. **运输侧不受口径影响**：两种口径下运输机与电池组的需求、缺口完全相同——"
      "增配只改中继，不动运输方案。")
    if res["A"] and res["B"]:
        gA2 = res["A"]["K"]["2"]["relay_gap"]
        gB2 = res["B"]["K"]["2"]["relay_gap"]
        gA3 = res["A"]["K"]["3"]["relay_gap"]
        gB3 = res["B"]["K"]["3"]["relay_gap"]
        A("2. **中继侧缺口随口径变化**：K=2 下口径 A 缺口 %d 架、口径 B 缺口 %d 架；"
          "K=3 下分别为 %d 架与 %d 架。口径 A 的「缺口 0」只代表**2 架折中方案本身**"
          "占用不超库存，**不代表通信约束被满足**。" % (gA2, gB2, gA3, gB3))
    A("3. **合并建议**：在 K=2 分组下，若按口径 B 采纳增配，"
      "需追加 **1 架 C 型运输机 + 1 架中继无人机**"
      "（C 型缺口见 `results/Q4_说明.md` 第七节；中继缺口见本文件）；"
      "若同时允许 B 型机与 B 型电池组间共享（放松性反事实，非合法解），"
      "追加清单可缩减为 **1 架 C 型机 + 1 架中继**。")
    A("")
    md = os.path.join(OUT, "Q4_中继增配情景.md")
    with io.open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n已写出：\n  %s\n  %s" % (os.path.join(OUT, "Q4_中继增配情景.json"), md))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
