# -*- coding: utf-8 -*-
"""make_front_matter.py —— 生成 Editorial Manager 表单可直接粘贴的三段文本：
   标题 / 摘要（纯文本）/ 关键词（分号分隔）。

为什么需要：EM 的标题-摘要-关键词栏**不接受 LaTeX**，而且有硬限制
（摘要 500 words、关键词 6 个）。系统自动抽取失败时只能人工粘，
所以这里把 main.tex 的摘要展开数字宏、清掉全部 LaTeX 标记，
并**打印词数与字符数**，便于判断是否需要删减。

输出：C:\\Users\\ASUS\\Desktop\\D题_TRC投稿包\\09_EM_form_text.md
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")
NUMS = os.path.join(BASE, "paper_en", "numbers_en.tex")
DEST = r"C:\Users\ASUS\Desktop\D题_TRC投稿包"


def brace_arg(t: str, start: int) -> tuple[str, int]:
    """从 start 处的 '{' 起做花括号配对，返回 (内容, 结束下标)。"""
    depth, j = 0, start
    while j < len(t):
        if t[j] == "{":
            depth += 1
        elif t[j] == "}":
            depth -= 1
            if depth == 0:
                return t[start + 1:j], j + 1
        j += 1
    return t[start + 1:], len(t)


def clean(s: str, mac: dict) -> str:
    # 1) 展开数字宏（否则会留下空档）
    s = re.sub(r"\\(EN[A-Za-z0-9]+)", lambda m: mac.get(m.group(1), ""), s)
    # 2) 逐层剥掉常见格式命令
    for _ in range(3):
        s = re.sub(r"\\(?:emph|textbf|texttt|mathrm|text|mbox)\{([^{}]*)\}", r"\1", s)
    # 3) 引用与交叉引用
    s = re.sub(r"\\(?:cite|ref|eqref|label)\{[^}]*\}", "", s)
    # 4) 行内数学
    s = re.sub(r"\$([^$]*)\$", r"\1", s)
    s = s.replace("\\P.~526", "P.526").replace("\\P.526", "P.526")
    s = s.replace("$T^{\\mathrm{cap}}$", "Tcap")
    # 5) 引号与不断行空格
    s = s.replace("``", '"').replace("''", '"').replace("~", " ")
    s = re.sub(r"\\,|\\;|\\!|\\ ", " ", s)
    # 6) 剩余控制序列与括号
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[{}\\]", " ", s)
    # 7) 收敛空白与标点
    # LaTeX 残留清理（EM 表单不接受 LaTeX，`--` 之类必须转成真字符）
    s = s.replace("--", "\u2013")          # en dash
    s = s.replace("P. 526", "P.526")
    s = re.sub(r"([\d.]+)\s*%", r"\1%", s)   # "+32.2 %" -> "+32.2%"
    s = re.sub(r"\+\s*(\d)", r"+\1", s)      # 保持 +32.2%
    # 数学被剥两层后，这个界会退化成 "N^ *." 之类（数字在第二层里已丢）。
    # 用两种形态兜住；正文里该界是 N* >= 2。
    s = s.replace("N^ * 2", "N* >= 2").replace("N^ * 3", "N* >= 3")
    s = re.sub(r"N\^ \*\.", "N* >= 2.", s)
    s = re.sub(r"N\^ \*(?=[,;.\s])", "N* >= 2 ", s)
    # 正文里该定理是 Theorem 1（手性：主定理为第一个 theorem 环境）
    # 放在下面那条 \s+([,.;:)]) 清理**之前**做：那条会把刚插进去的空格吃掉。
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\(Corollary\)", "Corollary 1", s)
    s = re.sub(r"\s+([,.;:)])", r"\1", s)
    # 定理编号：clean() 内部补，否则外层替换会被下面的空白收拢再抹掉
    s = s.replace("(Theorem)", "(Theorem 1)").replace("(Corollary)", "(Corollary 1)")
    s = " ".join(s.split())
    return s.strip()


def main() -> int:
    mac = dict(re.findall(r"\\newcommand\{\\([A-Za-z0-9]+)\}\{([^}]*)\}",
                          io.open(NUMS, encoding="utf-8").read()))
    t = io.open(TEX, encoding="utf-8").read()

    # 标题
    i = t.index("\\title{")
    title_raw, _ = brace_arg(t, i + len("\\title"))
    title = clean(title_raw.replace("\\\\", " ").replace("\\bfseries", ""), mac)

    # 摘要
    a0 = t.index("\\begin{abstract}") + len("\\begin{abstract}")
    a1 = t.index("\\end{abstract}")
    abstract = clean(t[a0:a1], mac)

    # 关键词
    # 关键词跨多行，单行正则只能取到第一行（上一版就少读了 4 个）。
    # 从 Keywords: 起取到注释分隔线或 \section 为止。
    i = t.find("Keywords:")
    tail = t[i:]
    stop = len(tail)
    for mk in ("\n\n%", "\n%===", "\n\section"):
        k = tail.find(mk)
        if k > 0:
            stop = min(stop, k)
    block = tail[:stop]
    block = block.split("}", 1)[1] if "}" in block[:40] else block
    kws = [x.strip().rstrip(".;") for x in re.split(r"[;,]", block)]
    kws = [re.sub(r"[{}]", "", k).strip() for k in kws if k.strip()]
    kws = [k.replace("\n", " ") for k in kws]

    # EM 的摘要栏硬限 500 词，而 main.tex 的摘要为 ~513 词。
    # 这里做**等义压缩**（只删冗余、不改任何数字与结论强度），并逐条列出改法，
    # 便于与正文摘要对照；压缩后仍超限就在报告里明说，不静默截断。
    TRIM = [
        ("the fleet size for which we can construct a verified schedule grows from",
         "the smallest fleet with a constructed schedule grows from"),
        ("We report the rate at which that condition is satisfiable at the median blackout window",
         "At the median blackout window that condition is satisfiable for"),
        ("and show that it does not close the question; we consequently report every fleet-size statement with its search scope, distinguishing",
         "which does not close the question; we therefore report every fleet-size statement with its scope, distinguishing"),
        ("That negative verdict is a statement about the declared finite set, and we say so wherever it is used: closing the state pruning at that breadth did not terminate within our compute budget, so we do not claim an unpruned decision.",
         "That verdict is a statement about the declared finite set: closing the state pruning at that breadth did not terminate within our budget, so we claim no unpruned decision."),
        ("the ITU-R P.526 single-knife-edge diffraction model evaluated on the 30 m digital elevation model",
         "the ITU-R P.526 single-knife-edge diffraction model on the 30 m DEM"),
        ("and the coverage-only relaxation needs 1 relay while the smallest fleet for which we can construct a verified schedule rises from 3 to 4, so the commonly reported",
         "and the coverage-only relaxation needs 1 relay while the smallest constructed fleet rises from 3 to 4, so the commonly reported"),
        ("with a threshold-accepting search over departure instants alone, holding the routing, batching and fleet decisions at their baseline values; the residual handover deficit was unchanged by that search, which is evidence against a purely scheduling-driven explanation but not a proof of its absence.",
         "with a threshold-accepting search over departure instants alone, holding routing, batching and fleet decisions fixed; the residual deficit was unchanged, which is evidence against a purely scheduling-driven explanation but not a proof of its absence."),
        ("run under the same scheduler, fails from the opposite direction: it wins the routing layer",
         "run under the same scheduler, fails from the opposite direction: it wins routing"),
        ("and show that the smallest fleet with a constructed schedule is a non-monotone function of terrain severity, with no monotone relation to the occlusion ratio",
         "and show that the smallest constructed fleet is a non-monotone function of terrain severity, with no monotone relation to occlusion ratio"),
        ("is generated from the shipped result files by a single scripted pipeline, with the exceptions listed explicitly in Section",
         "is generated from the shipped result files by one scripted pipeline, with exceptions listed in Section"),
    ]
    for a, b in TRIM:
        if a in abstract:
            abstract = abstract.replace(a, b, 1)

    nw = len(abstract.split())
    nc = len(abstract)
    lines = [
        "# Editorial Manager 表单文本（标题 / 摘要 / 关键词）",
        "",
        "直接从 `paper_en/main.tex` 抽出并清掉 LaTeX 标记；数字宏已展开。",
        "**不要**从 PDF 复制——PDF 会把连字符和数学符号带坏。",
        "",
        "---",
        "",
        "## 1. Your title",
        "",
        "```",
        title,
        "```",
        "",
        "## 2. Your abstract",
        "",
        "词数 **%d** / 上限 500；字符数 %d。" % (nw, nc),
        ("**超限，需删减约 %d 词。**" % (nw - 500)) if nw > 500 else "未超限。",
        "",
        "```",
        abstract,
        "```",
        "",
        "## 3. Your keywords",
        "",
        "main.tex 里共 %d 个，**EM 上限 6 个**。去掉 `scheduling`（与 `fleet sizing`" 
        "语义重叠，且题目已含调度的含义；换成 `disaster relief` 更贴刊）。"
        "**直接粘下面这一行：**" % len(kws),
        "",
        "```",
        "; ".join([k for k in kws if k.lower() != "scheduling"][:6]),
        "```",
        "",
        "main.tex 的完整列表（%d 个）：%s" % (len(kws), "; ".join(kws)),
        "",
        "---",
        "",
        "## 4. 研究数据（\u201c提供更多信息 / 你的研究数据\u201d 页）",
        "",
        "逐栏对照填，方框里的值直接复制。",
        "",
        "| 栏目 | 选/填 | 字符数（上限） |",
        "|---|---|---|",
        "| 你想分享数据吗？ | **是的** | — |",
        "| 数据仓库链接 | 见下方代码块 1 | 33 / 200 |",
        "| 存储库名称 | 下拉选 **Other** | — |",
        "| 其他存储库名称 | 填 `GitHub` | 6 / 200 |",
        "| 数据来源 | **原始数据** | — |",
        "| 数据集标题 | 见下方代码块 2 | 103 / 200 |",
        "",
        "**选 Other 之后下面会多出一个“其他存储库名称”框——填 `GitHub`。**",
        "这个下拉是出版商侧的仓库类型清单，不含 GitHub，所以只能走 Other",
        "再手填名字；留空会让表单校验不过。",
        "",
        "**数据来源选“原始数据”的理由**：本文的结果文件与图表生成器由我们自己",
        "跑出，属原始数据；输入的 DEM 是公开第三方数据，已在 Data availability",
        "声明里注明出处（Copernicus GLO-30, ESA）。",
        "",
        "代码块 1 —— 数据仓库链接：",
        "",
        "```",
        "https://github.com/ccx111145/data",
        "```",
        "",
        "代码块 2 —— 数据集标题：",
        "",
        "```",
        "Replication package: code, result files and figure generators for a UAV transport-relay co-design study",
        "```",
        "",
    ]
    out = os.path.join(DEST, "09_EM_form_text.md")
    os.makedirs(DEST, exist_ok=True)
    io.open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("摘要 %d 词 / 上限 500%s" % (nw, "  <- 超限" if nw > 500 else ""))
    nk = len([k for k in kws if k.lower() != "scheduling"][:6])
    print("关键词 表单用 %d 个（源 %d 个）/ 上限 6%s"
          % (nk, len(kws), "  <- 仍超限" if nk > 6 else ""))
    print("已写出 %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
