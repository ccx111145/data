# -*- coding: utf-8 -*-
"""_front_matter.py —— 从 main.tex 抽出版 Editorial Manager 三段可直接粘贴的文本：
   标题 / 摘要（纯文本，计词数）/ 关键词（分号分隔）。

为什么单独抽：EM 的表单不能粘 LaTeX。摘要里 $...$ 数学、\\emph、\\cite 都要清掉，
且摘要栏有 500 词上限、关键词栏上限 6 个，必须**量过**再给。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")


def strip_tex(s: str) -> str:
    s = re.sub(r"\\emph\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\texttt\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\cite\{[^}]*\}", "", s)
    s = re.sub(r"\\ref\{[^}]*\}", "", s)
    s = re.sub(r"\\eqref\{[^}]*\}", "", s)
    s = re.sub(r"\$([^$]*)\$", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\{?", " ", s)
    s = re.sub(r"[{}\\]", " ", s)
    return " ".join(s.split())


def main() -> int:
    t = io.open(TEX, encoding="utf-8").read()

    # 标题：\title{...} 用花括号配对，含 \\ 换行
    key = "\\title{"
    i = t.find(key) + len(key)
    depth, j = 1, i
    while j < len(t) and depth:
        if t[j] == "{":
            depth += 1
        elif t[j] == "}":
            depth -= 1
        j += 1
    title = re.sub(r"\s+", " ", t[i:j - 1].replace("\\\\", " ").replace("\\bfseries", "")).strip()
    title = re.sub(r"[{}]", "", title)

    # 摘要
    a0 = t.index("\\begin{abstract}") + len("\\begin{abstract}")
    a1 = t.index("\\end{abstract}")
    abstract = strip_tex(t[a0:a1])

    # 关键词
    kw_m = re.search(r"Keywords:\s*(.*)", t)
    kws = [x.strip().rstrip(".;") for x in re.split(r"[;,]", kw_m.group(1))] if kw_m else []
    kws = [k for k in kws if k]

    print("=" * 78)
    print("TITLE")
    print("=" * 78)
    print(title)
    print()
    print("=" * 78)
    print("ABSTRACT  (%d words, limit 500)" % len(abstract.split()))
    print("=" * 78)
    print(abstract)
    print()
    print("=" * 78)
    print("KEYWORDS  (%d, limit 6) -- semicolon separated" % len(kws))
    print("=" * 78)
    print("; ".join(kws))
    return 0


if __name__ == "__main__":
    sys.exit(main())
