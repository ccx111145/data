# -*- coding: utf-8 -*-
"""_probe_fig2.py —— 同时量出：每张插图在页面上的实际宽高，以及图内文字的字号。

诊断用：判断"图内文字偏小"到底是
  (a) 画布远宽于显示宽度（缩放比 <1，字号等比缩小），还是
  (b) 字号本来就设得太小。
用法：python code/_probe_fig2.py [pdf名]
"""
from __future__ import annotations

import os
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, "paper_en", "build", (sys.argv[1] if len(sys.argv) > 1 else "main_ieee") + ".pdf")

# 正文正文字号（IEEEtran 10pt 正文约 9.96pt），用来做参照
BODY = 9.96


def main() -> int:
    doc = fitz.open(PDF)
    print("PDF: %s  共 %d 页  正文字号≈%.2f pt" % (os.path.basename(PDF), len(doc), BODY))
    print()
    for i, pg in enumerate(doc, 1):
        dr = pg.get_drawings()
        if len(dr) < 15:
            continue
        xs0 = min(d["rect"].x0 for d in dr)
        xs1 = max(d["rect"].x1 for d in dr)
        ys0 = min(d["rect"].y0 for d in dr)
        ys1 = max(d["rect"].y1 for d in dr)
        # 图内文字字号
        d = pg.get_text("dict")
        sizes = {}
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    if sp["text"].strip():
                        k = round(sp["size"], 2)
                        sizes[k] = sizes.get(k, 0) + len(sp["text"])
        # 只统计图区域内的
        in_fig = {}
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    bb = sp["bbox"]
                    if bb[0] >= xs0 - 5 and bb[1] >= ys0 - 5 and bb[2] <= xs1 + 5 and bb[3] <= ys1 + 5:
                        if sp["text"].strip():
                            k = round(sp["size"], 2)
                            in_fig[k] = in_fig.get(k, 0) + len(sp["text"])
        mn = min(in_fig) if in_fig else None
        print("第 %-2d 页 图框 %.0fx%.0f pt (%.2f x %.2f in)"
              % (i, xs1 - xs0, ys1 - ys0, (xs1 - xs0) / 72, (ys1 - ys0) / 72))
        if in_fig:
            top = sorted(in_fig.items(), key=lambda x: -x[1])[:5]
            print("        图内字号: %s   最小 %.2f pt (正文的 %.0f%%)"
                  % ("  ".join("%.1f×%d" % (s, n) for s, n in top), mn, 100 * mn / BODY))
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
