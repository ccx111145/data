# -*- coding: utf-8 -*-
"""check_consistency.py —— 稿件一致性体检（投稿前必跑）

为什么需要这个脚本：本稿已经**三次**出现同一类缺陷——同一份内容被抄成了两处，
改了一处漏了另一处：

  1. `make_elsarticle.py` 的 `FRONT_IEEE` 里手抄了一整段摘要，正文改了措辞而
     IEEE 版停留在旧版（摘要写着 "decided rather than searched"，正文已改成
     搜索范围口径）——同一篇稿件两个说法；
  2. 标题/定理样式块原先放在「期刊变体拼接区间」之外，期刊变体根本没拿到，
     首次修复等于没生效；
  3. `PREAMBLE_EL` / `PREAMBLE_IEEE` 里各留了一份 `\\eqfit` / `\\newtheorem`，
     与共享段重复定义（`already defined`）。

这类缺陷靠人眼复检是不可靠的：它不报错、不警告，只让两个版本悄悄分叉。
本脚本把这三条变成**可执行断言**，构建即失败。

用法：python code/check_consistency.py
退出码 0 = 全部通过；非 0 = 有不一致，禁止投稿。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PE = os.path.join(BASE, "paper_en")

FAIL = []
OK = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (OK if cond else FAIL).append((name, detail))
    print("  [%s] %s%s" % ("OK " if cond else "!! ", name,
                           ("  —— " + detail) if (detail and not cond) else ""))


def read(p: str) -> str:
    return io.open(p, encoding="utf-8").read()


def main() -> int:
    main_tex = os.path.join(PE, "main.tex")
    derived = [os.path.join(PE, n + ".tex")
               for n in ("main_elsarticle", "main_elsarticle_anon", "main_ieee")]
    missing = [d for d in derived if not os.path.exists(d)]
    if missing:
        print("缺少派生文件，先跑 make_elsarticle.py：%s" % missing)
        return 2

    src = read(main_tex)

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def tex_abstract(t: str):
        """取 \\begin{abstract}..\\end{abstract} 的**内层文本**。"""
        if "\\begin{abstract}" not in t:
            return None
        i = t.index("\\begin{abstract}") + len("\\begin{abstract}")
        j = t.index("\\end{abstract}", i)
        return t[i:j]

    def tex_keywords(t: str):
        for pat in (r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}",
                    r"\\begin\{keyword\}(.*?)\\end\{keyword\}"):
            m = re.search(pat, t, re.S)
            if m:
                return m.group(1)
        return None

    print("=== 1. 摘要与关键词：三个变体必须与 main.tex 同源 ===")
    src_abs = norm(tex_abstract(src) or "")
    check("main.tex 摘要非空", len(src_abs) > 200, "解析不到摘要正文")
    for d in derived:
        t = read(d)
        got = norm(tex_abstract(t) or "")
        # IEEEtran 的 abstract 环境自带缩进，抽取时会去掉一个 \noindent
        same = (got == src_abs) or (got == norm(src_abs.replace("\\noindent", "", 1)))
        check("%-26s 摘要与 main.tex 逐字一致" % os.path.basename(d), same,
              "长度 %d vs %d，疑似手抄后失同步" % (len(got), len(src_abs)))
        kd = tex_keywords(t)
        check("%-26s 含关键词块" % os.path.basename(d), kd is not None)
        if kd is not None:
            kws = [w.strip() for w in re.split(r"\\sep|;", kd) if w.strip()]
            check("%-26s 关键词 ≥4 个" % os.path.basename(d), len(kws) >= 4,
                  "只解析到 %d 个：%s" % (len(kws), kws))

    print("=== 2. 样式统块必须在所有变体内（拼接区间要正确）===")
    for key in ("\\newtheoremstyle{dshplain}", "\\newcommand{\\eqfit}",
                "ifclassloaded", "标题统一"):
        for d in derived:
            t = read(d)
            check("%-32s 在 %s" % (key, os.path.basename(d)), key in t,
                  "样式块落在期刊变体的拼接区间之外")

    print("=== 3. 不得重复定义（preamble 与共享段各留一份）===")
    # 注意判据：preamble 与共享段**各有一份**才是缺陷（会 already defined）。
    # 两个 preamble 各有一份是**合法的**——PREAMBLE_EL 与 PREAMBLE_IEEE 是
    # 互斥分支，同一个变体只会拼进其中一个。因此必须查派生文件，而不是查
    # 脚本里出现几次（后者会误报 \fitwide 这类共同需要的宏）。
    src_script = read(os.path.join(BASE, "code", "make_elsarticle.py"))
    for key in ("\\newcommand{\\eqfit}", "\\newtheorem{theorem}"):
        for d in derived:
            t = read(d)
            check("%s 内 %s 只出现 1 次" % (os.path.basename(d), key),
                  t.count(key) == 1, "preamble 与共享段各有副本（实际 %d 次）"
                  % t.count(key))
    # 每个变体都必须有 \fitwide 的定义，且恰好一处
    for d in derived + [main_tex]:
        t = read(d)
        check("%-26s 内 \\fitwide 恰好定义 1 次" % os.path.basename(d),
              t.count("\\newcommand{\\fitwide}") == 1,
              "定义 %d 次" % t.count("\\newcommand{\\fitwide}"))

    print("=== 4. 正文不得含非 ASCII（IEEE 变体走 pdflatex）===")
    for ln, line in enumerate(src.split("\n"), 1):
        code = line.split("%")[0]
        bad = [ch for ch in code if ord(ch) > 127]
        if bad:
            check("main.tex 第 %d 行无非 ASCII" % ln, False,
                  "含 %r（pdflatex 会报 Unicode character 错误）" % bad[0])
            break
    else:
        check("main.tex 正文无非 ASCII 字符", True)

    print("=== 5. 过强表述不得回流 ===")
    BANNED = ["decided rather than searched", "not merely searched",
              "decided exactly", "not merely unsearched",
              "Minimum fleet", "minimum fleet", "four times",
              "proven impossible"]
    # "proven impossible" 允许出现在否定语境里，单独放行
    ALLOW = {"proven impossible"}
    for d in derived + [main_tex]:
        t = read(d)
        hits = []
        for b in BANNED:
            if b not in t:
                continue
            if b in ALLOW:
                # 只允许出现在 "never ... proven impossible" 这类否定句里
                for m in re.finditer(re.escape(b), t):
                    ctx = t[max(0, m.start() - 90):m.start()].lower()
                    if "never" not in ctx and "not " not in ctx:
                        hits.append(b)
                        break
            else:
                hits.append(b)
        check("%-26s 无过强表述回流" % os.path.basename(d), not hits, str(hits))

    # 5b. 投稿包的外围文本文件也必须过同一套禁用词。
    #     为什么要加这一段：正文改过 5 轮，而 03_Highlights.txt 一直写着
    #     "Two-relay infeasibility is decided exactly, not merely unsearched"，
    #     与正文已经撤回的说法正面冲突——外围文件从来没进过闸门，所以没人发现。
    #     投稿包若不在场（例如只跑论文目录）就跳过，不算失败。
    pkg = r"C:\Users\ASUS\Desktop\D题_投稿包"
    if os.path.isdir(pkg):
        for fn in sorted(os.listdir(pkg)):
            if not fn.endswith(".txt"):
                continue
            p = os.path.join(pkg, fn)
            try:
                t = io.open(p, encoding="utf-8").read()
            except Exception:                                       # noqa: BLE001
                continue
            hits = [b for b in BANNED if b in t and b not in ALLOW]
            # 投稿包里也允许 "proven impossible" 出现在否定句里
            if "proven impossible" in t:
                for m in re.finditer(re.escape("proven impossible"), t):
                    ctx = t[max(0, m.start() - 90):m.start()].lower()
                    if "never" not in ctx and "not " not in ctx:
                        hits.append("proven impossible")
                        break
            check("投稿包 %-22s 无过强表述" % fn, not hits, str(hits))
    else:
        check("投稿包不在场，跳过外围文件扫描", True)

    print("=== 6. 宏与引用：正文引用的宏必须已定义，编译日志不得有 undefined ===")
    nums = read(os.path.join(PE, "numbers_en.tex"))
    defined = set(re.findall(r"\\newcommand\{\\(EN[A-Za-z]+)\}", nums))
    used = {u[1:] for u in re.findall(r"\\EN[A-Za-z]+", src)}
    missing = sorted(used - defined)
    check("正文引用的 EN* 宏全部已定义", not missing,
          "未定义：%s（先跑 make_numbers_en.py，或宏名拼错）" % missing)
    # 编译日志：0 错误 / 0 未定义引用
    for name, logname in (("main", "main.log"),
                          ("main_elsarticle", os.path.join("build", "main_elsarticle.log")),
                          ("main_ieee", os.path.join("build", "main_ieee.log"))):
        lp = os.path.join(PE, logname)
        if not os.path.exists(lp):
            check("存在 %s 日志" % name, False, "先编译一次")
            continue
        log = read(lp)
        errs = len(re.findall(r"(?m)^! ", log))
        undef = len(re.findall(r"LaTeX Warning: (?:Reference|Citation) .* undefined", log))
        check("%-16s 0 错误 / 0 未定义引用" % name, errs == 0 and undef == 0,
              "errors=%d undef=%d（%s）" % (errs, undef, logname))

    print()
    print("通过 %d 项，失败 %d 项" % (len(OK), len(FAIL)))
    if FAIL:
        print("\n失败明细：")
        for n, d in FAIL:
            print("  - %s：%s" % (n, d))
        print("\n结论：禁止投稿，先修掉上面的不一致。")
        return 1
    print("结论：一致性体检通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
