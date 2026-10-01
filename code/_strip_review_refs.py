# -*- coding: utf-8 -*-
"""_strip_review_refs.py —— 删除论文正文里的「对应审阅 #NN」这类**内部评审用语**。

两个原因：(1) 竞赛论文不应出现内部评审编号；(2) LaTeX 中 `#` 是宏参数符，
未转义会直接导致 `You can't use 'macro parameter character #'` 编译错误。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper", "paper.tex")

REPL = [
    (r"\emph{口径说明（对应审阅 #17）}", r"\emph{口径说明}"),
    (r"\noindent\textbf{水平能耗项的假设强度（对应审阅 #21，须如实声明）}",
     r"\noindent\textbf{水平能耗项的假设强度（须如实声明）}"),
    (r"\noindent\textbf{该 MILP 的完备性边界（对应审阅 #18，避免「列了式子就等于全形式化」的误读）}",
     r"\noindent\textbf{该 MILP 的完备性边界（避免「列了式子就等于全形式化」的误读）}"),
    (r"\emph{必须纠正一个易犯的误读（对应审阅 #20）}", r"\emph{必须纠正一个易犯的误读}"),
    (r"\noindent\textbf{初始状态与终止条件（对应审阅 #6）}", r"\noindent\textbf{初始状态与终止条件}"),
    (r"\noindent\textbf{完备性的边界（必须如实声明，对应审阅 #2）}",
     r"\noindent\textbf{完备性的边界（必须如实声明）}"),
    (r"\emph{措辞校准（对应审阅 #2）}", r"\emph{措辞校准}"),
    (r"\noindent\textbf{核验性质的声明（对应审阅 #9：采样核验 $\ne$ 连续时间的证明）}",
     r"\noindent\textbf{核验性质的声明（采样核验 $\ne$ 连续时间的证明）}"),
]

s = io.open(TEX, encoding="utf-8").read()
for old, new in REPL:
    if s.count(old) != 1:
        print("[MISS] %s（%d）" % (old[:40], s.count(old)))
        continue
    s = s.replace(old, new)
    print("[OK] %s" % old[:44])

# 兜底：任何残留的「对应审阅 #N」
import re
s2, k = re.subn(r"（[^）]*对应审阅[^）]*#\s*\d+[^）]*）", "", s)
if k:
    print("[OK] 兜底清除 %d 处残留" % k)
    s = s2
io.open(TEX, "w", encoding="utf-8").write(s)
left = len(re.findall(r"#", s))
print("文件中剩余 # 字符数：%d（应仅为 LaTeX 宏定义中的 ##，本文件应为 0）" % left)
