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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
XELATEX = r"H:\texlive\2024\bin\windows\xelatex.exe"
BIBTEX = r"H:\texlive\2024\bin\windows\bibtex.exe"

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


def compile_en():
    tex = os.path.join(ROOT, "paper_en", "main.tex")
    if not os.path.exists(tex):
        print("[pdf] 未找到 %s" % tex)
        return 1
    if not os.path.exists(XELATEX):
        print("[pdf] 未找到 xelatex，跳过编译（源文件已就绪）")
        return 0
    rc = 0
    for k in range(3):
        args = [XELATEX, "-interaction=nonstopmode",
                "-output-directory=paper_en", "paper_en/main.tex"]
        r = subprocess.run(args, cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        rc |= r.returncode
        if k == 0 and os.path.exists(BIBTEX):
            subprocess.run([BIBTEX, "main"], cwd=os.path.join(ROOT, "paper_en"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    pdf = os.path.join(ROOT, "paper_en", "main.pdf")
    print("[pdf] %s %s" % ("已生成" if os.path.exists(pdf) else "未生成", pdf))
    return rc


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
            rc |= run("figs-en", ["make_figs_en.py"], timeout=900)
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
