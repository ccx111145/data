# -*- coding: utf-8 -*-
"""_check_overlap.py —— 检测插图内文字是否互相重叠（截图里"糊成一片"的量化判据）。

判据：同一页里两个文本 span 的包围盒面积重叠率 > 35% 即判为碰撞。
不做重叠检测的话，只能靠人眼看截图——这次就是截图才发现的。

用法：python code/_check_overlap.py [pdf路径]
"""
from __future__ import annotations

import os
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "paper_en", "build", "main_elsarticle.pdf")

THRESH = 0.35


def inter(a, b) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def main() -> int:
    doc = fitz.open(PDF)
    total = 0
    for i, pg in enumerate(doc, 1):
        spans = []
        d = pg.get_text("dict")
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    t = sp["text"].strip()
                    if t:
                        spans.append((sp["bbox"], t))
        hits = []
        for a in range(len(spans)):
            for c in range(a + 1, len(spans)):
                ra, ta = spans[a]
                rb, tb = spans[c]
                ov = inter(ra, rb)
                if ov <= 0:
                    continue
                m = min(area(ra), area(rb))
                if m > 0 and ov / m > THRESH:
                    hits.append((ta[:22], tb[:22], ov / m))
        # 只报"图区域"里的碰撞：同一 x 列内、y 接近的密集小字
        if hits:
            print("第 %d 页：%d 处文字重叠" % (i, len(hits)))
            for ta, tb, r in hits[:6]:
                print("    %-22s <-> %-22s  重叠 %.0f%%" % (ta, tb, 100 * r))
            total += len(hits)
    print()
    print("合计重叠 %d 处" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
