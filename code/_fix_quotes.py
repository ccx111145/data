# -*- coding: utf-8 -*-
"""_fix_quotes.py —— 把 paper.tex 正文里的直角双引号 " 统一换成中文直角引号「」（按行内
奇数位为开引号、偶数位为闭引号配对）。纯排版修正，不改语义。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")

with io.open(TEX, "r", encoding="utf-8") as f:
    lines = f.read().split("\n")

n_line = n_rep = bad = 0
out = []
for ln, s in enumerate(lines, 1):
    # 先把 \" 归一成 "
    s2 = s.replace('\\"', '"')
    cnt = s2.count('"')
    if cnt == 0:
        out.append(s)
        continue
    if cnt % 2:
        print("[WARN] 第 %d 行引号数为奇数(%d)，跳过：%s" % (ln, cnt, s2[:80]))
        bad += 1
        out.append(s)
        continue
    buf, k = [], 0
    for ch in s2:
        if ch == '"':
            buf.append("「" if k % 2 == 0 else "」")
            k += 1
        else:
            buf.append(ch)
    out.append("".join(buf))
    n_line += 1
    n_rep += cnt

with io.open(TEX, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n已处理 %d 行、%d 个引号；跳过 %d 行" % (n_line, n_rep, bad))
