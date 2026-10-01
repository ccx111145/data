# -*- coding: utf-8 -*-
"""_extract_fig_labels.py —— 从 make_figs.py 抽出"会画到图上"的中文字符串。

只保留传给 text/title/label/legend/annotate/set_xticklabels 等绘图 API 的字面量，
以及 ax.text(...) 的位置参数；错误提示、日志、pandas 列名一律排除。
输出一张 待翻译 清单，便于一次性建立 中文->英文 映射。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "code", "make_figs.py")

# 会渲染文字的调用
API = ("set_title", "set_xlabel", "set_ylabel", "set_xticklabels",
       "set_yticklabels", "legend", "text", "annotate", "suptitle",
       "set_label", "figtext")

CJK = re.compile(r"[\u4e00-\u9fff]")
STR = re.compile(r"""(["'])((?:\\.|(?!\1).)*?)\1""")


def main() -> int:
    t = io.open(SRC, encoding="utf-8").read()
    lines = t.split("\n")
    out = []
    for i, ln in enumerate(lines, 1):
        if not any(a in ln for a in API):
            continue
        for m in STR.finditer(ln):
            s = m.group(2)
            if CJK.search(s):
                out.append((i, s))
    # 去重且保序
    seen = set()
    uniq = []
    for ln, s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append((ln, s))
    print("需要翻译的图上文字 %d 条：" % len(uniq))
    for ln, s in uniq:
        print("  %-5d %s" % (ln, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
