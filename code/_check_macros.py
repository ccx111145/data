# -*- coding: utf-8 -*-
"""_check_macros.py —— 论文宏一致性体检。

检查三件事（审阅 #26/#28 的交付质量要求）：
  1. paper.tex 中引用的每一个宏，是否在 numbers.tex / tables.tex / q3_gap.tex 中有定义；
  2. 三个宏文件是否存在**重复定义**（\\newcommand 重名会让 LaTeX 直接报错）；
  3. 是否有宏的值仍是占位符「待补」而被正文引用（说明结果文件缺失）。
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(BASE, "paper")
FILES = ["numbers.tex", "tables.tex", "q3_gap.tex"]

tex = io.open(os.path.join(PAPER, "paper.tex"), encoding="utf-8").read()
# 去掉自定义宏定义区的干扰：只收集正文里的 \Macro 用法
used = set(re.findall(r"\\([A-Za-z@]+)", tex))
builtin = set("""documentclass usepackage newcommand renewcommand providecommand
IfFileExists input include typeout texttt textbf textit emph textrm textsf textnormal
includegraphics caption label ref cite eqref section subsection subsubsection
begin end item centering toprule midrule bottomrule small footnotesize scriptsize
tiny large Large huge Huge vspace hspace noindent quad qquad left right frac sum
prod max min sup inf le ge ne approx cdot times pm mp to rightarrow Rightarrow
subseteq supseteq cup cap in notin forall exists infty mathrm mathcal mathbb mathbf
overline underline underbrace lceil rceil lfloor rfloor sqrt exp log lg
textwidth linewidth columnwidth baselineskip arraystretch tabcolsep parbox fbox
resizebox multirow multicolumn longtable tabularx graphicspath
makeatletter makeatother thispagestyle addcontentsline arabic bfseries normalsize
captionsetup ctexset chinese detokenize dots url varphi wedge big Big bigcup
downarrow uparrow text width height scale color textcolor rule hfill vfill
itemize enumerate description center figure table tabular align equation
leftmargin itemsep parsep topsep labelitemi arraystretch newcolumntype
setlength DeclareMathOperator tag nonumber notag Dfig UseResource CheckSummary
tightlist bigl bigr Biggl Biggr left right Delta S chi circ eta rho sigma sim star tau varepsilon varrho author date title maketitle tableofcontents newpage geometry InputRes Delta mathrm mathbf mathcal text width height scale""".split())
cands = sorted(x for x in used if x not in builtin)

defined, dup, vals = {}, {}, {}
for f in FILES:
    p = os.path.join(PAPER, f)
    if not os.path.exists(p):
        print("! 缺少宏文件 %s" % f)
        continue
    s = io.open(p, encoding="utf-8").read()
    for m in re.finditer(r"\\(?:new|renew|provide)command\{\\([A-Za-z]+)\}\{([^}]*)\}", s):
        name, val = m.group(1), m.group(2)
        dup.setdefault(name, []).append(f)
        defined[name] = f
        vals[name] = val

missing = [c for c in cands if c not in defined]
placeholder = [c for c in cands if defined.get(c) and vals.get(c, "").strip() == "待补"]
dupes = {k: v for k, v in dup.items() if len(v) > 1}

print("paper.tex 引用宏 %d 个；三个宏文件共定义 %d 个" % (len(cands), len(defined)))
if missing:
    print("\n[未定义] %d 个（编译会出现 Undefined control sequence）：" % len(missing))
    for m in missing:
        print("   \\%s" % m)
else:
    print("\n[未定义] 无")
if dupes:
    print("\n[重复定义] %d 个（LaTeX 会报 Command already defined）：" % len(dupes))
    for k, v in sorted(dupes.items()):
        print("   \\%s -> %s" % (k, "、".join(v)))
else:
    print("[重复定义] 无")
if placeholder:
    print("\n[仍为占位符] %d 个（正文会印出「待补」，说明结果文件缺失）：" % len(placeholder))
    for m in placeholder:
        print("   \\%s（定义于 %s）" % (m, defined[m]))
else:
    print("[仍为占位符] 无")
sys.exit(1 if (missing or dupes) else 0)
