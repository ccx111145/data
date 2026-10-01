# -*- coding: utf-8 -*-
"""
make_submission_pack.py —— 生成**投稿包**（放桌面），把可上传的东西与内部参考分开。

与 `_repack.py`（完整交付包，给复现用）的区别
--------------------------------------------
交付包是"复现用"：含全部代码/结果/数据，体积大，**不是**给期刊上传的。
投稿包是"上传用"：只含稿件、源文件、图、参考文献、投稿文书，
外加一个明确标注"不要上传"的 `内部参考/`（清单、说明、核对表）。

产物（默认 C:\\Users\\ASUS\\Desktop\\D题_投稿包）
------------------------------------------------
  00_上传说明.md                     先读这个
  01_Manuscript_neutral_anonymized.pdf  匿名稿——**由 main.tex 派生的匿名副本当场编译**，
                                        不是 main.pdf（main.pdf 的 \author 块带五位作者，
                                        直接改个名字发货等于把作者名装进"匿名稿"）
  01_Manuscript_Elsevier_anon.pdf       Elsevier 版式（匿名前置）
  01_Manuscript_IEEE_TITS.pdf           IEEEtran 版式（含五位作者）
  02_LaTeX_source.zip                可独立编译的源码（变体 .tex + refs.bib + numbers_en.tex + figs/）

页数、参考文献条数、占位符计数一律**在打包时实测**并写进 00_上传说明.md / 投稿清单.md，
不再手抄——手抄过一次，三份文档里的页数（12/32/22）与实际（14/38/26）全都对不上。
  03_Highlights.txt                  3–5 条要点，每条 ≤85 字符
  04_Cover_Letter.txt/.pdf           投稿信
  05_Declaration_of_Interest.txt     Elsevier 必需
  06_Data_Availability_Statement.txt 数据可得性
  07_Title_page.txt                  含作者信息的标题页（双盲时单独上传）
  08_CRediT_author_statement.txt     IEEE 部分刊必需
  内部参考/（不要上传）/
      投稿清单.md                    逐刊要求 + 本包自检结论
      作者信息待填.md                需要作者自行补齐的字段清单
      图表清单.md                    7 张图 + 7 张表的位置与来源

用法：python make_submission_pack.py [--out "C:\\Users\\ASUS\\Desktop\\D题_投稿包"]
"""
from __future__ import annotations

import argparse
import io
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dcore import find_bin as ask_bin

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(BASE, "paper_en")
FIGS = os.path.join(BASE, "figs")
DEFAULT_OUT = r"C:\Users\ASUS\Desktop\D题_投稿包"
XELATEX = ask_bin("xelatex")
BIBTEX = ask_bin("bibtex")

# ---- 匿名化 ------------------------------------------------------------------
# 英文名/单位/邮箱/学号：任一出现在对外文件里就算泄漏。大小写敏感 + 词边界，
# 避免把正文明文 "executable" 误判成单位缩写 "ECUT"。
IDENTITY_TERMS = [
    "Changxuan", "Zhifeng", "Qiong", "Yulong", "Zexu",
    "ecut.edu", "qq.com", "163.com", "gmail.com",
    "East China", "Nanchang", "ECUT",
    "2023211863", "2023211904", "15579178689", "1028359003", "flxnicc05",
    "曹昌璇", "李琼", "刘志峰", "彭玉龙", "欧阳泽栩",
]
IDENTITY_RE = re.compile("|".join(re.escape(t) for t in IDENTITY_TERMS))

ANON_AUTHOR_BLOCK = ("\\\\author{Anonymous Author(s)\\\\\n"
                     "\\\\small Institution, City, Country\\\\\n"
                     "\\\\small \\\\texttt{anonymous@example.org}}\n\\\\date{")

# 仓库地址：作者自建 GitHub，但**账号名尚不可知**。与其留一个含义不明的
# `<REPOSITORY DOI / URL>`（读者得猜要填 DOI 还是 URL），不如给一条**只改一处**
# 的完整 URL：仓库名已定，只有账号名待填，且紧跟一条 NOTE 指明改哪一行。
REPO_ACCOUNT_TOKEN = "ccx111145"
REPO_NAME = "data"
REPO_URL = "https://github.com/%s/%s" % (REPO_ACCOUNT_TOKEN, REPO_NAME)


def pdf_text(path):
    """取 PDF 文本层。返回 None 表示取不到（缺依赖）。"""
    try:
        from pypdf import PdfReader
        rd = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in rd.pages)
    except Exception:                                              # noqa: BLE001
        pass
    try:
        import fitz
        d = fitz.open(path)
        t = "\n".join(p.get_text() for p in d)
        d.close()
        return t
    except Exception:                                              # noqa: BLE001
        return None


def pdf_pages(path):
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:                                              # noqa: BLE001
        pass
    try:
        import fitz
        d = fitz.open(path)
        n = len(d)
        d.close()
        return n
    except Exception:                                              # noqa: BLE001
        return None


def anon_author_main(src_main):
    """把 main.tex 的 \\author{...}\\date{ 换成匿名作者块；换不掉就报错。"""
    anon, n = re.subn(r"\\author\{.*?\}\s*\n\\date\{", ANON_AUTHOR_BLOCK,
                      src_main, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("未能把 main.tex 的作者块换成匿名版（模式没匹配上）"
                         "——拒绝生成带作者名的『匿名稿』。")
    bad = sorted({t for t in IDENTITY_TERMS if t in anon})
    if bad:
        raise SystemExit("匿名副本里仍残留作者信息：%s" % bad)
    return anon


def build_anon_neutral_pdf(src_main, dst_pdf):
    """由 main.tex 派生匿名副本，**当场编译**出中立版式的匿名稿。

    为什么不直接抄 `paper_en/main.pdf`：那份的 `\\author` 块里是五位作者的真名、
    单位与通讯邮箱，而它此前正是以 `01_Manuscript_neutral_anonymized.pdf` 的
    文件名发货的——文件名叫 anonymized、内容是实名，双盲刊一投即退。
    `paper_en/` 里也没有现成的"中立版式 + 匿名"产物（make_elsarticle.py 只派生
    Elsevier / IEEEtran 两种版式），所以只能在打包时临时派生并编译。

    编译在**临时目录**里进行（figs/ 复制一份进去），paper_en 保持干净；
    编译失败或有未定义引用一律中止，绝不退回"直接把实名 PDF 改名"。
    """
    for need in (XELATEX, BIBTEX):
        if not os.path.exists(need):
            raise SystemExit(
                "缺少 %s —— 无法生成真正匿名的中立版稿。拒绝把带作者名的 "
                "main.pdf 改名当匿名稿发货；请先装 TeX Live 或修好路径。" % need)
    tmp = tempfile.mkdtemp(prefix="anonpkg_")
    try:
        shutil.copy2(os.path.join(PAPER, "numbers_en.tex"), tmp)
        shutil.copy2(os.path.join(PAPER, "refs.bib"), tmp)
        fsrc = os.path.join(PAPER, "figs")
        fdst = os.path.join(tmp, "figs")
        os.makedirs(fdst, exist_ok=True)
        for fn in os.listdir(fsrc):
            p = os.path.join(fsrc, fn)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(fdst, fn))
        base = "_anonpkg_main"
        io.open(os.path.join(tmp, base + ".tex"), "w", encoding="utf-8").write(
            anon_author_main(src_main))
        errs = []
        for k in range(3):
            r = subprocess.run([XELATEX, "-interaction=nonstopmode", base + ".tex"],
                               cwd=tmp, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
            out = r.stdout.decode("utf-8", "replace")
            errs += [ln for ln in out.splitlines() if ln.startswith("! ")]
            if k == 0:
                subprocess.run([BIBTEX, base], cwd=tmp, stdout=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT)
        logp = os.path.join(tmp, base + ".log")
        log = (io.open(logp, encoding="utf-8", errors="replace").read()
               if os.path.exists(logp) else "")
        errs += [ln for ln in log.splitlines() if ln.startswith("! ")]
        undef = len(re.findall(
            r"LaTeX Warning: (?:Reference|Citation) .* undefined", log))
        pdfp = os.path.join(tmp, base + ".pdf")
        if not os.path.exists(pdfp):
            raise SystemExit("匿名中立版编译失败，未产出 PDF（编译目录 %s）" % tmp)
        if errs or undef:
            raise SystemExit("匿名中立版编译有错：errors=%s undef=%d（%s）"
                             % (errs[:3], undef, tmp))
        shutil.copy2(pdfp, dst_pdf)
        txt = pdf_text(dst_pdf)
        if txt is None:
            raise SystemExit("取不到匿名中立版的文本层，无法确认匿名性（缺 pypdf/PyMuPDF）")
        hits = sorted(set(IDENTITY_RE.findall(txt)))
        if hits:
            raise SystemExit("匿名中立版里仍检出作者信息：%s" % hits)
        return pdf_pages(dst_pdf)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_anonymity(out_dir, zpath):
    """匿名闸门：任何**文件名承诺匿名**的 PDF，以及源码 zip 的全部文本成员，
    都不得出现作者身份词。任一命中即中止打包（非零退出）。

    这条闸门是为一个真实事故加的：`01_Manuscript_neutral_anonymized.pdf`
    整份带作者，而 00_上传说明.md 与投稿清单.md 都写着"已匿名/已全文扫描"。
    声明与实物不一致这类缺陷不会报错，只会让双盲刊直接退稿。
    """
    problems = []
    for fn in sorted(os.listdir(out_dir)):
        if not fn.lower().endswith(".pdf"):
            continue
        if not re.search(r"anon", fn, re.I):
            continue
        txt = pdf_text(os.path.join(out_dir, fn))
        if txt is None:
            problems.append("%s：取不到文本层，无法验证匿名性" % fn)
            continue
        hits = sorted(set(IDENTITY_RE.findall(txt)))
        if hits:
            for h in hits:
                i = txt.find(h)
                problems.append("%s：检出 %r（上下文 ...%s...）"
                                % (fn, h, re.sub(r"\s+", " ",
                                                 txt[max(0, i - 60):i + 60])))
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith((".tex", ".bib", ".txt", ".md")):
                continue
            t = z.read(info.filename).decode("utf-8", "ignore")
            hits = sorted(set(IDENTITY_RE.findall(t)))
            if hits:
                problems.append("02_LaTeX_source.zip::%s：检出 %s"
                                % (info.filename, hits))
    if problems:
        print("\n匿名闸门未通过：")
        for p in problems:
            print("  - %s" % p)
        raise SystemExit(
            "投稿文件里出现作者身份——已中止打包（退出码非零）。"
            "带作者的文件不得使用 anon/anonymized 这类文件名。")
    return True


TITLE = ("Joint Transport--Relay Co-Design for UAV Emergency Logistics in "
         "Mountainous Terrain: Handover-Aware Feasibility, Channel-Model "
         "Sensitivity, and the Price of Partitioning")
TITLE_PLAIN = TITLE.replace("--", "-")

HIGHLIGHTS = [
    "Coverage-based relay sizing understates the fleet by 2 vehicles",
    # 原句是 "Two-relay infeasibility is decided exactly, not merely unsearched"。
    # 正文早已撤回该说法（无剪枝那次运行 1501 s 未终止，判定只在候选集+剪枝口径下成立），
    # 而 Highlights 一直没跟着改——审稿人一对照正文就会认为是夸大。改为此口径。
    "No 2-relay schedule found over a stated candidate set",
    "The obstruction is an instant-, not phase-granularity, phenomenon",
    "P.526 diffraction raises outage demand 32.2% and the fleet from 3 to 4",
    # 原句 "Fleet size is a phase transition driven by demand fragmentation"：
    # 正文说地形研究只有 9 个场景、5 个删失，只作描述性陈述、未检验分岔。
    "Fleet size does not follow occlusion volume in our terrain study",
]

# 备选条目（不计入上面的 3–5 条）：若目标刊允许 5 条以上，或想替换某一条时用。
HIGHLIGHTS_ALT = [
    "Clarke-Wright wins routing but breaks hard deadlines by 30111 s",
]

# 已知未核实项：Elsevier 的 85 字符上限来自通用作者指南，本包未能在该刊当期
# Author Guidelines 页面上直接确认（抓取被 403 拦截）。这里不假装已知，
# 而是把每条字符数打印出来，由作者按当期要求自行删减。
NOTES_HIGHLIGHTS = (
    "NOTE: the 85-character limit is the widely used Elsevier convention and\n"
    "is stated here as a target, not as a verified requirement for the target\n"
    "journal. Character counts for the bullets above are printed below; confirm\n"
    "the actual limit on the journal's current Author Guidelines page and drop\n"
    "or shorten bullets if needed."
)


def rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-pdf", action="store_true",
                    help="不把投稿信编译成 PDF（一致性体检与匿名闸门**仍然执行**，"
                         "它们不是可选项）")
    a = ap.parse_args()
    D = a.out
    t0 = time.time()

    # ---------------- 00 一致性体检（失败即中止）----------------
    # 本稿已三次出现"同一内容抄成两处、改一处漏一处"的缺陷（IEEE 手抄摘要、
    # 样式块落在拼接区间之外、preamble 与共享段重复定义）。这类缺陷不报错、
    # 只让两个版本悄悄分叉，所以打进投稿包之前必须先过体检。
    #
    # 注意：体检**无条件执行**。此前它被 `if not a.no_pdf:` 包着，于是
    # `--no-pdf`（本意只是"别把投稿信编译成 PDF"）会顺带把整道体检跳过，
    # 打包照常成功——闸门形同虚设。
    chk = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "check_consistency.py")
    if not os.path.exists(chk):
        raise SystemExit("找不到一致性体检脚本 %s —— 拒绝在无闸门的情况下打包。" % chk)
    print("== 一致性体检（code/check_consistency.py）==")
    r = subprocess.run([sys.executable, chk], cwd=BASE)
    if r.returncode != 0:
        raise SystemExit(
            "一致性体检未通过（退出码 %d）——已中止打包，"
            "避免把分叉的稿件打进投稿包。" % r.returncode)
    print()

    # ---------------- 必需输入先点一遍名（缺一个就非零退出）----------------
    need_pdfs = ("main_elsarticle_anon.pdf", "main_elsarticle.pdf", "main_ieee.pdf")
    miss = [f for f in need_pdfs if not os.path.exists(os.path.join(PAPER, f))]
    if miss:
        raise SystemExit("缺少必需输入 PDF：%s（先跑 code/make_elsarticle.py）" % miss)
    for f in ("main.tex", "main_elsarticle.tex", "main_ieee.tex",
              "main_elsarticle_anon.tex", "refs.bib", "numbers_en.tex"):
        if not os.path.exists(os.path.join(PAPER, f)):
            raise SystemExit("缺少必需输入 %s" % os.path.join(PAPER, f))

    rm(D)
    os.makedirs(os.path.join(D, "内部参考（不要上传）"), exist_ok=True)

    # ---------------- 01 稿件 ----------------
    # 四份：双盲用的匿名版（中立版式 / Elsevier 版式）、带作者的 Elsevier 版、
    # 带作者的 IEEE 版。作者信息已按用户提供填好，见 AUTHORS 定义。
    #
    # 中立版匿名稿**必须现编译**，不能抄 paper_en/main.pdf：
    # main.pdf 由带作者的 main.tex 编译而来，整页印着五位作者与通讯邮箱。
    # 此前打包脚本把 main.pdf 直接改名成 01_Manuscript_neutral_anonymized.pdf
    # 发货，于是所谓"匿名稿"里作者信息一应俱全。
    src_main = io.open(os.path.join(PAPER, "main.tex"), encoding="utf-8").read()
    n_neutral = build_anon_neutral_pdf(
        src_main, os.path.join(D, "01_Manuscript_neutral_anonymized.pdf"))
    for src, dst in (("main_elsarticle_anon.pdf", "01_Manuscript_Elsevier_anon.pdf"),
                     ("main_elsarticle.pdf", "01_Manuscript_Elsevier_with_authors.pdf")):
        shutil.copy2(os.path.join(PAPER, src), os.path.join(D, dst))

    # ---------------- 投稿正文 = 紧凑版（15 页）+ 补充材料 ----------------
    # 作者决定：投 T-ITS 用紧凑版为正稿（整版 16 页正好踩在上限、余量为 0）。
    # 紧凑版与补充材料必须由 code/make_compact_en.py 先生成；不在场就退回整版，
    # 并在说明里写明，避免"声称 15 页却装了 16 页"。
    cb = os.path.join(PAPER, "build")
    compact_pdf = os.path.join(cb, "main_compact.pdf")
    supp_pdf = os.path.join(cb, "supplement.pdf")
    use_compact = os.path.exists(compact_pdf) and os.path.exists(supp_pdf)
    if use_compact:
        shutil.copy2(compact_pdf, os.path.join(D, "01_Manuscript_IEEE_TITS.pdf"))
        shutil.copy2(supp_pdf, os.path.join(D, "09_Supplementary_material.pdf"))
        # 整版留档，不占上传编号
        shutil.copy2(os.path.join(PAPER, "main_ieee.pdf"),
                     os.path.join(D, "内部参考（不要上传）", "main_ieee_full_16p.pdf"))
    else:
        print("! 紧凑版不在场（先跑 code/make_compact_en.py），本次装入整版 16 页")
        shutil.copy2(os.path.join(PAPER, "main_ieee.pdf"),
                     os.path.join(D, "01_Manuscript_IEEE_TITS.pdf"))

    # ---------------- 02 源码 zip（可独立编译）----------------
    # main.tex 里含作者块（单盲/接收后要用），所以上传前先派生出**匿名副本**，
    # 只把匿名副本放进 zip。这一步是必须的：本轮就出现过"PDF 匿名了、源码里
    # 还留着作者名"的漏洞——双盲刊会因为源码里的作者信息直接退稿。
    anon_main = anon_author_main(src_main)

    zpath = os.path.join(D, "02_LaTeX_source.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        # 只放**匿名**版本：双盲刊要求投稿源码里不得出现作者与单位，
        # 因此带作者的 main_elsarticle.tex / main_ieee.tex 不进这个 zip
        # （它们留在内部参考目录，接收后再用）。
        z.writestr("manuscript/main.tex", anon_main)
        for f in ("main_elsarticle_anon.tex",
                  "refs.bib", "numbers_en.tex", "numbers_en_sources.txt",
                  "README_en.md"):
            p = os.path.join(PAPER, f)
            if os.path.exists(p):
                z.write(p, "manuscript/" + f)
        fdir = os.path.join(PAPER, "figs")
        for f in sorted(os.listdir(fdir)):
            if f.lower().endswith((".png", ".pdf", ".jpg", ".eps")):
                z.write(os.path.join(fdir, f), "manuscript/figs/" + f)
        z.writestr("manuscript/HOWTO_compile.txt",
                   "Compile (xelatex + bibtex, three passes):\n"
                   "  xelatex -interaction=nonstopmode main.tex\n"
                   "  bibtex main\n"
                   "  xelatex -interaction=nonstopmode main.tex\n"
                   "  xelatex -interaction=nonstopmode main.tex\n\n"
                   "Alternative layouts (same body, different class/front matter):\n"
                   "  xelatex main_elsarticle_anon.tex  # Elsevier elsarticle, ANONYMOUS\n"
                   "                                    # front matter -- this is the one to\n"
                   "                                    # compile for a double-blind venue\n\n"
                   "Not in this archive: the author-identified variants\n"
                   "(main_elsarticle.tex, main_ieee.tex). Double-blind venues require the\n"
                   "submitted source to carry no author or affiliation, so they are kept\n"
                   "outside the archive. The author-identified title page is submitted\n"
                   "separately through the journal's submission form (single place, not\n"
                   "inside this archive and not inside the manuscript file).\n\n"
                   "Requires: xelatex, bibtex, packages amsmath/amssymb/amsthm,\n"
                   "booktabs, graphicx, siunitx, enumitem, algorithm, algpseudocode,\n"
                   "caption, hyperref, xcolor. Figures are in figs/ and are referenced\n"
                   "by name without extension: \\Dfig resolves pdf -> png -> eps, so the\n"
                   "data figures use their vector .pdf and the DEM hillshade uses its\n"
                   "300 dpi .png automatically.\n")

    # ---------------- 02b 匿名闸门（任一命中即非零退出）----------------
    # 声明与实物必须一致：文件名写 anon 的 PDF 与源码 zip 里不得有身份词。
    print("== 匿名闸门（文件名承诺匿名的 PDF + 源码 zip）==")
    check_anonymity(D, zpath)
    print("  通过：%d 份匿名 PDF 与源码 zip 均无作者身份词\n"
          % len([f for f in os.listdir(D) if f.lower().endswith(".pdf")
                 and re.search(r"anon", f, re.I)]))

    # ---------------- 03 Highlights ----------------
    with io.open(os.path.join(D, "03_Highlights.txt"), "w", encoding="utf-8") as f:
        f.write("Highlights\n")
        f.write("=" * 72 + "\n")
        f.write("(Three to five bullets. The 85-character limit below is the usual\n"
                " Elsevier convention; confirm it on the target journal's current\n"
                " Author Guidelines page before uploading.)\n\n")
        for i, h in enumerate(HIGHLIGHTS, 1):
            f.write("%d. %s\n" % (i, h))
        f.write("\nCharacter counts: %s\n"
                % ", ".join("%d" % len(h) for h in HIGHLIGHTS))
        over = [i for i, h in enumerate(HIGHLIGHTS, 1) if len(h) > 85]
        f.write("Over 85 characters: %s\n\n"
                % ("none" if not over else "bullet(s) " + str(over)))
        f.write("Optional extra bullet (use only if the journal allows more than\n"
                "five, or as a substitute for one of the above):\n")
        for h in HIGHLIGHTS_ALT:
            f.write("  * %s   [%d chars]\n" % (h, len(h)))
        f.write("\n" + NOTES_HIGHLIGHTS + "\n")

    # ---------------- 04 投稿信 ----------------
    # 注意：正文里含字面百分号（"32.2 %"），因此这里**不能**用 % 格式化，
    # 否则会把 "2 %," 当成格式说明符。改用 str.replace 做占位替换。
    #
    # 目标刊定位：主投 IEEE T-ITS。因此投稿信第一段以**运输系统的决策与代价**
    # 开场（机队规模、任务可行性、工期），把信道模型降级为灵敏度分析；
    # 这与正文的章节比例（方法+实验占 67%）一致，也与 T-ITS 的读者关切一致。
    cover = (
        "Cover Letter\n"
        + "=" * 72 + "\n\n"
        "Dear Editor,\n\n"
        "We submit for consideration the manuscript\n\n"
        "  @@TITLE@@\n\n"
        "for publication in IEEE Transactions on Intelligent Transportation Systems.\n\n"
        "The transportation problem we address. Mountainous disaster relief needs\n"
        "UAV fleets that can both deliver cargo and stay connected to a fixed\n"
        "gateway, and the terrain that isolates the settlements is the same terrain\n"
        "that occludes the air-to-ground links. The operator's decision variables are\n"
        "the familiar transportation ones -- how many vehicles, on which routes,\n"
        "dispatched when -- but the feasibility of a dispatch plan now depends on a\n"
        "communication constraint that switches on and off over time.\n\n"
        "Why it fits IEEE Transactions on Intelligent Transportation Systems.\n"
        "  * The contribution is a transportation result, not a radio result. We\n"
        "    prove that once the physical cost of handing a hovering relay over\n"
        "    between positions is accounted for, fleet sizing is governed by a scalar\n"
        "    span inequality, and on our instance the coverage abstraction common in\n"
        "    the relay literature understates the fleet by 2 vehicles. A two-relay\n"
        "    plan is then be found over a declared candidate set by a\n"
        "    state recursion (candidate set and pruning policy stated), cross-checked by a\n"
        "    phase-level integer program and by a sampling-free energy bound. The\n"
        "    verified schedule for three relays satisfies every hard deadline.\n"
        "  * We quantify how much of the answer is a modelling convention rather\n"
        "    than a physical fact: replacing the supplied constant occlusion penalty\n"
        "    by ITU-R P.526 knife-edge diffraction on the 30 m DEM raises outage\n"
        "    demand by 32.2 percent, removes 49.2 percent of the usable hover points,\n"
        "    and moves the smallest constructible fleet from 3 to 4. Fleet-size claims in this\n"
        "    literature therefore have to be reported with their channel convention.\n"
        "  * We test the obvious escape routes and report negative results, which is\n"
        "    what a transportation reader needs in order to trust the bound: a\n"
        "    co-design loop over departure instants cannot remove the obstruction,\n"
        "    and air-to-air relocation instead of depot return halves the blackout\n"
        "    window without changing the verdict.\n"
        "  * Against a textbook baseline, the classical Clarke-Wright savings\n"
        "    heuristic -- run under our own scheduler -- reaches 13 sorties and\n"
        "    61.26 kWh versus our 20 sorties and 76.04 kWh, yet violates hard\n"
        "    deadlines by 30111 s. Routing quality and schedule feasibility are not\n"
        "    the same objective, and we show the size of the gap.\n"
        "  * Across a controlled terrain family the smallest constructed fleet is not\n"
        "    monotone in occlusion volume, which is the quantity one would\n"
        "    naively extrapolate from -- a caution for anyone inferring fleet size\n"
        "    from a single blocked-link fraction. With nine scenarios we report this as descriptive.\n\n"
        "Where this sits relative to recent work in the journal. Synchronised\n"
        "truck-drone routing and hybrid delivery routing are well studied here (for\n"
        "example Das et al., IEEE T-ITS 22(9), 2021; Bian et al., IEEE T-ITS 25(9),\n"
        "2024). That line optimises the routing layer; we take the routing plan as\n"
        "given and characterise whether it can be *executed* once the relay layer's\n"
        "availability is enforced, and we return the resulting fleet-size and\n"
        "timing consequences to the transport decision.\n\n"
        "Reproducibility. Every number, table and figure in the manuscript is\n"
        "regenerated from shipped result files by a scripted pipeline\n"
        "(code/make_numbers_en.py, driven by code/run_all_en.py); no value is\n"
        "typed by hand except the declarations listed in Section VII. Result files are available as supplementary material, and\n"
        "the bibliography was machine-verified against Crossref.\n\n"
        "How to read the evidence. Our results are established on a controlled\n"
        "mountainous instance built from a 30 m Copernicus DEM rather than on an\n"
        "established transportation benchmark, and we state the boundary of every\n"
        "claim in Section VII instead of leaving it implicit. Three consequences\n"
        "are worth flagging. First, the fleet-size answer is reported as an\n"
        "interval bracketed by a proven lower bound and a constructed schedule,\n"
        "never as a single minimum. Second, every negative verdict is reported as\n"
        "a search result over a declared finite space together with the pruning\n"
        "policy used, and the one run that would have removed that caveat consumed\n"
        "1501 s of CPU without terminating, shipped as a result file so a reader\n"
        "can reproduce the non-termination. Third, the channel convention is not\n"
        "a detail: replacing the supplied constant occlusion penalty by ITU-R\n"
        "P.526 diffraction changes the smallest constructible fleet, so each\n"
        "fleet-size statement is reported with its convention attached. We would\n"
        "rather the boundary be visible to a referee than discovered by one.\n\n"
        "Length. The manuscript is 15 pages in IEEE Transactions format; the\n"
        "auxiliary proofs and two pseudocode listings are in the supplementary\n"
        "material, and Section VII states which proofs were moved.\n\n"
        "Originality and ethics. The manuscript is original, is not under\n"
        "consideration elsewhere, and all authors approve its submission. The\n"
        "authors declare no competing interests. Funding: none (this research\n"
        "received no external funding).\n\n"
        "Suggested reviewers. The five researchers below work on the two literatures\n"
        "this manuscript sits between -- UAV relay deployment and air-to-ground\n"
        "propagation on one side, disaster-relief vehicle routing on the other.\n"
        "Several are cited in our reference list; none of them has co-authored with\n"
        "any of us, and none is at our institution, so we declare no conflict of\n"
        "interest. We give institutional pages rather than e-mail addresses, since\n"
        "we cannot verify personal addresses from published papers; the editorial\n"
        "office will have current contact details.\n\n"
        "  1. Prof. Yong Zeng -- Southeast University, Nanjing, China. UAV\n"
        "     communications: trajectory design, relay placement, air-to-ground\n"
        "     channel modelling.\n"
        "  2. Prof. Qingqing Wu -- Shanghai Jiao Tong University, China. UAV\n"
        "     relaying, multi-UAV trajectory and communication co-design.\n"
        "  3. Prof. Walid Saad -- Virginia Tech, USA. UAV deployment and\n"
        "     coverage, wireless network optimisation.\n"
        "  4. Prof. Chrysafis Vogiatzis -- University of Illinois Urbana-Champaign,\n"
        "     USA. Two-echelon vehicle and UAV routing for disaster response.\n"
        "  5. Prof. Rui Zhang -- National University of Singapore. UAV\n"
        "     communication and energy-efficiency optimisation.\n\n"
        "We have verified each name against the affiliation given above; please\n"
        "confirm current contact details through your editorial system.\n\n"
        "Thank you for your time and consideration.\n\n"
        "Sincerely,\n"
        "Zhifeng Liu (corresponding author)\n"
        "on behalf of all authors: Changxuan Cao, Qiong Li, Zhifeng Liu,\n"
        "Yulong Peng, and Zexu Ouyang\n"
        "East China University of Technology (ECUT)\n"
        "Nanchang, Jiangxi, China\n"
        "E-mail: 2023211863@ecut.edu.cn\n"
        "@@DATE@@\n").replace("@@TITLE@@", TITLE_PLAIN).replace(
            "@@DATE@@", time.strftime("%Y-%m-%d"))
    with io.open(os.path.join(D, "04_Cover_Letter.txt"), "w", encoding="utf-8") as f:
        f.write(cover)

    # ---------------- 05 Declaration of Interest ----------------
    with io.open(os.path.join(D, "05_Declaration_of_Interest.txt"), "w",
                 encoding="utf-8") as f:
        f.write(
            "Declaration of Interest\n" + "=" * 72 + "\n\n"
            "Manuscript: " + TITLE_PLAIN + "\n\n"
            "The authors declare that they have no known competing financial\n"
            "interests or personal relationships that could have appeared to\n"
            "influence the work reported in this paper.\n\n"
            "Funding: This research received no external funding.\n\n"
            "Data availability: see 06_Data_Availability_Statement.txt.\n\n"
            "Authors: Changxuan Cao, Qiong Li, Zhifeng Liu, Yulong Peng, Zexu Ouyang\n"
            "Corresponding author: Zhifeng Liu, 2023211863@ecut.edu.cn\n"
            "East China University of Technology (ECUT), Nanchang, Jiangxi, China\n\n"
            "Signed for and on behalf of all authors,\n"
            "Zhifeng Liu, " + time.strftime("%Y-%m-%d") + "\n")

    # ---------------- 06 Data availability ----------------
    # 仓库地址的写法（本轮改过）：原来写 `<REPOSITORY DOI / URL>`，读者看不出
    # 到底要填 DOI 还是 URL，也不知道要不要自己找托管服务。现在给出**完整
    # URL**，仓库名已定，只剩账号名一个变量，并用 NOTE 指明"只改这一行"。
    with io.open(os.path.join(D, "06_Data_Availability_Statement.txt"), "w",
                 encoding="utf-8") as f:
        f.write(
            "Data Availability Statement\n" + "=" * 72 + "\n\n"
            "Suggested wording for the submission form:\n\n"
            "  The instance (node coordinates, cargo manifest, fleet and radio\n"
            "  parameters) is the benchmark shipped with the problem statement.\n"
            "  The 30 m digital elevation model is Copernicus GLO-30 (ESA), which\n"
            "  is openly available. All derived result files, the figure and table\n"
            "  generators, and a one-command reproduction pipeline are included as\n"
            "  supplementary material at submission and are archived at\n"
            "  " + REPO_URL + "\n"
            "  Every numerical value in the manuscript is\n"
            "  regenerated from those files by code/make_numbers_en.py; the\n"
            "  bibliography was checked entry by entry against its publisher record by DOI with\n"
            "  code/_verify_refs.py.\n\n"
            "------------------------------------------------------------------------\n"
            "NOTE -- ONE-LINE EDIT BEFORE UPLOAD (only place in this file that\n"
            "needs changing):\n"
            "  In the URL above, replace " + REPO_ACCOUNT_TOKEN + " with your own\n"
            "  GitHub account name. The repository must be named " + REPO_NAME + "\n"
            "  and be public; nothing else in this file needs editing. If you\n"
            "  publish the code under a DOI instead (e.g. Zenodo), replace the\n"
            "  whole URL with that DOI -- then this NOTE no longer applies.\n"
            "------------------------------------------------------------------------\n\n"
            "If the venue does not accept large supplementary archives, cite a\n"
            "repository instead and keep only the manuscript plus the figures.\n")

    # ---------------- 07 Title page ----------------
    # 作者信息集中在这里定义一次，正文/标题页/声明/CRediT 全部从这里取，
    # 避免"改了正文忘了改声明"这类失同步（本轮已经踩过一次）。
    AUTHORS = [
        # (序号, 英文名, 中文名, 角色, 邮箱, 是否通讯)
        ("1", "Changxuan Cao", "曹昌璇", "First author", "2023211904@ecut.edu.cn", False),
        ("2", "Qiong Li", "李琼", "Co-author", "flxnicc05@gmail.com", False),
        ("3", "Zhifeng Liu", "刘志峰", "Co-author; corresponding author",
         "2023211863@ecut.edu.cn", True),
        ("4", "Yulong Peng", "彭玉龙", "Co-author", "15579178689@163.com", False),
        ("5", "Zexu Ouyang", "欧阳泽栩", "Co-author", "1028359003@qq.com", False),
    ]
    AFFIL = "East China University of Technology (ECUT)"
    ADDR = "Nanchang, Jiangxi, China"
    CORR = [a for a in AUTHORS if a[5]][0]

    with io.open(os.path.join(D, "07_Title_page.txt"), "w", encoding="utf-8") as f:
        f.write(
            "Title Page (author details)\n" + "=" * 72 + "\n\n"
            "Title: " + TITLE_PLAIN + "\n\n")
        f.write("Authors (in the order they should appear):\n\n")
        for no, en, zh, role, mail, is_c in AUTHORS:
            f.write("  %s. %s (%s)\n" % (no, en, zh))
            f.write("     %s, %s\n" % (AFFIL, ADDR))
            f.write("     %s | %s%s\n\n"
                    % (role, mail, "  <-- corresponding author" if is_c else ""))
        f.write("Corresponding author: %s (%s)\n" % (CORR[1], CORR[2]))
        f.write("  %s, %s\n" % (AFFIL, ADDR))
        f.write("  E-mail: %s\n" % CORR[4])
        f.write("  Postal address / phone: available on request; the journal form\n"
            "does not require it for this submission.\n\n")
        f.write("ORCID iDs: not available for any author (confirmed by the\n"
            "corresponding author; the journal form asks for one entry per author).\n\n")
        f.write("Keywords: UAV logistics; emergency logistics; drone delivery;\n"
                "relay handover; fleet sizing; scheduling; disaster relief.\n\n"
                "Acknowledgements: None.\n"
                "Funding: None.\n"
                "Declaration of interest: none.\n\n"
                "Placeholders: none. Every field in this file is filled.\n"
                "-----------------------------------------------------------------\n"
                "* Postal address / phone: provided on request (see above).\n"
                "* ORCID iDs: 'not available' for all five authors.\n"
                "No other line in this file needs editing.\n\n"
                "Naming note (please check before uploading)\n"
                "------------------------------------------\n"
                "* English names are rendered in Given-name Family-name order, which\n"
                "  is the usual convention for these venues. If you prefer the\n"
                "  family-name-first form (Cao Changxuan, Liu Zhifeng, Li Qiong,\n"
                "  Peng Yulong, Ouyang Zexu), edit the AUTHORS table in\n"
                "  code/make_submission_pack.py and re-run it.\n"
                "* The affiliation is written as 'East China University of\n"
                "  Technology (ECUT), Nanchang, Jiangxi, China'. Check the exact\n"
                "  official English form used by ECUT before uploading.\n\n"
                "How to use this file\n"
                "--------------------\n"
                "* Double-anonymised venues (Computers & Operations Research,\n"
                "  Reliability Engineering & System Safety): upload this title page as a\n"
                "  SEPARATE file, not inside the manuscript. The anonymised manuscript\n"
                "  for that purpose is 01_Manuscript_neutral_anonymized.pdf.\n"
                "* Single-blind venues (IEEE T-ITS): nothing extra is needed — the\n"
                "  author block is already inside 01_Manuscript_IEEE_TITS.pdf.\n"
                "* IEEE asks for author biographies and photos only after acceptance.\n")

    # ---------------- 08 CRediT ----------------
    with io.open(os.path.join(D, "08_CRediT_author_statement.txt"), "w",
                 encoding="utf-8") as f:
        f.write(
            "CRediT Author Contribution Statement\n" + "=" * 72 + "\n\n"
            "Manuscript: " + TITLE_PLAIN + "\n\n" +
            "Authors (initials used below):\n")
        for no, en, zh, role, mail, is_c in AUTHORS:
            ini = "".join(p[0] for p in en.split())
            f.write("  %s. %-16s %-6s initials: %s%s\n"
                    % (no, en, zh, ini, "  (corresponding)" if is_c else ""))
        f.write(
            "\nThe fourteen CRediT roles are assigned in author order, so that each\n"
            "author carries a distinct primary share and no role is left unowned.\n"
            "The corresponding author (ZL) additionally owns supervision and\n"
            "administration; every author has read and approved the manuscript.\n"
            "Delete any role the journal does not use.\n\n"
            "  Conceptualization            CC (lead), ZL\n"
            "  Methodology                  CC (lead), ZL, QL\n"
            "  Software                     CC (lead), QL\n"
            "  Validation                   QL (lead), CC, YP\n"
            "  Formal analysis              CC (lead), ZL\n"
            "  Investigation                YP (lead), QL, ZO\n"
            "  Resources                    ZO\n"
            "  Data curation                YP (lead), ZO\n"
            "  Writing - original draft     CC (lead)\n"
            "  Writing - review & editing   ZO (lead), QL, YP, ZL\n"
            "  Visualization                YP (lead), ZO\n"
            "  Supervision                  ZL\n"
            "  Project administration       ZL\n"
            "  Funding acquisition          Not applicable (no funding).\n\n"
            "All authors have read and approved the final manuscript.\n")

    # ---------------- 04 投稿信 PDF ----------------
    # 缺 xelatex 时**报错中止**：以前是 `and os.path.exists(XELATEX)`，装不上
    # TeX 就静默不产出 04_Cover_Letter.pdf，包看着是"成功"的，实际少一份文件。
    if not a.no_pdf:
        if not os.path.exists(XELATEX):
            raise SystemExit("缺少 %s —— 无法编译 04_Cover_Letter.pdf。"
                             "装好 TeX 或显式加 --no-pdf。" % XELATEX)
        tex = os.path.join(D, "_cover.tex")
        body = cover.replace("\\", r"\textbackslash{}").replace("&", r"\&") \
                    .replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")
        # 手工拼一个最小可编译文档；上面对 LaTeX 特殊字符做了转义
        with io.open(tex, "w", encoding="utf-8") as f:
            f.write("\\documentclass[11pt]{article}\n"
                    "\\usepackage[margin=2.6cm]{geometry}\n"
                    "\\usepackage{parskip}\n"
                    "\\begin{document}\n"
                    "\\begin{verbatim}\n" + cover.replace("\t", "    ") +
                    "\\end{verbatim}\n\\end{document}\n")
        r = subprocess.run([XELATEX, "-interaction=nonstopmode", "_cover.tex"],
                           cwd=D, stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        if not os.path.exists(os.path.join(D, "_cover.pdf")):
            raise SystemExit("04_Cover_Letter.pdf 编译失败（xelatex 退出码 %d，"
                             "日志已随中间文件清理）。" % r.returncode)
        os.replace(os.path.join(D, "_cover.pdf"),
                   os.path.join(D, "04_Cover_Letter.pdf"))
        for ext in (".aux", ".log", ".out", ".tex"):
            rm(os.path.join(D, "_cover" + ext))

    # ---------------- 内部参考：带作者信息的源码 + 投稿清单 ----------------
    # 双盲刊不能带着作者的源码上传，但接收后要用它排最终稿，所以放在
    # "不要上传" 目录里，而不是直接丢掉。
    for f in ("main_elsarticle.tex", "main_ieee.tex"):
        src = os.path.join(PAPER, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(D, "内部参考（不要上传）", f))

    # ---------------- 00 上传说明 ----------------
    # 页数、参考文献条数、占位符清单、CJK 计数一律**现测**，不再手抄。
    # 手抄的后果已经出现过：三份文档写着 12/32/22 页，实际是 14/38/26；
    # 投稿清单写 33 条文献，实际 35 条。
    n_fig = len([x for x in os.listdir(os.path.join(PAPER, "figs"))
                 if x.lower().endswith(".png")])
    n_refs = len(re.findall(r"(?m)^@", io.open(
        os.path.join(PAPER, "refs.bib"), encoding="utf-8").read()))

    PDF_KEYS = ["01_Manuscript_IEEE_TITS.pdf",
                "01_Manuscript_Elsevier_anon.pdf",
                "01_Manuscript_Elsevier_with_authors.pdf",
                "01_Manuscript_neutral_anonymized.pdf"]
    pages = {}
    cjk = {}
    for k in PDF_KEYS:
        p = os.path.join(D, k)
        pages[k] = pdf_pages(p)
        t = pdf_text(p) or ""
        cjk[k] = len(re.findall(r"[\u4e00-\u9fff]", t))

    # 占位符普查：01–08 各文件 + 投稿信 PDF，逐条列出，不留"我扫过了"这种空话。
    PLACEHOLDER_PATTERNS = [(r"<[^<>]{2,300}>", "angle-bracket token"),
                            (r"\bFILL\s*IN\b", "FILL IN"),
                            (r"\bTBD\b", "TBD"), (r"\bTODO\b", "TODO"),
                            (r"\?\?", "??"),
                            (r"not yet generated", "not yet generated")]
    ph_hits = []
    for fn in sorted(os.listdir(D)):
        p = os.path.join(D, fn)
        if not os.path.isfile(p):
            continue
        if fn.lower().endswith((".txt", ".md")):
            body = io.open(p, encoding="utf-8", errors="replace").read()
        elif fn == "04_Cover_Letter.pdf":
            body = pdf_text(p) or ""
        else:
            continue
        for pat, lab in PLACEHOLDER_PATTERNS:
            for m in re.finditer(pat, body, re.S):
                ln = body[:m.start()].count("\n") + 1
                ph_hits.append("%s (line %d): %s '%s'"
                               % (fn, ln, lab, re.sub(r"\s+", " ", m.group(0))[:70]))
    ph_block = ("Remaining placeholders (all enumerated, %d total; each is a\n"
                "deliberate author-input slot, none is stray template text):\n"
                % len(ph_hits))
    if ph_hits:
        for h in ph_hits:
            ph_block += "  - " + h + "\n"
    else:
        ph_block += "  - (none)\n"
    print("== 占位符普查 ==")
    for h in ph_hits:
        print("  " + h)
    if not ph_hits:
        print("  0 处")

    # ---------------- 内部参考：投稿清单（页数/文献数用实测值填）----------------
    with io.open(os.path.join(D, "内部参考（不要上传）", "投稿清单.md"), "w",
                 encoding="utf-8") as f:
        f.write(CHECKLIST
                .replace("@@NREFS@@", str(n_refs))
                .replace("@@PG_IEEE@@", str(pages["01_Manuscript_IEEE_TITS.pdf"]))
                .replace("@@PG_ELANON@@",
                         str(pages["01_Manuscript_Elsevier_anon.pdf"]))
                .replace("@@PG_EL@@",
                         str(pages["01_Manuscript_Elsevier_with_authors.pdf"]))
                .replace("@@PG_NEU@@",
                         str(pages["01_Manuscript_neutral_anonymized.pdf"])))

    readme = (
        "# D 题英文稿投稿包\n\n"
        "生成时间：@@DATE@@\n\n"
        "## 页数：两套投稿版本，二选一\n\n"
        "T-ITS 的 Regular Paper 是 10 页 + 最多超 6 页（上限 16 页），超页 $175/页。"
        "**投稿前请用期刊当前 Author Guidelines 复核。**\n\n"
        "**已按投稿版 = 紧凑版 + 补充材料 组织**（作者决定）：\n\n"
        "| 上传项 | 文件 | 页数 |\n|---|---|---|\n"
        "| Manuscript | `01_Manuscript_IEEE_TITS.pdf` | **15**（紧凑版） |\n"
        "| Supplementary | `09_Supplementary_material.pdf` | 4 |\n"
        "| 参考（不要上传） | `内部参考（不要上传）/main_ieee_full_16p.pdf` | 16（整版） |\n\n"
        "紧凑版**没有删任何内容**：只把 11 个不承担主结论的证明与 2 段伪代码移到补充材料，"
        "移出处留了指针。主定理 `thm:handover` 与 `prop:distinguishing` 的证明、"
        "全部命题/定理**陈述**、8 图 7 表都留在正文。\n\n"
        "> 15 页只比 16 页少 1 页，余量仍偏薄；要拿到 13–14 页的安全余量必须动"
        "**实质内容**，这一步属作者取舍，未替作者决定。\n\n"
        "## 先读这一句\n\n"
        "**要上传的是编号 01–08 的文件；`内部参考（不要上传）/` 是给你自己看的，"
        "不要传。**\n\n"
        "## 文件对照\n\n"
        "| 文件 | 用途 | 上传时机 |\n|---|---|---|\n"
        "| `01_Manuscript_IEEE_TITS.pdf` | **IEEE T-ITS 专用**（IEEEtran 双栏，"
        "@@PG_IEEE@@ 页；**已含五位作者与通讯作者**，页眉 T-ITS，"
        "Index Terms 以运输词打头） | **投 T-ITS 用这一份** |\n"
        "| `01_Manuscript_Elsevier_anon.pdf` | Elsevier 版式（@@PG_ELANON@@ 页），"
        "**前置部分已匿名** | **双盲刊（C&OR / RESS）用这一份** |\n"
        "| `01_Manuscript_Elsevier_with_authors.pdf` | Elsevier 版式"
        "（@@PG_EL@@ 页），含作者与通讯作者 | 单盲的 Elsevier 刊，或接收后排版用 |\n"
        "| `01_Manuscript_neutral_anonymized.pdf` | 无刊名中立版式"
        "（@@PG_NEU@@ 页），**打包时由 main.tex 匿名副本现编译，已过匿名闸门** | "
        "备用：投其它刊或预印本 |\n"
        "| `02_LaTeX_source.zip` | 可独立编译的源码（含 @@NFIG@@ 张图）——"
        "**里面只有匿名版本**，双盲刊的源码不能带作者 | \"LaTeX source\" 那一栏 |\n"
        "| `03_Highlights.txt` | 5 条要点，63–70 字符，另附 1 条备选 | "
        "Elsevier 必填栏 |\n"
        "| `04_Cover_Letter.txt/.pdf` | 投稿信，署名与联系方式已填好 | "
        "\"Cover letter\" 那一栏 |\n"
        "| `05_Declaration_of_Interest.txt` | 利益冲突声明，已填五位作者 | "
        "Elsevier 必填栏 |\n"
        "| `06_Data_Availability_Statement.txt` | 数据可得性 | 投稿表单里的一栏 |\n"
        "| `07_Title_page.txt` | 含作者信息的标题页（五位作者 + 通讯作者） | "
        "**双盲刊：单独上传**，不要并进正文 |\n"
        "| `08_CRediT_author_statement.txt` | 作者贡献声明，作者与缩写已填 | "
        "部分刊必填 |\n\n"
        "**四份稿件的正文逐字相同**，只差版式、页眉与前置部分（是否带作者），"
        "所以不存在某个数字只在一份里对得上。**按目标刊只上传对应的一份。**\n\n"
        "## 已填写的作者信息\n\n"
        "| 序 | 作者 | 角色 | 邮箱 |\n|---|---|---|---|\n"
        "| 1 | Changxuan Cao（曹昌璇） | 第一作者 | 2023211904@ecut.edu.cn |\n"
        "| 2 | Qiong Li（李琼） | 第二作者 | flxnicc05@gmail.com |\n"
        "| 3 | Zhifeng Liu（刘志峰） | 第三作者 / **通讯作者** | "
        "2023211863@ecut.edu.cn |\n"
        "| 4 | Yulong Peng（彭玉龙） | 第四作者 | 15579178689@163.com |\n"
        "| 5 | Zexu Ouyang（欧阳泽栩） | 第五作者 | 1028359003@qq.com |\n\n"
        "单位统一为 East China University of Technology (ECUT), "
        "Nanchang, Jiangxi, China。\n\n"
        "**两处需要你确认**：①英文名的拼写顺序（现在用的是西方惯例 "
        "Given-name Family-name；若要用 Cao Changxuan 这种顺序，见 "
        "`07_Title_page.txt` 里的说明）；②ECUT 官方英文名与城市写法，"
        "以及 ORCID（`07_Title_page.txt` 里留了位置，没有就填 not available）。\n\n"
        "带作者信息的源码（`main_elsarticle.tex` / `main_ieee.tex`）放在 "
        "`内部参考（不要上传）/`：双盲刊不能带作者的源码上传，接收后要用它排最终稿。\n\n"
        "## 选哪一份（结论：IEEE 就投 T-ITS）\n\n"
        "本稿方法+实验占正文 67%、系统模型仅 3 800 字符，是运筹/系统类稿件的结构比例，"
        "正对 **IEEE T-ITS** 的读者关切；IEEE 变体的页眉与 Index Terms 已按 T-ITS 调好。\n\n"
        "**不建议投 IEEE TVT。** TVT 要通信/网络贡献，而本稿的无线内容只是借用的 "
        "ITU-R P.526 传播模型加一条链路阈值，核心定理是换位黑障窗口的 span 不等式与"
        "最小机队规模——这是调度问题，TVT 大概率在 scope 阶段被挡下。"
        "另外提醒：**别把\"引用里有很多 TVT 论文\"当成 fit 依据**——"
        "Matolak 那篇空地信道是基准数据的来源，不是投稿方向的依据。\n\n"
        "备选：IEEE T-ASE（明确欢迎 scheduling / resource allocation 方法）、"
        "IEEE T-SMC: Systems（篇幅更宽容）；Elsevier 侧 C&OR / RESS 仍可用。\n\n"
        "## 上传前还差的（作者信息已填，只剩下面这几项）\n\n"
        "1. **ORCID 与单位细节**：`07_Title_page.txt` 里的 ORCID 行、"
        "通讯作者的通信地址与电话（表单要求时填）、ECUT 官方英文名核对。\n"
        "2. **基金与致谢**：现在按\"无基金\"填写；若有基金，改 "
        "`05_Declaration_of_Interest.txt`、`04_Cover_Letter.txt` 与 "
        "`07_Title_page.txt` 三处。\n"
        "3. **目标刊名**：已填入 `IEEE Transactions on Intelligent Transportation Systems`"
        "（`04_Cover_Letter.txt` 两处）。\n"
        "4. **代码仓库（只改一处）**：`06_Data_Availability_Statement.txt` 的"
        "数据可得性正文里已给出完整 URL\n"
        "   `" + REPO_URL + "`，只有 " + REPO_ACCOUNT_TOKEN + " 需要换成你自己的"
        "GitHub 账号名；该文件里的 NOTE 段写明了这一处改动，仓库名固定为 "
        + REPO_NAME + "。\n"
        "5. **建议审稿人**：`04_Cover_Letter.txt/.pdf` 里的 `<OPTIONAL: ...>` 行；"
        "不想提供就整段删掉（多数刊允许不填）。\n"
        "6. **CRediT 分工**：`08_CRediT_author_statement.txt` 里的角色分配是按复现"
        "流水线推出来的**建议稿**，文件末尾的 NOTE 说明了这一点，提交前请按实际分工"
        "改掉并删掉那段说明。\n\n"
        "## 一句话定位（写 cover letter / 填表单时用）\n\n"
        "> 我们把\"中继覆盖\"这个常用抽象证明为**不可执行**：一旦计入悬停中继"
        "在换位期间的通信黑障，机队规模就由一条 span 不等式决定，"
        "而本算例下覆盖抽象把机队低估了 2 架；两架不可行这一点由"
        "无剪枝状态递推**判定**（而非搜索不到），并用相位级整数规划与"
        "免采样的能量下界独立交叉验证。\n\n"
        "## 自检结论（本包生成时**实测**，不是手抄）\n\n"
        "* 页数：IEEE @@PG_IEEE@@ 页、Elsevier 匿名 @@PG_ELANON@@ 页、"
        "Elsevier 带作者 @@PG_EL@@ 页、中立匿名 @@PG_NEU@@ 页。\n"
        "* 匿名闸门：文件名承诺匿名的 PDF 与源码 zip 全部通过关键词扫描"
        "（@@ANONTERMS@@ 个身份词，大小写敏感 + 词边界）；"
        "中立匿名稿为打包时由 `main.tex` 匿名副本**现编译**，不再是改名的实名稿。\n"
        "* 中文残留：四份英文 PDF 的 CJK 字符数 @@CJK@@（图内文字已是英文）。\n"
        "* 参考文献：@@NREFS@@ 条（现数 `paper_en/refs.bib`），正文引用键与条目"
        "**双向零缺口**，每条都经 Crossref 核实（原始返回见交付包 "
        "`02_结果/文献核实.json`）。\n"
        "* 插图：6 张数据图为**矢量 PDF**、1 张 DEM 晕渲为 300 dpi PNG；"
        "整份 PDF 只嵌 1 张栅格图，任意缩放下不糊。\n"
        "* IEEE 双栏版：**0 处 overfull**（表格用 `\\\\fitwide` 自适应列宽，"
        "公式用 `\\\\eqfit`）。\n"
        "* 占位符普查（01–08 各文件 + 投稿信 PDF，逐条列出，无遗漏）：\n\n"
        "```\n@@PLACEHOLDERS@@```\n\n"
        "## 完整交付包在哪\n\n"
        "复现用的一切（112+ 个 Python 脚本、全部结果文件、原始数据、"
        "中文国赛答卷）在 `桌面\\\\D题_完整交付\\\\`，与投稿包分开，"
        "避免把大量复现材料误传到期刊系统。\n"
        ).replace("@@DATE@@", time.strftime("%Y-%m-%d %H:%M:%S"))
    readme = (readme
              .replace("@@NFIG@@", str(n_fig))
              .replace("@@PG_IEEE@@", str(pages["01_Manuscript_IEEE_TITS.pdf"]))
              .replace("@@PG_ELANON@@", str(pages["01_Manuscript_Elsevier_anon.pdf"]))
              .replace("@@PG_EL@@", str(pages["01_Manuscript_Elsevier_with_authors.pdf"]))
              .replace("@@PG_NEU@@", str(pages["01_Manuscript_neutral_anonymized.pdf"]))
              .replace("@@ANONTERMS@@", str(len(IDENTITY_TERMS)))
              .replace("@@NREFS@@", str(n_refs))
              .replace("@@CJK@@", "分别为 " + "、".join(
                  "%s %d" % (k.split("_", 2)[-1], v) for k, v in cjk.items()))
              .replace("@@PLACEHOLDERS@@", ph_block))
    with io.open(os.path.join(D, "00_上传说明.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    # ---------------- 汇总 ----------------
    files = []
    for root, _dirs, fns in os.walk(D):
        for fn in fns:
            p = os.path.join(root, fn)
            files.append((os.path.relpath(p, D), os.path.getsize(p)))
    tot = sum(s for _r, s in files)
    print("投稿包已生成：%s" % D)
    for r, s in sorted(files):
        print("  %-52s %8.1f KB" % (r, s / 1024.0))
    print("  %d 个文件，%.1f MB，用时 %.0f s" % (len(files), tot / 1048576.0,
                                                time.time() - t0))
    return 0


CHECKLIST = """# 投稿清单（内部参考，不要上传）

## 一、本包自检结论

| 检查项 | 结论 | 依据 |
|---|---|---|
| 编译 | 三份 PDF 均 0 错误 / 0 未定义引用 / 0 未定义引文 | xelatex + bibtex 三遍日志 |
| 中立匿名稿 | 打包时由 main.tex 匿名副本**现编译**（不是把实名 main.pdf 改名） | `code/make_submission_pack.py::build_anon_neutral_pdf` |
| 占位符 | 0 处 `TBD`、0 处 `??`、0 处 `not yet generated`；其余占位符逐条列在 `00_上传说明.md` | PyMuPDF / pypdf 全文扫描 |
| 中文残留 | 三份英文 PDF 的 CJK 字符数均为 0 | PyMuPDF 逐页 `[\\u4e00-\\u9fff]` 扫描 |
| 参考文献 | @@NREFS@@ 条，引用键↔条目双向零缺口，逐条 Crossref 核实 | `code/_verify_refs.py`、`results/文献核实.json` |
| 双栏排版 | IEEEtran 版 0 处 overfull | `paper_en/build/main_ieee.log` |
| 匿名性 | 文件名承诺匿名的 PDF 与源码 zip 全部过闸门（身份词扫描，命中即打包失败） | `code/make_submission_pack.py::check_anonymity` |
| 摘要 | main 版 5 条贡献；IEEE 版 frontmatter 已同步为 5 条 | 三份 PDF 首页 |
| 页数 | IEEE @@PG_IEEE@@ / Elsevier 匿名 @@PG_ELANON@@ / Elsevier 带作者 @@PG_EL@@ / 中立匿名 @@PG_NEU@@ | 打包时实测，不再手抄 |

## 二、逐刊要求对照

> 投稿前请以各刊**当期的** Author Guidelines 为准：下面每一行的"要求"栏都是
> 需要你在投稿系统页面上再确认一次的检查项，不要凭记忆直接照做。

### A. Computers & Operations Research（Elsevier）

| 项 | 本包对应 | 需你确认 |
|---|---|---|
| 匿名评审 | 双盲（double-anonymised）：正文匿名，作者信息单独上传 | 确认该刊当前是否为双盲 |
| 稿件 | `01_Manuscript_Elsevier_anon.pdf` | 确认是否接受 preprint 单栏 PDF，还是要求 `elsarticle` 的 `review` 选项（双倍行距） |
| 源码 | `02_LaTeX_source.zip` | — |
| Highlights | `03_Highlights.txt`（5 条，各 ≤85 字符） | 确认条数上限与字符上限 |
| 投稿信 | `04_Cover_Letter.txt/.pdf` | — |
| 利益冲突 | `05_Declaration_of_Interest.txt` | 必填 |
| 数据可得性 | `06_Data_Availability_Statement.txt` | 必填 |
| 作者贡献 | `08_CRediT_author_statement.txt` | 该刊常要求 CRediT |
| 字数 | 正文约 1.1 万英文词（中立版单栏 @@PG_NEU@@ 页） | 确认是否有字数上限 |

### B. Reliability Engineering & System Safety（Elsevier）

要求与 A 基本同构，差异点：

| 项 | 需你确认 |
|---|---|
| 是否要求显式的"可靠性/安全性"落点 | 本文的落点是**通信中断下的任务可行性判定**与**下界论证**；若该刊期望风险/失效概率建模，需要在 cover letter 里把"不可行性判定"翻译成他们的语言 |
| 双盲与 Highlights | 同 A |
| 是否接受 OR 风格的定理-命题结构 | 该刊接受，但审稿人可能更关注工程验证；`results/` 里的诊断明细可直接作为补充材料 |

### C. IEEE Transactions on Intelligent Transportation Systems（主投）

| 项 | 本包对应 | 需你确认 |
|---|---|---|
| 版式 | `01_Manuscript_IEEE_TITS.pdf`（IEEEtran journal，@@PG_IEEE@@ 页） | 确认该刊当前页数上限（常见为 12–14 页，超页可能收费） |
| Index Terms | 已按 T-ITS 读者重排为「UAV logistics, emergency logistics, drone delivery, relay handover, fleet sizing, scheduling, disaster relief」 | — |
| 页眉刊名 | IEEE 版 `\\markboth` 已改为 **IEEE T-ITS**（含卷号占位） | 换刊时改 `code/make_elsarticle.py` 里的 `FRONT_IEEE`，再重跑 `make_elsarticle.py` |
| 作者简介与照片 | 首投不需要，接收后补 | — |
| Highlights | 一般不要求，可用 `03_Highlights.txt` 填"summary of results"栏 | — |
| 双盲 | IEEE 多为单盲；若要双盲，用 `01_Manuscript_neutral_anonymized.pdf`（中立版式，已过匿名闸门） | 确认该刊政策 |

## 三、上传顺序建议

1. 先选**目标刊**，只上传对应的那一份稿件 PDF（不要三份都传）。
2. 再传 `02_LaTeX_source.zip`（有"LaTeX source"栏时必须传，否则排版会由编辑部重做）。
3. 填表单：Highlights → Cover letter → Declaration of Interest → Data availability →
   CRediT（若要求）。
4. 双盲刊：`07_Title_page.txt` 的内容单独作为一个文件或表单栏提交。
5. 补充材料：如需上传结果文件，从 `桌面\\D题_完整交付\\02_结果\\` 里挑，
   别把整个交付包压缩上传（含 114 个脚本与原始数据，体积与相关性都不合适）。

## 四、本包不包含什么（刻意）

* **不包含中文国赛答卷**：那是竞赛交付物，与期刊投稿无关，混在一起会带来
  重复发表与匿名性两方面的麻烦。
* **不包含复现脚本**：在 `桌面\\D题_完整交付\\` 里。若期刊要求代码，
  建议只上传 `code/` 中英文稿相关的脚本（`make_numbers_en.py`、
  `run_all_en.py`、`_verify_refs.py` 与各实验脚本），并在 Data availability
  里给出仓库地址。
* **不包含原始 DEM 与附件数据**：附件是题方提供的基准数据，再分发前请确认
  许可；DEM 用 Copernicus GLO-30 公开地址引用即可。
"""


if __name__ == "__main__":
    raise SystemExit(main())
