# -*- coding: utf-8 -*-
"""_refcheck.py —— 核对审稿报告 16 条是否都已落地（用朴素子串，避免正则转义歧义）。"""
from __future__ import annotations

import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")

# (编号, 说明, 必须出现的子串 或 None, 必须消失的子串)
ITEMS = [
    ("M-1", "递推 M2 失败时刻改用 TairPP",
     "ENgrFailNTwoTairPP$\\,s under M2", None),
    ("M-1b", "不再把验证器时刻用于递推",
     None, "ENgrFailNTwoT$\\,s under M1 and $t=\\ENgrFailNTwoTair$"),
    ("M-2", "(C1) 明说无需轮流",
     "does \\emph{not} require the relays to take turns", None),
    ("M-2b", "证明不再断言交替",
     None, "the relays alternate and no two windows"),
    ("M-3", "不再误引 prop:W(iii)",
     None, "Proposition~\\ref{prop:W}(iii)"),
    ("M-3b", "点明 (iii) 是三角界",
     "it is \\emph{not} part (iii), which is the", None),
    ("M-4", "图题不再称递推为下界",
     None, "lower bounds of Proposition"),
    ("M-4b", "图题已改说法",
     "the recursion's first empty state is \\emph{not} a lower", None),
    ("M-5", "改为比较相位间隔",
     "gap between", None),
    ("M-5b", "相位长度上限已改对",
     "$3190$\\,s --- is not the binding quantity", None),
    ("M-6", "删除 earlier-draft 自注",
     None, "earlier draft"),
    ("M-7", "清除 for-this-revision 措辞",
     None, "for this revision"),
    ("m-1", "候选预算改名 b（与组数 K 区分）",
     "per-cell candidate budget $b$", None),
    ("m-2", "d_i 已在 Require 中定义",
     "$d_i$ for each sortie", None),
    ("m-3", "\\rm 全部改为 \\mathrm",
     None, "_{\\rm "),
    ("m-4", "fig:modes 已在正文引用",
     "Figure~\\ref{fig:modes}", None),
    ("m-5", "Proven 清单已补 prop:lb / prop:W",
     "Proposition~\\ref{prop:lb}", None),
    ("m-6", "D 的定义改为格口径",
     "Work in the cell convention", None),
    ("m-7", "Fisher-z 措辞已改",
     "by the Fisher $z$-transform", None),
    ("extra", "5400 这个错数字已清",
     None, "5400"),
]


def main() -> int:
    t = io.open(TEX, encoding="utf-8").read()
    bad = 0
    for tag, desc, must, mustnot in ITEMS:
        ok = True
        why = []
        if must and must not in t:
            ok = False
            why.append("缺少 %r" % must[:48])
        if mustnot and mustnot in t:
            ok = False
            why.append("仍存在 %r" % mustnot[:48])
        print("  %-7s %-34s %s%s" % (tag, desc, "OK" if ok else "**未落地**",
                                     "" if ok else "  <- " + "; ".join(why)))
        if not ok:
            bad += 1
    print()
    print("未落地 %d / %d" % (bad, len(ITEMS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
