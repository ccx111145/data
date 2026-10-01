# -*- coding: utf-8 -*-
"""make_compact_en.py —— 生成 T-ITS 版面收紧版 + 补充材料（supplementary）。

为什么需要
----------
T-ITS Regular Paper 的页限是 10 页、最多可超 6 页（即上限 16 页），超页 $175/页。
原始 `main.tex` 编译出的 IEEEtran 版正好 16 页 —— 踩在上限上、余量为 0，
正式模板再多出一行就会被退回或加价。

做法
----
**不删任何内容**，只把它分成两份都能独立阅读的文件：

1. `main.tex` 本体照旧（neutral / Elsevier / 双栏 IEEE 三版式都从它派生），
   供直接阅读与后续排版；
2. 本脚本生成 `paper_en/main_compact.tex`：把若干**非承重证明**与**伪代码清单**
   移到补充材料，正文原位留一行指针。
3. 同时生成 `paper_en/supplement.tex`：自包含的补充材料，含被移出的证明与伪代码。

只移"换了位置不影响主线论证"的部分。被移动的证明在正文里都写明了
"proof in the supplementary material"，命题陈述本身仍在正文，因此正文单独
阅读不缺口。

用法：python code/make_compact_en.py
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys

import dcore as D

PAPER_EN = os.path.join(D.BASE, "paper_en")
TEX = os.path.join(PAPER_EN, "main.tex")
BUILD = os.path.join(PAPER_EN, "build")

SUPP_NAME = "supplement"
SUPP_LABEL = "supp"          # \ref 用的标签/文件名

# ---------------------------------------------------------------------------
# 移到补充材料的证明（按 owner label）。判据：该证明不承载主结论。
# 承重、必须留在正文的：thm:handover、thm:exact、thm:two、prop:W、prop:lb 已移。
# ---------------------------------------------------------------------------
MOVE_PROOFS = {
    "cor:continuous",       # 与 thm:handover 证明相同，一句话
    "prop:phase",           # 辅助论证
    "prop:energy",          # 条件界，正文已给结论
    "prop:structural",      # 筛选用上界
    "thm:one",              # 单架边界情形
    "prop:monotone",        # 一行
    "prop:demand",          # 一行
    "prop:lipschitz",       # 辅助正则性
    "prop:lb",              # 下界构造
    # 下面两条是"构造即证明"型，陈述留在正文、证明移出：
    # thm:exact 的 (\Leftarrow) 是"给定调度、按时间序排出转移"；thm:two 同理。
    # 判断：陈述必须留在正文（它定义了我们报告什么），证明可复核、不必占版面。
    "thm:exact",
    "thm:two",
}

# 承重、必须留在正文的证明：thm:handover 是本文主定理（论文的核心不等式），
# prop:distinguishing 是"否定结论为何是有限搜索空间上的陈述"的直接依据。
KEEP_PROOFS = {"thm:handover", "prop:distinguishing"}

# 移到补充材料的伪代码（按 caption 关键词）
MOVE_ALGS = {
    "Handover-aware relay feasibility",
    "Co-design feedback loop",
}


def strip_comments(t: str) -> str:
    r"""把 % 之后到行尾的内容**用等长空白替换**（保留换行），这样
    \end{proof} / \begin{algorithm} 之类的注释文本不会干扰块定位，
    而所有下标仍与原串一一对应 —— 这一点很关键：如果压缩掉注释字符，
    在去注释副本上找到的下标用到原文上就会错位（表现为把正文当成算法块）。"""
    out = []
    for line in t.split("\n"):
        idx = None
        i = 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                idx = i
                break
            i += 1
        out.append(line if idx is None else line[:idx] + " " * (len(line) - idx))
    return "\n".join(out)


def find_blocks(t: str, env: str):
    """返回 [(start, end, line_no, owner_label)]，在**去注释**的副本上定位，
    但仍返回原文中的下标（因为去注释是等长替换）。"""
    clean = strip_comments(t)
    res = []
    for m in re.finditer(re.escape("\\begin{" + env + "}"), clean):
        close = "\\end{" + env + "}"
        j = clean.find(close, m.end())
        if j < 0:
            continue
        end = j + len(close)
        labs = re.findall(r"\\label\{([^}]+)\}", clean[:m.start()])
        owner = labs[-1] if labs else "?"
        res.append((m.start(), end, t[:m.start()].count("\n") + 1, owner))
    return res


def cut_macro(t: str, name: str) -> str:
    r"""删除 \name{...} 整段（含跨行），用花括号配对定位真正的结尾。"""
    key = "\\" + name + "{"
    i = t.find(key)
    if i < 0:
        return t
    j = i + len(key)
    depth = 1
    while j < len(t) and depth:
        if t[j] == "{":
            depth += 1
        elif t[j] == "}":
            depth -= 1
        j += 1
    while j < len(t) and t[j] in " \t\r\n":
        j += 1
    return t[:i] + t[j:]


def replace_macro_text(t: str, name: str, new_text: str) -> str:
    r"""把 \name{...} 换成 \name{new_text}，同样用花括号配对。"""
    key = "\\" + name + "{"
    i = t.find(key)
    if i < 0:
        return t
    j = i + len(key)
    depth = 1
    while j < len(t) and depth:
        if t[j] == "{":
            depth += 1
        elif t[j] == "}":
            depth -= 1
        j += 1
    return t[:i] + "\\" + name + "{" + new_text + "}" + t[j:]


def prepend_preamble(dst_tex: str, extra: str) -> str:
    t = io.open(TEX, encoding="utf-8").read()
    i = t.find("\\begin{document}")
    j = t.find("\\end{document}")
    return t[:i] + extra + t[i:j + len("\\end{document}")] + "\n"


def load_elsarticle_mod():
    """导入同目录的 make_elsarticle.py，复用它的 PREAMBLE_IEEE 与共享宏段。"""
    import importlib.util as ilu
    here = os.path.dirname(os.path.abspath(__file__))
    spec = ilu.spec_from_file_location("make_elsarticle", os.path.join(here, "make_elsarticle.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wrap_as_ieee(compact_src: str) -> str:
    r"""把紧凑版正文包进 IEEEtran 导言，得到与投稿版同版式的 PDF。

    直接复用 main.tex 的 article 前导会得到单栏 27 页，与投稿版面（16 页）
    不可比；因此这里换成 make_elsarticle.py 里已经调好的 IEEEtran 导言 +
    共享宏段（\InputRes / \Dfig / \eqfit / \fitwide / 定理样式），
    保证紧凑版与 main_ieee 同字体、同栏宽、同宏。
    """
    mod = load_elsarticle_mod()
    s = io.open(TEX, encoding="utf-8").read()
    i_inres = s.find("% ---- 结果文件缺失时给出显式提示")
    i_title = s.find("\\title{")
    if i_inres < 0 or i_title < i_inres:
        raise RuntimeError("找不到共享宏段边界")
    shared = s[i_inres:i_title]

    i_doc = compact_src.find("\\begin{document}")
    marker = ("%==============================================================================\n"
              "\\section{Introduction}")
    i_body = compact_src.find(marker)
    if i_doc < 0 or i_body < 0:
        raise RuntimeError("找不到紧凑版正文边界")
    front = compact_src[i_doc:i_body]          # \begin{document} .. 摘要/关键词
    body = compact_src[i_body:]                 # Introduction 起

    # IEEEtran 要求 \title 在 \begin{document} 之前。紧凑版是从 main.tex 派生的，
    # 但 \title 在"共享宏段"之后、\begin{document} 之前的位置上，直接取会导致
    # "No \title given"。这里显式补一个标题（与 main.tex 同题）。
    title = ("\\title{Joint Transport--Relay Co-Design for UAV Emergency Logistics "
             "in Mountainous Terrain:\\\\ Handover-Aware Feasibility, Channel-Model "
             "Sensitivity, and the Price of Partitioning}\n"
             "\\author{}\n\\date{}\n")
    # 紧凑版把算法 2/3 移到了补充材料，正文里仍有 \ref{alg:code} 之类的引用。
    # 用 xr 读补充材料的 .aux，让这些编号照样解析；同时正文里指向补充材料的
    # \ref{supp} 也由此解析。编译顺序必须是 supplement -> main_compact。
    xr = ("\n% xr：从 supplement.aux 读取移出内容的 label，使正文里的 \\ref 仍可解析\n"
          "\\usepackage{xr}\n\\externaldocument{supplement}\n")
    return (mod.PREAMBLE_IEEE + "\n" + shared + "\n" + xr + "\n" + title + "\n"
            + front
            + "%==============================================================================\n"
            + body)


def main() -> int:
    t = io.open(TEX, encoding="utf-8").read()

    proofs = find_blocks(t, "proof")
    algs = find_blocks(t, "algorithm")

    moved_proofs = [(a, b, ln, ow) for (a, b, ln, ow) in proofs if ow in MOVE_PROOFS]
    moved_algs = []
    for (a, b, ln, ow) in algs:
        seg = strip_comments(t[a:b])
        if any(k in seg for k in MOVE_ALGS):
            moved_algs.append((a, b, ln, ow))

    print("找到 proof 块 %d 个，其中移出 %d 个" % (len(proofs), len(moved_proofs)))
    print("找到 algorithm 块 %d 个，其中移出 %d 个" % (len(algs), len(moved_algs)))

    # ---- 1) 先抽走要移出的原文（从后往前替换，避免下标错位）----
    pieces = []          # (owner, kind, 原文)
    for (a, b, ln, ow) in moved_proofs:
        pieces.append((ow, "proof", t[a:b]))
    for (a, b, ln, ow) in moved_algs:
        pieces.append((ow, "algorithm", t[a:b]))

    compact = t
    for (a, b, ln, ow) in sorted(moved_proofs + moved_algs, key=lambda x: -x[0]):
        seg = strip_comments(t[a:b])
        if seg.lstrip().startswith("\\begin{proof}"):
            repl = ("\\noindent\\emph{Proof.} Omitted here for length; the full proof is "
                    "in the supplementary material~\\ref{%s}.\n" % SUPP_LABEL)
        else:
            repl = ("\\noindent\\emph{Pseudocode.} The listing is omitted here for length "
                    "and is given in the supplementary material~\\ref{%s}.\n" % SUPP_LABEL)
        compact = compact[:a] + repl + compact[b:]

    # ---- 2) 正文里补一句指向补充材料的总说明 ----
    anchor = "\\begin{abstract}"
    note = ("\\noindent\\textbf{Supplementary material.} Proofs of the auxiliary "
            "propositions and the pseudocode listings are collected in the "
            "supplementary material~\\ref{%s}; no claim in the main text depends on "
            "reading them, and every moved proof is flagged at its point of use.\n\n"
            % SUPP_LABEL)
    if anchor in compact:
        compact = compact.replace(anchor, note + anchor, 1)

    # ---- 2b) 组装补充材料正文 ----
    supp_body = ["\\section*{Supplementary material}\\label{%s}" % SUPP_LABEL,
                 "",
                 "This supplement collects the proofs and the pseudocode listings that are",
                 "omitted from the main text for length. Equation and theorem numbering",
                 "follows the main text; every item below is flagged at its point of use",
                 "there.",
                 ""]
    order = {"proof": 0, "algorithm": 1}
    for (ow, kind, body) in sorted(pieces, key=lambda x: (order[x[1]], x[0])):
        title = ("Proof of \\texttt{%s}" % ow) if kind == "proof" else \
                ("Pseudocode for \\texttt{%s}" % ow)
        supp_body.append("\\subsection*{%s}" % title)
        supp_body.append(body)
        supp_body.append("")

    # ---- 3) 生成补充材料：复用 main.tex 的前导，换标题、去掉作者 ----
    # 必须用花括号配对：\author{...\textsuperscript{1}...} 有嵌套花括号，
    # 非贪婪正则会在第一个 } 就停、切出半截，导致 "Too many }'s"
    # 与 "Missing \begin{document}"。
    src = io.open(TEX, encoding="utf-8").read()
    i = src.find("\\begin{document}")
    head = src[:i]
    head = replace_macro_text(head, "title", "Supplementary Material")
    head = cut_macro(head, "author")
    # 补充材料会引用正文里的定理/假设编号（thm:handover、asm:* 等）。
    # 用 xr 把 main_ieee 的 .aux 挂进来，这些 \ref 才能解析成正文的编号，
    # 否则会有 10 处悬空引用。注意 head 只到 \begin{document} 之前，
    # 所以直接往 head 末尾追加即可（早先写成 replace("\\begin{document}", ...)
    # 匹配不到，xr 根本没加载）。
    if "\\usepackage{xr}" not in head:
        head = head.rstrip() + \
            "\n\n% xr：从正文变体的 .aux 读取 label，使下面的 \\ref 指向正文编号\n" \
            "\\usepackage{xr}\n\\externaldocument{main_ieee}\n\n"
    supp_final = head + "\\begin{document}\n\\maketitle\n\n" + \
        "\n".join(supp_body) + "\n\\end{document}\n"

    os.makedirs(BUILD, exist_ok=True)
    out_compact = os.path.join(BUILD, "main_compact.tex")
    out_supp = os.path.join(BUILD, "supplement.tex")

    # 紧凑版必须是 **IEEEtran 双栏**，否则页数没有可比性：直接沿用 main.tex 的
    # article 前导会得到单栏 27 页，而投稿版面（main_ieee）是 16 页。
    # 这里复用 make_elsarticle.py 已经调好的 IEEE 导言与共享宏段，
    # 保证紧凑版与正式 IEEE 版同字体、同栏宽、同宏定义。
    ieee_src = wrap_as_ieee(compact)
    io.open(out_compact, "w", encoding="utf-8").write(ieee_src)
    io.open(out_supp, "w", encoding="utf-8").write(supp_final)
    print("已写出 %s" % out_compact)
    print("已写出 %s" % out_supp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
