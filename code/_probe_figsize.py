# -*- coding: utf-8 -*-
"""_probe_figsize.py —— 量出正文里每张插图的实际占用尺寸与图内最小字号。

为什么要单独量：图是矢量，所以清晰度不是位图分辨率问题，而是**缩放比**问题——
图按"全栏宽/版心宽"设计，塞进 IEEEtran 单栏后整体缩小，图内字号跟着等比缩小，
于是出现"略带虚化感"的观感（其实是矢量被缩到 2–3 pt）。
"""
from __future__ import annotations

import io
import os
import re
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, "paper_en", "build", "main_compact.pdf")


def main() -> int:
    if not os.path.exists(PDF):
        print("找不到 %s" % PDF)
        return 1
    doc = fitz.open(PDF)
    print("版心/栏宽参考：IEEEtran 10pt 双栏，单栏文字宽约 252 pt")
    print()
    for i, pg in enumerate(doc, 1):
        d = pg.get_text("dict")
        # 每页按字号聚类：小于正文字号的 span 很可能来自插图
        spans = []
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    if sp["text"].strip():
                        spans.append((round(sp["size"], 2), sp["text"].strip()[:26],
                                      sp["bbox"]))
        small = [s for s in spans if s[0] < 7.0]
        if not small:
            continue
        # 只看位于页面上半部分、且成簇的（插图区域）
        print("第 %d 页：有 %d 个 < 7pt 的文本 span" % (i, len(small)))
        for sz, txt, bb in sorted(small, key=lambda x: x[0])[:5]:
            print("    %.2f pt  %-26s  bbox=%s" % (sz, txt, tuple(round(v) for v in bb)))
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
