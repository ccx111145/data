# -*- coding: utf-8 -*-
"""_xreflint.py —— 交叉引用体检：给出"定义了但从未被引用"的 label。

为什么要单独写：用正则扫 \\Dfig 抓 label 会被图注里的嵌套花括号带偏，
而 .aux 里的 \\newlabel 是 LaTeX 自己算出来的权威列表，直接读它最稳。
用法：python code/_xreflint.py
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_EN = os.path.join(BASE, "paper_en")


def main() -> int:
    src = io.open(os.path.join(PAPER_EN, "main.tex"), encoding="utf-8").read()
    i = src.find("\\begin{document}")
    body = src[i:] if i >= 0 else src

    aux = ""
    p = os.path.join(PAPER_EN, "main.aux")
    if os.path.exists(p):
        aux = io.open(p, encoding="utf-8").read()
    labels = set(re.findall(r"\\newlabel\{([^}]+)\}", aux))

    # 正文里的引用（\ref / \eqref / \autoref / \Cref）
    refs = set(re.findall(r"\\(?:ref|eqref|autoref|Cref|cref)\{([^}]+)\}", body))
    # \Dfig{name}{caption}{label}：label 是第 3 个必选参数
    for m in re.finditer(r"\\Dfig\b", body):
        rest = body[m.end():]
        args, k, depth, cur = [], 0, 0, None
        while k < len(rest) and len(args) < 3:
            ch = rest[k]
            if cur is None:
                if ch == "{":
                    depth, cur = 1, []
                k += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    args.append("".join(cur))
                    cur = None
            else:
                cur.append(ch)
            k += 1
        if len(args) == 3:
            labels.add(args[2].strip())

    missing = sorted(refs - labels)
    orphan = sorted(labels - refs)

    print("label 总数（含 \\Dfig 生成的）: %d" % len(labels))
    print("正文引用数                   : %d" % len(refs))
    print()
    print("引用了但不存在 : %s" % (missing or "无"))
    print()
    print("定义了但从未被引用 (%d):" % len(orphan))
    for o in orphan:
        print("   ", o)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
