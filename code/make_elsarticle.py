# -*- coding: utf-8 -*-
"""
make_elsarticle.py —— 由 `paper_en/main.tex` **派生**出 Elsevier 模板版本
`paper_en/main_elsarticle.tex`（Elsevier）与 `paper_en/main_ieee.tex`（IEEEtran），并编译验证。

为什么派生而不是手工维护两份
----------------------------
两份文件一旦各自演进就会失同步（图表编号、宏引用、定理编号都靠 `\\label`/`\\ref`，
正文必须完全一致）。本脚本只做**两处机械替换**：
  1) 导言区：`article` 类 → `elsarticle` 类，并把 elsarticle 需要/冲突的宏包对齐；
  2) 前置部分：`\\title/\\author/\\date/\\maketitle + abstract + keywords`
     → `\\begin{frontmatter} … \\end{frontmatter}`。
正文（Introduction 到 Conclusion，含定理、算法、图表）**逐字不变**。

用法：python make_elsarticle.py [--no-compile]
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "paper_en", "main.tex")
DST = os.path.join(BASE, "paper_en", "main_elsarticle.tex")
XELATEX = r"H:\texlive\2024\bin\windows\xelatex.exe"
PDFLATEX = r"H:\texlive\2024\bin\windows\pdflatex.exe"
BIBTEX = r"H:\texlive\2024\bin\windows\bibtex.exe"

PREAMBLE_EL = r"""%==============================================================================
%  Elsevier (elsarticle) version — DERIVED FILE, do not edit by hand.
%  Regenerate with:  python code/make_elsarticle.py
%  The body is byte-identical to paper_en/main.tex; only the class and the
%  front matter differ.
%==============================================================================
\documentclass[preprint,12pt]{elsarticle}

\usepackage{amsmath,amssymb,amsthm}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{siunitx}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{xcolor}
\usepackage{caption}
\usepackage{algorithm}
\usepackage{algpseudocode}
\algrenewcommand\algorithmicrequire{\textbf{Input:}}
\algrenewcommand\algorithmicensure{\textbf{Output:}}
\floatname{algorithm}{Algorithm}
\captionsetup{font=small}

% ---- 表格自适应列宽 ---------------------------------------------------------
% 同一个 body 要能在三种版式下编译：单栏 article / elsarticle preprint，
% 以及 IEEEtran 的双栏窄栏。表格按单栏宽度排就会在双栏里溢出（右列被裁掉），
% 所以所有表格统一走 \fitwide：只在表格宽于版心时按比例缩小。
\newsavebox{\wearfitbox}
\newcommand{\fitwide}[1]{%
  \sbox{\wearfitbox}{#1}%
  \ifdim\wd\wearfitbox>\linewidth
    \resizebox{\linewidth}{!}{\usebox{\wearfitbox}}%
  \else
    \usebox{\wearfitbox}%
  \fi
}

"""

FRONT_EL = r"""\begin{frontmatter}

\title{Joint Transport--Relay Co-Design for UAV Emergency Logistics in
Mountainous Terrain: Handover-Aware Feasibility, Channel-Model Sensitivity,
and the Price of Partitioning}

\author[a]{Changxuan Cao}
\author[a]{Qiong Li}
\author[a]{Zhifeng Liu\corref{cor1}}
\author[a]{Yulong Peng}
\author[a]{Zexu Ouyang}
\cortext[cor1]{Corresponding author.}
\affiliation[a]{East China University of Technology (ECUT), Nanchang, Jiangxi,
China}
\ead{2023211904@ecut.edu.cn}
\ead{flxnicc05@gmail.com}
\ead[cor1]{2023211863@ecut.edu.cn}
\ead{15579178689@163.com}
\ead{1028359003@qq.com}

\begin{abstract}
REPLACE_WITH_MAIN_ABSTRACT
\end{abstract}

\begin{keyword}
REPLACE_WITH_MAIN_KEYWORDS
\end{keyword}

\end{frontmatter}
"""

# 双盲投稿用的匿名前置部分：C&OR / RESS 要求正文里不出现作者与单位，
# 但作者信息在 IEEE 变体里是必须的。同一套正文派生两个前置部分，
# 由 --anonymous 开关决定是否额外产出匿名 elsarticle 版。
FRONT_EL_ANON = FRONT_EL.replace(
    r"""\author[a]{Changxuan Cao}
\author[a]{Qiong Li}
\author[a]{Zhifeng Liu\corref{cor1}}
\author[a]{Yulong Peng}
\author[a]{Zexu Ouyang}
\cortext[cor1]{Corresponding author.}
\affiliation[a]{East China University of Technology (ECUT), Nanchang, Jiangxi,
China}
\ead{2023211904@ecut.edu.cn}
\ead{flxnicc05@gmail.com}
\ead[cor1]{2023211863@ecut.edu.cn}
\ead{15579178689@163.com}
\ead{1028359003@qq.com}""",
    r"""\author[a]{}
\affiliation[a]{}""")


PREAMBLE_IEEE = r"""%==============================================================================
%  IEEEtran version — DERIVED FILE, do not edit by hand.
%  Regenerate with:  python code/make_elsarticle.py
%  The body is byte-identical to paper_en/main.tex; only the class and the
%  front matter differ.  Target venue: IEEE T-ITS.
%==============================================================================
\documentclass[journal,10pt]{IEEEtran}
% IEEEtran 默认向 Times 借字形（TU/ptm/*），而 xelatex 下这些字形未定义，
% 编译会刷 148 条 "Font shape TU/ptm/* undefined" 并把正文回退成 Computer
% Modern——与 IEEE 的排版习惯不符。显式加载 newtx（Times 文本 + 数学）即可：
% 字形真实可用，警告消失，正文与公式同时变成 Times 系。
% IEEEtran 默认向 Times 借字形（TU/ptm/*）。这些字形在 xelatex 下未定义，
% 编译会刷上百条 "Font shape TU/ptm/* undefined" 并把正文回退成 Computer
% Modern——与 IEEE 的排版习惯不符。用 psnfss 的 mathptmx（Times 文本 + 数学）
% 一次性解决；它与 amssymb 无符号冲突（newtxmath 会与 amssymb 抢 \Bbbk /
% \openbox，故不用）。
\usepackage{mathptmx}

\usepackage{amsmath,amssymb,amsthm}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{siunitx}
\usepackage{enumitem}
\usepackage{url}
\usepackage{xcolor}
\usepackage{caption}
\usepackage{algorithm}
\usepackage{algpseudocode}
\algrenewcommand\algorithmicrequire{\textbf{Input:}}
\algrenewcommand\algorithmicensure{\textbf{Output:}}
\floatname{algorithm}{Algorithm}
\captionsetup{font=small}

\newsavebox{\wearfitbox}
\newcommand{\fitwide}[1]{%
  \sbox{\wearfitbox}{#1}%
  \ifdim\wd\wearfitbox>\linewidth
    \resizebox{\linewidth}{!}{\usebox{\wearfitbox}}%
  \else
    \usebox{\wearfitbox}%
  \fi
}

"""

FRONT_IEEE = r"""\title{Joint Transport--Relay Co-Design for UAV Emergency Logistics in
Mountainous Terrain: Handover-Aware Feasibility, Channel-Model Sensitivity, and
the Price of Partitioning}

\author{Changxuan Cao, Qiong Li, Zhifeng Liu, Yulong Peng, and Zexu Ouyang%%
\thanks{Manuscript prepared \today. The authors are with the East China
University of Technology (ECUT), Nanchang, Jiangxi, China.}%
\thanks{Corresponding author: Zhifeng Liu (e-mail: 2023211863@ecut.edu.cn).}%
\thanks{All numerical results in this manuscript are regenerated from the
shipped result files by \texttt{code/make\_numbers\_en.py}; every macro is
traced to its source in \texttt{numbers\_en\_sources.txt}.}}

\markboth{IEEE Transactions on Intelligent Transportation Systems, Vol.~XX, No.~X, 2026}%
{Cao \MakeLowercase{\textit{et al.}}: Joint Transport--Relay Co-Design for UAV Emergency Logistics}

\maketitle

\begin{abstract}
REPLACE_WITH_MAIN_ABSTRACT
\end{abstract}

\begin{IEEEkeywords}
REPLACE_WITH_MAIN_KEYWORDS
\end{IEEEkeywords}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-compile", action="store_true")
    a = ap.parse_args()

    s = io.open(SRC, encoding="utf-8").read()
    i_doc = s.find("\\begin{document}")
    assert i_doc > 0, "未找到 \\begin{document}"
    i_front_end = s.find("%==============================================================================\n\\section{Introduction}")
    assert i_front_end > i_doc, "未找到正文起点（Introduction）"

    # 1) 导言区：取共享宏定义（\InputRes / \Dfig / \tbd）并前置 elsarticle 导言
    i_inres = s.find("% ---- 结果文件缺失时给出显式提示")
    i_title = s.find("\\title{")
    assert i_inres > 0 and i_title > i_inres
    shared = s[i_inres:i_title]

    # 1b) 摘要与关键词：从 main.tex **抽取**，不在这里另抄一份。
    #     理由：另抄一份就会与正文失同步（本轮就发生过——IEEE 前置部分还写着
    #     "four contributions"，而正文已是五条）。这里只保留一份真源。
    #     注意只取 abstract **环境内部**的正文：main.tex 用的是 article 的
    #     \begin{abstract}...\end{abstract}，而 elsarticle 的 frontmatter 自带
    #     abstract 环境，整段搬过去会嵌套两层、报 "Extra }"。
    ab_open = "\\begin{abstract}"
    a0 = s.index(ab_open) + len(ab_open)
    a1 = s.index("\\end{abstract}", a0)
    abstract_inner = s[a0:a1].strip()
    k0 = s.index("\\noindent\\textbf{Keywords:}")
    # 关键词段以那一行长注释分隔线结束；用 \section{Introduction} 当右界会把
    # 注释行一起吞进来，所以这里**先切掉分隔线**再右界。
    k1 = s.index("%" + "=" * 78, k0)
    # 起点要加 "\\noindent\\textbf{Keywords:" 的长度**再加 1**（闭合花括号），
    # 否则 "}" 会被当成第一个关键词带进 \begin{keyword}，报 "Extra }"。
    kstart = k0 + len("\\noindent\\textbf{Keywords:") + 1
    assert s[kstart - 1] == "}", "关键词起点偏移错位：应紧跟在 \\textbf{Keywords:} 之后"
    kw_txt = s[kstart:k1]
    kw_items = [w.strip().rstrip(".;") for w in kw_txt.replace("\n", " ").split(";")]
    kw_items = [w for w in kw_items if w]
    front_el = FRONT_EL.replace(
        "REPLACE_WITH_MAIN_ABSTRACT", abstract_inner
    ).replace("REPLACE_WITH_MAIN_KEYWORDS", " \\sep ".join(kw_items))
    front_el_anon = FRONT_EL_ANON.replace(
        "REPLACE_WITH_MAIN_ABSTRACT", abstract_inner
    ).replace("REPLACE_WITH_MAIN_KEYWORDS", " \\sep ".join(kw_items))
    # IEEE 变体同样从 main.tex **抽取**摘要与关键词。以前这份 front matter 里
    # 是手抄的整段摘要，于是正文改了措辞而 IEEE 版停留在旧版
    # （它的摘要还写着 "decided rather than searched"），同一篇稿件出现两个说法。
    # 现在三个变体共用 main.tex 这一份真源。
    front_ieee = FRONT_IEEE.replace(
        "REPLACE_WITH_MAIN_ABSTRACT",
        # IEEEtran 的 abstract 环境自己处理缩进，去掉 main.tex 里的 \noindent
        abstract_inner.replace("\\noindent", "", 1).strip()
    ).replace("REPLACE_WITH_MAIN_KEYWORDS", "; ".join(kw_items))

    # shared 段里已经包含 \InputRes{numbers_en.tex}，不要再追加一次（会重复定义宏）。
    # 期刊变体在 paper_en/build/ 下编译，numbers_en.tex 会被复制到那里，
    # 而 \InputRes 的第一条候选路径就是裸文件名，因此无需再改路径。
    head = PREAMBLE_EL + "\n" + shared + "\n"
    body = s[i_front_end:]
    out = head + "\\begin{document}\n" + front_el + "\n" + body

    variants = [("main_elsarticle", PREAMBLE_EL, front_el),
                ("main_elsarticle_anon", PREAMBLE_EL, front_el_anon),
                ("main_ieee", PREAMBLE_IEEE, front_ieee)]
    # 变体 .tex 与它们的编译产物**放在同一个目录**（paper_en/build/）。
    # 以前 .tex 写在 paper_en/、而编译在 paper_en/build/，于是 paper_en/ 里
    # 留下一套「从未被编译过」的陈旧 main_<变体>.aux/.log/.bbl（其中 .bbl
    # 是 0 字节）。任何人若在 paper_en/ 里直接重跑 bibtex，会读到缺少
    # \bibdata 的陈旧 .aux 并得到空参考文献，从而复现出"文献全空"的假象。
    # 同目录输出从根本上消除这一陷阱。
    build = os.path.join(BASE, "paper_en", "build")
    os.makedirs(build, exist_ok=True)
    for name, pre, front in variants:
        out = pre + "\n" + shared + "\n" + "\\begin{document}\n" + front + "\n" + body
        dst = os.path.join(build, name + ".tex")
        io.open(dst, "w", encoding="utf-8").write(out)
        print("已写出 %s（%d 字节）" % (dst, len(out)))
    # 清掉旧布局遗留在 paper_en/ 的变体产物与 0 字节 .bbl
    import glob as _glob
    for pat in ("main_elsarticle*", "main_ieee*"):
        for f in _glob.glob(os.path.join(BASE, "paper_en", pat)):
            if os.path.abspath(f).startswith(os.path.abspath(build)):
                continue
            try:
                os.remove(f)
                print("已清理旧布局残留：%s" % os.path.basename(f))
            except OSError:
                pass
    if a.no_compile:
        return

    if not os.path.exists(XELATEX):
        print("未找到 xelatex，跳过编译")
        return

    # 编译工作目录：paper_en/build/ —— xelatex 按 **cwd** 解析图形相对路径，
    # 而正文引用的是 figs/xxx（\Dfig 宏会优先取同名 .pdf 矢量图、回退 .png）；
    # 把 figs/ 整个复制到 build/ 下即可原样编译。
    src_figs = os.path.join(BASE, "paper_en", "figs")
    if os.path.isdir(src_figs):
        # 正文写的是 figs/xxx.png，故必须放进 build/figs/（而不是 build/ 根下）
        dst_figs = os.path.join(build, "figs")
        os.makedirs(dst_figs, exist_ok=True)
        for fn in os.listdir(src_figs):
            p = os.path.join(src_figs, fn)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(dst_figs, fn))
    for nm in ("numbers_en.tex", "refs.bib", "main_elsarticle.tex",
               "main_elsarticle_anon.tex", "main_ieee.tex"):
        p = os.path.join(BASE, "paper_en", nm)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(build, nm))

    t0 = time.time()
    for name, _pre, _front in variants:
        # IEEEtran 用 TU 编码向 Times 借字形（TU/ptm/*），而 xelatex 没有这些字形，
        # 会回退成 Latin Modern 并刷上百条 "Font shape undefined"。该变体不含任何
        # 需要系统字体的内容（图内文字已全部栅格化/矢量化），因此**用 pdflatex 编译**：
        # 此时 mathptmx 提供的 Times 字形真实可用，正文与公式统一为 Times，
        # 这也更接近 IEEE 官方模板的产出。其余变体仍走 xelatex。
        engine = PDFLATEX if name == "main_ieee" and os.path.exists(PDFLATEX) else XELATEX
        for k in range(3):
            r = subprocess.run([engine, "-interaction=nonstopmode", name + ".tex"],
                               cwd=build, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log = r.stdout.decode("utf-8", "replace")
            errs = [ln for ln in log.splitlines() if ln.startswith("! ")]
            if k == 0 and os.path.exists(BIBTEX):
                subprocess.run([BIBTEX, name], cwd=build,
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            print("  [%s] 第 %d 遍（%s）：退出码 %d%s"
                  % (name, k + 1, os.path.basename(engine).split(".")[0],
                     r.returncode,
                     ("；错误：" + " | ".join(errs[:3])) if errs else ""))
        for ext in (".pdf", ".tex"):
            src = os.path.join(build, name + ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(BASE, "paper_en", name + ext))
        pdf = os.path.join(BASE, "paper_en", name + ".pdf")
        if os.path.exists(pdf):
            try:
                from pypdf import PdfReader
                rd = PdfReader(pdf)
                txt = "\n".join((p.extract_text() or "") for p in rd.pages)
                print("已生成 %s（%d 页，TBD=%d，??=%d）"
                      % (pdf, len(rd.pages), txt.count("TBD"), txt.count("??")))
            except Exception:                                      # noqa: BLE001
                print("已生成 %s" % pdf)
        else:
            print("!! 未生成 %s，请检查 paper_en/build/%s.log" % (pdf, name))
    print("总耗时 %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
