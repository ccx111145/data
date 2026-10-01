# -*- coding: utf-8 -*-
"""_fix_cover.py —— 把投稿信里两处已被正文修正的过强表述改对，并补一段策略性定位。

背景：投稿信是在正文多轮修订**之前**写的，因此还留着正文已经撤掉的说法：
  * "decided infeasible ... by an unpruned state recursion" —— 正文已明确改成
    "在声明的候选集与声明的剪枝策略下未找到可行调度"，且无剪枝那次运行
    （1501 s CPU）并未终止。投稿信这样说等于把证据等级又抬回去，审稿人对照正文
    会认为是夸大。
  * "no value is typed by hand" —— 正文已给出完整例外清单，投稿信照旧会与正文冲突。
  * "the bibliography was machine-verified against Crossref" —— 改成可核验的说法
    （每条按 DOI 对照出版方记录）。
另外补一节 "How to read the evidence"，主动说明这是自建山地算例、并已逐项声明边界——
与其等审稿人发现，不如自己在投稿信里定位清楚。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = r"C:\Users\ASUS\Desktop\D题_投稿包"
TXT = os.path.join(DESK, "04_Cover_Letter.txt")


def main() -> int:
    if not os.path.exists(TXT):
        print("找不到投稿信：%s" % TXT)
        return 1
    t = io.open(TXT, encoding="utf-8").read()
    orig = t

    subs = [
        # (1) 证据等级：从"无剪枝判定"降为正文口径
        ("""A two-relay
      plan is then *decided* infeasible over a declared candidate set by an
      unpruned state recursion, and independently cross-checked by a
      phase-level integer program and by a sampling-free energy bound.""",
         """No two-relay
      schedule is then found over a declared candidate set by a state
      recursion, with the candidate set, the per-cell refinement and the
      pruning policy all stated; the verdict is cross-checked by a
      phase-level integer program and by a sampling-free energy bound, and
      Section VII records that closing the pruning did not terminate within
      our compute budget."""),

        # (2) 复现性：与正文的例外清单口径一致
        ("""no value is
      typed by hand.""",
         """no value is
      typed by hand except for the short list of declarations given in
      Section VII."""),

        # (3) 文献核验：改成可核验的说法
        ("the bibliography was machine-verified against Crossref.",
         "every bibliography entry was checked against its publisher record by DOI."),
    ]

    for old, new in subs:
        if old in t:
            t = t.replace(old, new, 1)
            print("OK   已替换：%s" % old.split("\n")[0][:52])
        else:
            print("MISS 未匹配：%s" % old.split("\n")[0][:52])

    # (4) 补一节策略性定位，放在 "Originality and ethics" 之前
    anchor = "  Originality and ethics."
    strat = """  How to read the evidence. Our results are established on a controlled
  mountainous instance built from a 30 m Copernicus DEM rather than on an
  established transportation benchmark, and we state the boundary of every
  claim in Section VII instead of leaving it implicit. Three consequences
  are worth flagging to the editor. First, the fleet-size answer is reported
  as an interval bracketed by a proven lower bound and a constructed
  schedule, never as a single "minimum". Second, every negative verdict is
  reported as a search result over a declared finite space, together with
  the pruning policy used, and the one run that would have removed that
  caveat consumed 1501 s of CPU without terminating and is shipped as a
  result file so that a reader can reproduce the non-termination. Third, the
  channel convention is not a detail: replacing the supplied constant
  occlusion penalty by ITU-R P.526 diffraction changes the smallest
  constructible fleet, so we report each fleet-size statement with its
  convention attached. We would rather the boundary be visible to a referee
  than discovered by one.

"""
    if anchor in t and "How to read the evidence" not in t:
        t = t.replace(anchor, strat + anchor, 1)
        print("OK   已补 'How to read the evidence' 一节")
    else:
        print("MISS 未能插入策略节（锚点缺失或已存在）")

    # (5) 页数信息补一行
    t = t.replace(
        "date: 2026-09-25",
        "date: 2026-09-25")  # 占位，若无匹配则无副作用
    if "page limit" not in t:
        t = t.replace(
            "  Thank you for your time and consideration.",
            "  Length. The manuscript is 15 pages in IEEE Transactions format, with\n"
            "  the auxiliary proofs and two pseudocode listings moved to the\n"
            "  supplementary material.\n\n"
            "  Thank you for your time and consideration.", 1)
        print("OK   已补页数说明")

    if t != orig:
        io.open(TXT, "w", encoding="utf-8").write(t)
        print("已写回 %s" % TXT)
    else:
        print("没有改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
