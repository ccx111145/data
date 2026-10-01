# -*- coding: utf-8 -*-
"""make_docx_cn.py —— 把中文论文（LaTeX）转成可编辑的 Word（.docx）

为什么不用现成的一条命令：
  * LibreOffice 导入 .tex 只把源码当纯文本倒出来（实测 1344 段全是 LaTeX 源码）；
  * tex4ht / make4ht 被 `\\ctexset` 那类中文排版设置打断，报
    "Missing number, treated as zero" 后整体失败。
所以走 pandoc，但 pandoc 不认本文自定义的两百多个数字宏
（`\\QthreeDpCells{}` 之类）与 `\\InputRes` / `\\Dfig` 这两个自造命令，
必须先就地展开成数值、再把插图路径改成 pandoc 认识的写法。

流程：
  1. 读 paper/numbers.tex 与 paper/q3_gap.tex，建立 宏名 -> 字面值 表；
  2. 把宏调用（含 `{}` 与可选参数形式）替换成字面值；
  3. `\\Dfig[宽]{文件}{图注}{标签}` -> 标准 figure + \\includegraphics；
  4. 展开 `\\InputRes` / `\\input` 的表格片段；
  5. 只保留导言区里 pandoc 需要的部分，正文交给 pandoc -> docx。

输出：桌面 D题_中文稿_Word\\中文论文.docx
用法：python code/make_docx_cn.py
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(BASE, "paper")
FIGS = os.path.join(BASE, "figs")
DESK = os.path.join(os.path.expanduser("~"), "Desktop", "D题_中文稿_Word")
PANDOC = os.path.join(os.environ.get("LOCALAPPDATA", ""), "pandoc-dsh", "pandoc.exe")


def read(p: str) -> str:
    return io.open(p, encoding="utf-8").read()


def load_macros() -> dict:
    """把 numbers.tex / q3_gap.tex 里的 \\newcommand 全部读成字典。"""
    mac: dict[str, str] = {}
    for fn in ("numbers.tex", "q3_gap.tex", "tables.tex"):
        p = os.path.join(PAPER, fn)
        if not os.path.exists(p):
            continue
        t = read(p)
        # 支持 \newcommand{\Name}{值} 与带参数的最简形式
        for m in re.finditer(r"\\newcommand\{\\([A-Za-z@]+)\}(?:\[(\d+)\])?\{(.*?)\}\s*$",
                             t, re.M | re.S):
            mac[m.group(1)] = m.group(3).strip()
    return mac


def expand_macros(t: str, mac: dict) -> tuple[str, list[str]]:
    """反复替换宏调用，直到不动点；返回 (文本, 未解析的宏名列表)。"""
    unresolved: set[str] = set()
    for _ in range(6):
        before = t

        def rep(m):
            name = m.group(1)
            if name in mac:
                return "{%s}" % mac[name]
            unresolved.add(name)
            return m.group(0)

        # \Name 或 \Name{} 或 \Name{...}（宏多为零参，最多吞掉一层空花括号）
        t = re.sub(r"\\([A-Za-z@]+)\s*(?:\{\s*\})?", rep, t)
        if t == before:
            break
    return t, sorted(unresolved)


def expand_figs(t: str) -> str:
    """\\Dfig[宽]{文件}{图注}{标签} -> 标准 figure 环境。"""
    def rep(m):
        w = (m.group(1) or "0.9").strip("[]")
        fn, cap, lab = m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
        path = os.path.join(FIGS, fn)
        if not os.path.exists(path):
            stem = os.path.splitext(fn)[0]
            for ext in (".png", ".pdf"):
                if os.path.exists(os.path.join(FIGS, stem + ext)):
                    fn = stem + ext
                    break
        return ("\n\\begin{figure}[htbp]\n\\centering\n"
                "\\includegraphics[width=%s\\linewidth]{%s}\n"
                "\\caption{%s}\n\\label{%s}\n\\end{figure}\n" % (w, fn, cap, lab))
    return re.sub(r"\\Dfig(?:\[([^\]]*)\])?\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}", rep, t)


def expand_inputs(t: str) -> str:
    """就地展开 \\InputRes{...} 与 \\input{...}。"""
    def rep(m):
        name = m.group(1).strip()
        for cand in (name, os.path.join("paper", name),
                     os.path.join(PAPER, os.path.basename(name))):
            if os.path.exists(cand):
                return read(cand)
        p = os.path.join(PAPER, os.path.basename(name))
        return read(p) if os.path.exists(p) else ""
    return re.sub(r"\\(?:InputRes|input|include)\{([^}]*)\}", rep, t)


def fix_math(t: str) -> str:
    """pandoc 的数学解析器不认旧式字体命令 \\rm / \\bf / \\it / \\sf / \\tt，
    会报 "unexpected control sequence \\rm" 并把整条公式退化成纯 TeX 文本。
    把它们改写成 \\mathrm / \\mathbf / \\mathit / \\mathsf / \\mathtt。
    注意先处理 `{\\rm xxx}` 这种分组写法，再处理裸 `\\rm `。"""
    for old, new in (("rm", "mathrm"), ("bf", "mathbf"), ("it", "mathit"),
                     ("sf", "mathsf"), ("tt", "mathtt")):
        # 替换串里的反斜杠在 re.sub 中是转义引导，必须写成 \\
        # 但 lambda 返回的是**字面串**（不经 re.sub 转义），只需一个反斜杠
        t = re.sub(r"\{\s*\\%s\s+([^{}]*)\}" % old,
                   lambda m, n=new: "\\%s{%s}" % (n, m.group(1).strip()), t)
        t = re.sub(r"\\%s\s+" % old, "\\\\%s " % new, t)
    return t


def strip_body(t: str) -> str:
    """取 \\begin{document}..\\end{document} 之间的正文。"""
    i = t.find("\\begin{document}")
    j = t.find("\\end{document}")
    if i < 0:
        return t
    return t[i + len("\\begin{document}"):j if j > 0 else len(t)]


def _localize_toc(path: str, src: str, dst: str) -> None:
    """把 docx 里目录标题的英文原文换成中文，其余字节原样保留。

    docx 就是一个 zip；只重写 word/document.xml，其它 entry 用原压缩方式拷回去，
    这样不会破坏样式表、关系表与图片。
    """
    import zipfile as _zip
    tmp = path + ".tmp"
    n = 0
    with _zip.ZipFile(path, "r") as zin, _zip.ZipFile(tmp, "w", _zip.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                s = data.decode("utf-8")
                # 目录标题是独立段落里的一个 w:t，精确替换文本节点内容
                s2 = s.replace(">%s</w:t>" % src, ">%s</w:t>" % dst)
                n = s2.count(">%s</w:t>" % dst) - s.count(">%s</w:t>" % dst)
                data = s2.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)
    print("目录标题已本地化：%s -> %s（%d 处）" % (src, dst, n))


def main() -> int:
    if not os.path.exists(PANDOC):
        print("找不到 pandoc：%s" % PANDOC)
        return 1
    src = os.path.join(PAPER, "paper.tex")
    t = read(src)
    mac = load_macros()
    print("已读入数字宏 %d 个" % len(mac))

    t = expand_inputs(t)
    t = expand_figs(t)
    t, unresolved = expand_macros(t, mac)
    print("正文展开完成；未解析宏 %d 个" % len(unresolved))
    if unresolved:
        print("  " + ", ".join("\\" + u for u in unresolved[:20]))

    body = strip_body(t)
    body = fix_math(body)
    os.makedirs(DESK, exist_ok=True)
    # 工作目录放到系统临时区，不要落在交付目录里：
    # 旧版把它建在桌面的 D题_中文稿_Word/_build，里面是 body.tex 加全套插图，
    # 于是交付目录凭空多出 ~25 MB 的中间产物，收件人打开会一脸问号。
    work = os.path.join(tempfile.gettempdir(), "_dsh_docx_cn")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    # 只拷中文稿真正用到的插图：fig_en_* 是英文投稿版专有图，
    # 中文稿从不引用，拷进来只会把 docx 撑大（旧版就是这么做的）。
    copied = 0
    for f in os.listdir(FIGS):
        if f.startswith("fig_en_"):
            continue
        shutil.copy2(os.path.join(FIGS, f), os.path.join(work, f))
        copied += 1
    print("已拷贝插图 %d 张（已跳过 fig_en_*）" % copied)
    io.open(os.path.join(work, "body.tex"), "w", encoding="utf-8").write(body)

    out = os.path.join(DESK, "中文论文.docx")
    ref = os.path.join(DESK, "参考样式.docx")
    cmd = [PANDOC, "body.tex", "-o", out,
           "--from=latex+raw_tex", "--to=docx",
           "--resource-path=%s" % work,
           "--toc", "--toc-depth=3", "--number-sections",
           "--standalone"]
    if os.path.exists(ref):
        cmd.append("--reference-doc=%s" % ref)
    print("调用 pandoc ...")
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if r.returncode != 0:
        print("pandoc 失败：\n%s\n%s" % (r.stdout[-2000:], r.stderr[-2000:]))
        return 1
    if r.stderr.strip():
        print("pandoc 提示：%s" % r.stderr.strip()[:1200])
    print("已写出：%s（%.1f MB）" % (out, os.path.getsize(out) / 1048576))
    # pandoc 生成的目录标题固定是英文 "Table of Contents"，放进中文稿里很突兀。
    # docx 是 zip+xml，直接改 document.xml 里的那一段文字最稳（不碰样式）。
    try:
        _localize_toc(out, "Table of Contents", "目录")
    except Exception as e:                                          # noqa: BLE001
        print("目录标题本地化跳过：%s" % e)
    # 中间产物用完即清，交付目录里只留 docx 本身
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
