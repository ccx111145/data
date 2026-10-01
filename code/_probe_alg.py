# -*- coding: utf-8 -*-
"""_probe_alg.py —— 打印算法块里 caption 原文，排查移动匹配失败的原因。"""
from __future__ import annotations

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")


def strip_comments(t: str) -> str:
    out = []
    for line in t.split("\n"):
        idx = None
        for i, ch in enumerate(line):
            if ch == "%" and (i == 0 or line[i - 1] != "\\"):
                idx = i
                break
        out.append(line if idx is None else line[:idx])
    return "\n".join(out)


def find_blocks(t: str, env: str):
    clean = strip_comments(t)
    res = []
    for m in re.finditer(re.escape("\\begin{" + env + "}"), clean):
        close = "\\end{" + env + "}"
        j = clean.find(close, m.end())
        if j < 0:
            continue
        res.append((m.start(), j + len(close), t[:m.start()].count("\n") + 1))
    return res


def main() -> int:
    t = io.open(TEX, encoding="utf-8").read()
    clean = strip_comments(t)
    for i, (a, b, ln) in enumerate(find_blocks(t, "algorithm"), 1):
        seg = clean[a:b]
        cap = re.search(r"\\caption\{(.{0,120})", seg, re.S)
        print("#%d 行 %d" % (i, ln))
        print("   caption 原文: %r" % (cap.group(1) if cap else None))
        print("   含 'feasibility': %s" % ("feasibility" in seg))
        print("   含 'Co-design': %s" % ("Co-design" in seg))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
