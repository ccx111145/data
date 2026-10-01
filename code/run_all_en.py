# -*- coding: utf-8 -*-
"""
run_all_en.py —— 英文 SCI 稿的一键复现：增补实验 → 数字宏 → 编译 PDF。

阶段（可用 `--only` 单跑）：
    ch    防线 3：信道模型对比（观察口径 / P.526 单刃峰 / 多刃峰上界）
    cf    防线 2：协同再调度反馈回路
    mode  防线 1：换位模式对比 + 跨度—黑障不等式
    base  实验②（中继侧）：覆盖基线与严格下界
    terr  实验①：多地形基准
    abl   基线与消融汇总（含分区代价）
    rep   中文《SCI 增补实验报告》
    num   英文稿数字宏（numbers_en.tex）
    pdf   编译英文稿（xelatex → bibtex → xelatex ×2）

用法：
    python run_all_en.py                 # 全部
    python run_all_en.py --only pdf       # 只编译
    python run_all_en.py --fast           # 缩小搜索预算，快速验证链路

依赖：与主流程相同（numpy/pandas/scipy/openpyxl/matplotlib/ortools）+ TeXLive。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dcore import find_bin as ask_bin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
# TeX 二进制不再硬编码：按 环境变量 -> PATH -> 本机常见位置 解析，
# 别人 clone 本仓库后只要有 TeXLive 在 PATH 里就能编译。
XELATEX = ask_bin("xelatex")
BIBTEX = ask_bin("bibtex")

STAGES = ["ch", "cf", "mode", "base", "ilp", "cw", "terr", "abl", "obs", "rep", "fig", "num", "pdf", "jrnl"]


def run(name, args, cwd=HERE, timeout=7200, quiet=False):
    t0 = time.time()
    print("\n" + "=" * 78)
    print("[%s] %s" % (name, " ".join(args)))
    print("=" * 78, flush=True)
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([PY] + args if args[0].endswith(".py") else args,
                       cwd=cwd, env=env, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", errors="replace")
    if not quiet:
        tail = "\n".join(out.strip().splitlines()[-12:])
        print(tail)
    print("[%s] 退出码 %d，用时 %.0f s" % (name, r.returncode, time.time() - t0), flush=True)
    return r.returncode


def _run_with_env(script, extra_env, timeout=7200):
    """跑一个脚本并附加环境变量（用于给图生成器传 DTS_FIGW / DTS_FIGDIR）。"""
    t0 = time.time()
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra_env)
    r = subprocess.run([PY, script], cwd=HERE, env=env, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    ok = sum(1 for l in out.splitlines() if "[OK]" in l)
    print("[figs] %-24s W=%-4s -> %-10s 生成 %d 张，退出码 %d"
          % (script, extra_env.get("DTS_FIGW", "-"),
             os.path.basename(extra_env.get("DTS_FIGDIR", "")), ok, r.returncode),
          flush=True)
    if r.returncode:
        for l in out.splitlines()[-6:]:
            print("      " + l.strip()[:110])
    return r.returncode


def compile_en():
    tex = os.path.join(ROOT, "paper_en", "main.tex")
    if not os.path.exists(tex):
        print("[pdf] 未找到 %s" % tex)
        return 1
    if not os.path.exists(XELATEX):
        print("[pdf] 未找到 xelatex，跳过编译（源文件已就绪）")
        return 0
    # 三遍 xelatex + 一遍 bibtex。这里不再用 DEVNULL 吞掉输出——早先那样做，
    # 编译失败时只留一个莫名的退出码 1，看不出错在哪。现在捕获输出、
    # 检查 "!" 错误行、并核对 main.pdf 是否真的产出。
    errs = []
    for k in range(3):
        args = [XELATEX, "-interaction=nonstopmode",
                "-output-directory=paper_en", "paper_en/main.tex"]
        r = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        bad = [l for l in out.splitlines() if l.startswith("!")]
        if bad:
            errs = bad
        if k == 0 and os.path.exists(BIBTEX):
            rb = subprocess.run([BIBTEX, "main"], cwd=os.path.join(ROOT, "paper_en"),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            bout = (rb.stdout or b"").decode("utf-8", errors="replace")
            if "error" in bout.lower() or "I couldn't" in bout:
                errs = errs or ["bibtex: " + bout.strip().splitlines()[0][:100]]
    log = os.path.join(ROOT, "paper_en", "main.log")
    if os.path.exists(log):
        try:
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                ltxt = f.read()
            import re as _re
            unresolved = _re.findall(r"Warning: (?:Reference|Citation) `([^']+)' .*undefined",
                                     ltxt)
            if unresolved:
                errs = errs or ["undefined refs/cites: %s" % ", ".join(sorted(set(unresolved))[:5])]
        except OSError:
            pass
    pdf = os.path.join(ROOT, "paper_en", "main.pdf")
    ok = os.path.exists(pdf)
    print("[pdf] %s %s" % ("已生成" if ok else "未生成", pdf))
    if errs:
        print("[pdf] 编译报错：")
        for e in errs[:5]:
            print("      " + e.strip()[:110])
        return 1
    if not ok:
        print("[pdf] 编译未报错但未产出 PDF，请检查 main.log")
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, choices=STAGES)
    ap.add_argument("--fast", action="store_true",
                    help="缩小搜索预算（快速验证链路，数值会略差）")
    ap.add_argument("--skip-terr", action="store_true",
                    help="跳过最耗时的多地形基准（约 15 分钟）")
    a = ap.parse_args()

    iters, restarts, K = (200, 2, 70) if a.fast else (600, 4, 200)
    stages = [a.only] if a.only else [s for s in STAGES
                                      if not (a.skip_terr and s == "terr")]
    rc = 0
    for st in stages:
        if st == "ch":
            rc |= run("channel", ["channel_compare.py", "--models", "observed,p526,p526ub",
                                  "--topks", "200,400,600"], timeout=5400)
        elif st == "cf":
            rc |= run("cofeedback", ["cofeedback.py", "--iters", str(iters),
                                     "--restarts", str(restarts), "--K", str(K)], timeout=3600)
        elif st == "mode":
            rc |= run("mode", ["mode_compare.py"], timeout=3600)
            rc |= run("span", ["span_blackout.py"], timeout=3600)
        elif st == "base":
            rc |= run("baselines", ["relay_baselines.py", "--model", "observed",
                                    "--topk", "400"], timeout=3600)
        elif st == "ilp":
            # 相位级整数规划区间松弛（CP-SAT，方法学交叉验证；秒级）
            rc |= run("relay-ilp", ["relay_ilp.py", "--Ns", "1,2,3,4",
                                    "--tl", "90", "--per-phase", "40"], timeout=3600)
        elif st == "cw":
            # 运输侧教科书级外部基线：Clarke–Wright 节约算法（含同预算 ALNS 对照）
            rc |= run("cw-savings", ["cw_savings.py", "--alns-iters", "600",
                                     "--alns-restarts", "4", "--alns-tlimit", "120"],
                      timeout=5400)
        elif st == "terr":
            rc |= run("terrain", ["terrain_benchmark.py",
                                  "--alphas", "0.2,0.35,0.6,1.0,1.4",
                                  "--shifts", "40,40;120,40;90,-70",
                                  "--cuts", "1.0"], timeout=7200)
            rc |= run("terrain-md", ["terrain_md.py"], timeout=600)
        elif st == "abl":
            rc |= run("ablation", ["ablation.py"], timeout=600)
        elif st == "obs":
            # 理论量：span / alibi 放行率 / 能量下界 + 理论图（不含耗时极大的无剪枝判定）
            rc |= run("obstruction", ["obstruction.py", "--no-exact"], timeout=5400)
            rc |= run("fig-theory", ["make_fig_theory.py"], timeout=900)
        elif st == "rep":
            rc |= run("report", ["make_sci_report.py"], timeout=600)
        elif st == "fig":
            # 三套生成器 + 两种版式宽度，缺一不可：
            #   make_figs_en.py       环境/信道/基线/模式/反馈/地形（6 张）
            #   make_figs_extra_en.py 相位结构/三法判定/理论面板（3 张）
            #   make_figs_cn_en.py    运输侧三图（Pareto/甘特/通信保障）
            # 宽度必须≈目标版式显示宽度，否则图内字号被缩放：
            #   elsarticle 单栏 ≈5.3 in -> 5.4      IEEEtran 跨栏 ≈7.07 -> 7.2
            # 早先这里只跑 make_figs_en.py，导致另外两套图、以及 theory 图
            # 在根 figs/ 下缺失，xelatex 报 "Unable to load picture"。
            for gen in ("make_figs_en.py", "make_figs_extra_en.py",
                        "make_figs_cn_en.py"):
                for w, outdir in (("5.4", "figs_els"), ("7.2", "figs_ieee")):
                    env = {"DTS_FIGW": w,
                           "DTS_FIGDIR": os.path.join(ROOT, outdir)}
                    rc |= _run_with_env(gen, env, timeout=1800)
            # xelatex 以仓库根为 cwd，\includegraphics{figs/x} 解析到根 figs/；
            # 因此把 Elsevier 宽度那套同步到根 figs/。
            import shutil as _sh
            src = os.path.join(ROOT, "figs_els")
            if os.path.isdir(src):
                for f in os.listdir(src):
                    for dst in (os.path.join(ROOT, "figs"),
                                os.path.join(ROOT, "paper_en", "figs"),
                                os.path.join(ROOT, "paper_en", "build", "figs")):
                        os.makedirs(dst, exist_ok=True)
                        try:
                            _sh.copy2(os.path.join(src, f), os.path.join(dst, f))
                        except OSError:
                            pass
                print("[figs] 已把 figs_els/ 同步到根 figs/ 与 paper_en/figs/")
        elif st == "num":
            rc |= run("numbers-en", ["make_numbers_en.py"], timeout=600)
        elif st == "pdf":
            rc |= compile_en()
        elif st == "jrnl":
            rc |= run("journal", ["make_elsarticle.py"], timeout=1800)
    print("\n全部阶段完成，累计退出码 %d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
