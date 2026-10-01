# -*- coding: utf-8 -*-
"""_probe_blocks.py —— 列出 main.tex 里所有 proof / algorithm 块的行号、字符数与归属标签。

用花括号配对而不是贪婪正则：正则 \begin{proof}.*?\end{proof} 会被注释里的
"proof}" 之类文本带偏，且 proof 内部还有嵌套环境。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")

BEGIN = "\\begin{"
END = "\\end{"


def find_blocks(t: str, env: str):
    """返回 [(start, end_of_block, line_no), ...]，按出现顺序。"""
    out = []
    pat = re.compile(re.escape(BEGIN + env + "}"))
    for m in pat.finditer(t):
        close = END + env + "}"
        j = t.find(close, m.end())
        if j < 0:
            continue
        out.append((m.start(), j + len(close), t[:m.start()].count("\n") + 1))
    return out


def owner_label(t: str, pos: int) -> str:
    """往回找最近的 \\label{...}，用来判断这段证明属于哪个命题。"""
    back = t[:pos]
    labs = re.findall(r"\\label\{([^}]+)\}", back)
    return labs[-1] if labs else "?"


def main() -> int:
    t = io.open(TEX, encoding="utf-8").read()
    body_at = t.find("\\begin{document}")
    body_len = len(t) - body_at

    print("正文字符数: %d" % body_len)
    print()
    for env in ("proof", "algorithm"):
        print("=== %s 块 ===" % env)
        tot = 0
        for i, (a, b, ln) in enumerate(find_blocks(t, env), 1):
            n = b - a
            tot += n
            head = re.sub(r"\s+", " ", t[a:a + 70])[len(BEGIN) + len(env) + 1:]
            print("  #%-2d 行 %-5d %5d 字符  属: %-22s %s"
                  % (i, ln, n, owner_label(t, a), head[:34]))
        print("  合计 %d 字符 (%.1f%% 正文)" % (tot, 100.0 * tot / body_len))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
