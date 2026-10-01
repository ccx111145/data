# -*- coding: utf-8 -*-
"""_fix_ieee_variant.py —— 在 make_elsarticle.py 中增加 IEEEtran 变体的生成。

补齐四个候选期刊的模板覆盖：
  * C&OR / RESS  → Elsevier `elsarticle`  （已实现）
  * T-ITS / TVT  → IEEE `IEEEtran`（双栏） （本次新增）
两个变体都与 `main.tex` 共用同一份正文，只有导言区与前置部分不同，
由脚本派生，不做手工维护，避免失同步。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "make_elsarticle.py")
s = io.open(P, encoding="utf-8").read()

# ---------------- 1) 文档字符串补充 ----------------
s = s.replace(
    '"""make_elsarticle.py —— 由 `paper_en/main.tex` **派生**出 Elsevier 模板版本',
    '"""make_elsarticle.py —— 由 `paper_en/main.tex` **派生**出两个期刊模板版本')
s = s.replace(
    "`paper_en/main_elsarticle.tex`，并编译验证。",
    "`paper_en/main_elsarticle.tex`（Elsevier）与 `paper_en/main_ieee.tex`（IEEEtran），并编译验证。")

# ---------------- 2) 新增 IEEE 导言与前置 ----------------
ieee = '''

PREAMBLE_IEEE = r"""%==============================================================================
%  IEEEtran version — DERIVED FILE, do not edit by hand.
%  Regenerate with:  python code/make_elsarticle.py
%  The body is byte-identical to paper_en/main.tex; only the class and the
%  front matter differ.  Target venues: IEEE T-ITS, IEEE TVT.
%==============================================================================
\\documentclass[journal,10pt]{IEEEtran}

\\usepackage{amsmath,amssymb,amsthm}
\\usepackage{booktabs}
\\usepackage{graphicx}
\\usepackage{siunitx}
\\usepackage{enumitem}
\\usepackage{url}
\\usepackage{xcolor}
\\usepackage{caption}
\\usepackage{algorithm}
\\usepackage{algpseudocode}
\\algrenewcommand\\algorithmicrequire{\\textbf{Input:}}
\\algrenewcommand\\algorithmicensure{\\textbf{Output:}}
\\floatname{algorithm}{Algorithm}
\\captionsetup{font=small}

\\newtheorem{theorem}{Theorem}
\\newtheorem{proposition}[theorem]{Proposition}
\\newtheorem{corollary}[theorem]{Corollary}
\\theoremstyle{definition}
\\newtheorem{assumption}[theorem]{Assumption}
\\newtheorem{definition}[theorem]{Definition}
"""

FRONT_IEEE = r"""\\title{Joint Transport--Relay Co-Design for UAV Emergency Logistics in
Mountainous Terrain: Handover-Aware Feasibility, Channel-Model Sensitivity, and
the Price of Partitioning}

\\author{Anonymous Author(s)%%
\\thanks{Manuscript prepared \\today. The authors are with Institution, City,
Country (e-mail: anonymous@example.org).}%
\\thanks{All numerical results in this manuscript are regenerated from the
shipped result files by \\texttt{code/make\\_numbers\\_en.py}; every macro is
traced to its source in \\texttt{numbers\\_en\\_sources.txt}.}}

\\markboth{IEEE Transactions on Vehicular Technology, Vol.~XX, No.~X, 2026}%
{Author \\MakeLowercase{\\textit{et al.}}: Joint Transport--Relay Co-Design for UAV Emergency Logistics}

\\maketitle

\\begin{abstract}
Mountainous disaster relief requires unmanned aerial vehicles (UAVs) to deliver
cargo while staying connected to a fixed gateway that terrain frequently
occludes. We study the resulting \\emph{transport--relay co-design} problem and
make four contributions.
(i) We show that the widely used ``relay coverage'' abstraction is
\\emph{not executable}: once the physical cost of \\emph{handing over} between
hovering positions is accounted for, the minimum relay fleet grows from
$\\ENrbNaive$ to at least $\\ENrbGreedy$ vehicles on our instance, and we give a
rigorous handover-obstruction certificate (Theorem~\\ref{thm:handover}) that
turns the handover cost into a checkable inequality on a single scalar
\\emph{span} function.
(ii) We replace the constant occlusion penalty supplied with the benchmark by
the ITU-R P.~526 single-knife-edge diffraction model evaluated on the 30\\,m
digital elevation model; this raises the outage demand by $\\ENchReqDelta\\%$,
reduces the number of usable relay hover points by $\\ENchCandDelta\\%$, and
raises the minimum fleet size from $\\ENchObsNStar$ to $\\ENchAltNStar$, so the
commonly reported ``add one relay'' conclusion must be qualified by the channel
convention.
(iii) We close the loop between transport scheduling and relay feasibility with
a threshold-accepting search over departure instants alone; the residual
handover deficit cannot be driven to zero, which shows that \\emph{decoupling is
not the cause} of infeasibility.
(iv) We introduce a controlled terrain family and show that the fleet size is
governed by the temporal fragmentation of the outage demand rather than by its
volume.
\\end{abstract}

\\begin{IEEEkeywords}
UAV logistics, air-to-ground channel, knife-edge diffraction, relay handover,
joint scheduling, disaster relief.
\\end{IEEEkeywords}
"""

'''

anchor = '\n\ndef main():'
assert s.count(anchor) == 1, s.count(anchor)
s = s.replace(anchor, ieee + '\ndef main():')

# ---------------- 3) main 里同时生成/编译 IEEE 变体 ----------------
old = '''    io.open(DST, "w", encoding="utf-8").write(out)
    print("已写出 %s（%d 字节）" % (DST, len(out)))
    if a.no_compile:
        return

    if not os.path.exists(XELATEX):
        print("未找到 xelatex，跳过编译")
        return
    t0 = time.time()
    for k in range(3):
        r = subprocess.run([XELATEX, "-interaction=nonstopmode",
                            "-output-directory=paper_en", "paper_en/main_elsarticle.tex"],
                           cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = r.stdout.decode("utf-8", "replace")
        errs = [ln for ln in log.splitlines() if ln.startswith("! ")]
        if k == 0 and os.path.exists(BIBTEX):
            subprocess.run([BIBTEX, "main_elsarticle"],
                           cwd=os.path.join(BASE, "paper_en"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print("  第 %d 遍：退出码 %d%s" % (k + 1, r.returncode,
                                        ("；错误：" + " | ".join(errs[:3])) if errs else ""))
    pdf = os.path.join(BASE, "paper_en", "main_elsarticle.pdf")
    if os.path.exists(pdf):
        try:
            from pypdf import PdfReader
            rd = PdfReader(pdf)
            txt = "\\n".join((p.extract_text() or "") for p in rd.pages)
            print("已生成 %s（%d 页，TBD=%d，??=%d，%.0f s）"
                  % (pdf, len(rd.pages), txt.count("TBD"), txt.count("??"), time.time() - t0))
        except Exception:                                          # noqa: BLE001
            print("已生成 %s" % pdf)
    else:
        print("!! 未生成 PDF，请检查 %s" % os.path.join(BASE, "paper_en", "main_elsarticle.log"))'''

new = '''    variants = [("main_elsarticle", PREAMBLE_EL, FRONT_EL),
                ("main_ieee", PREAMBLE_IEEE, FRONT_IEEE)]
    for name, pre, front in variants:
        out = pre + "\\n" + shared + "\\n" + "\\\\begin{document}\\n" + front + "\\n" + body
        dst = os.path.join(BASE, "paper_en", name + ".tex")
        io.open(dst, "w", encoding="utf-8").write(out)
        print("已写出 %s（%d 字节）" % (dst, len(out)))
    if a.no_compile:
        return

    if not os.path.exists(XELATEX):
        print("未找到 xelatex，跳过编译")
        return
    t0 = time.time()
    for name, _pre, _front in variants:
        for k in range(3):
            r = subprocess.run([XELATEX, "-interaction=nonstopmode",
                                "-output-directory=paper_en",
                                "paper_en/%s.tex" % name],
                               cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log = r.stdout.decode("utf-8", "replace")
            errs = [ln for ln in log.splitlines() if ln.startswith("! ")]
            if k == 0 and os.path.exists(BIBTEX):
                subprocess.run([BIBTEX, name], cwd=os.path.join(BASE, "paper_en"),
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            print("  [%s] 第 %d 遍：退出码 %d%s"
                  % (name, k + 1, r.returncode,
                     ("；错误：" + " | ".join(errs[:3])) if errs else ""))
        pdf = os.path.join(BASE, "paper_en", name + ".pdf")
        if os.path.exists(pdf):
            try:
                from pypdf import PdfReader
                rd = PdfReader(pdf)
                txt = "\\n".join((p.extract_text() or "") for p in rd.pages)
                print("已生成 %s（%d 页，TBD=%d，??=%d）"
                      % (pdf, len(rd.pages), txt.count("TBD"), txt.count("??")))
            except Exception:                                      # noqa: BLE001
                print("已生成 %s" % pdf)
        else:
            print("!! 未生成 %s，请检查 paper_en/%s.log" % (pdf, name))
    print("总耗时 %.0f s" % (time.time() - t0))'''

c = s.count(old)
print("main 置换匹配：%d" % c)
assert c == 1
s = s.replace(old, new)
io.open(P, "w", encoding="utf-8").write(s)
print("make_elsarticle.py 已扩展为双模板生成器")
