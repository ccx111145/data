# -*- coding: utf-8 -*-
"""
run_all.py —— D 题全流程一键复现

用法（在本脚本所在目录下执行）：
    set PYTHONHASHSEED=0 && python run_all.py                 # 全流程
    set PYTHONHASHSEED=0 && python run_all.py --from q3       # 从指定阶段开始
    set PYTHONHASHSEED=0 && python run_all.py --only q4       # 只跑某一阶段
    set PYTHONHASHSEED=0 && python run_all.py --with-sens     # 追加灵敏度分析
    set PYTHONHASHSEED=0 && python run_all.py --n3            # 问题三重跑 N=3 状态 DP
    python run_all.py --check-env                             # 只做环境与路径自检

阶段：
    q1   问题一：最大安全载荷 + 组批 Pareto + ρ 灵敏度 + CP-SAT 交叉验证
    q2   问题二：ALNS + CP-SAT 打磨 + Pareto 前沿（写入 results/solution.json）
    q3   问题三：运输—通信联合优化 + 中继相位规划
         + `q3refresh.py`（在**修正后的物理模型**下重算 2 架折中与 3 架增配方案，
           并回填 solution.json 的 relay / relay3 与 meta.relay_analysis）
    q4   问题四：2/3 分区与资源核算、库存缺口、中继双口径情景
    exp  结果提交表导出 + 独立仿真校验
    fig  图件 + 论文数字宏 + xelatex 编译
    sens 灵敏度分析（耗时较长，默认不跑，用 --with-sens 打开）

目录布局自适应（审阅 #26）
-------------------------
`dcore.py` 会按顺序探测数据目录，因此本脚本在下面两种布局下都能直接运行：
    工作区：      <root>/code/*.py  +  <root>/数据/  +  <root>/results/
    交付包：      <pkg>/03_程序/*.py + <pkg>/04_数据与模板/数据/  +  <pkg>/results/（自动创建）
也可用环境变量 `DTI_DATA_DIR` 显式指定数据目录。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

# TeX 二进制按 环境变量 -> PATH -> 本机常见位置 解析，不硬编码绝对路径。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dcore import find_bin as ask_bin                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
STAGES = ["q1", "q2", "q3", "q4", "exp", "fig"]


def run(name, args, cwd=HERE, timeout=3600):
    t0 = time.time()
    print("\n" + "=" * 78)
    print("[%s] %s %s" % (name, PY, " ".join(args)))
    print("=" * 78, flush=True)
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([PY] + args, cwd=cwd, env=env, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", errors="replace")
    tail = "\n".join(out.strip().splitlines()[-18:])
    print(tail)
    print("[%s] 退出码 %d，用时 %.0f s" % (name, r.returncode, time.time() - t0), flush=True)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--from", dest="start", default="q1", choices=STAGES)
    ap.add_argument("--only", default=None, choices=STAGES + ["sens"])
    ap.add_argument("--with-sens", action="store_true")
    ap.add_argument("--skip-q2", action="store_true", help="沿用已有 solution.json 的运输方案")
    ap.add_argument("--n3", action="store_true",
                    help="问题三：重跑 N=3 状态 DP（约 30 分钟；默认沿用已有 relay3）")
    ap.add_argument("--no-refresh", action="store_true",
                    help="问题三：跳过 q3refresh.py（沿用 solution.json 现有中继方案）")
    ap.add_argument("--diag", action="store_true",
                    help="问题三：重跑诊断脚本并合并（约 10 分钟，供稳健性数字刷新）")
    ap.add_argument("--check-env", action="store_true",
                    help="只做环境/路径自检后退出（不求解）")
    a = ap.parse_args()

    if a.check_env:
        return check_env()

    stages = [a.only] if a.only else STAGES[STAGES.index(a.start):]
    if a.only == "sens":
        stages = []
    if a.with_sens:
        stages = stages + ["sens"]

    rc = 0
    for st in stages:
        if st == "q1":
            rc |= run("q1", ["q1.py"])
            rc |= run("q1-verify", ["vq1.py"])
        elif st == "q2":
            rc |= run("q2", ["q2.py"])
        elif st == "q3":
            rc |= run("q3", ["q3.py"])
            rc |= run("q3-fix", ["fixsol.py"])
            # 修正物理模型下重算中继方案（2 架折中 + 3 架增配），并回填 solution.json
            if not a.no_refresh:
                rc |= run("q3-refresh", ["q3refresh.py", "--topk", "400"], timeout=3600)
            # N=2 不可行性判定（状态 DP），--n3 才重跑 3 架的 DP（约 30 分钟）
            args = ["q3final.py"] + (["--n3"] if a.n3 else [])
            rc |= run("q3-final", args, timeout=9000)
            # 诊断类结果文件合并（供 make_numbers.py 读取，避免依赖过期日志）
            # --diag 时才重跑产生诊断文件的脚本（fail_diag/mode_compare/span_blackout/
            # struct_diag/recompute_relay/greedy_relay，合计约 10 分钟）
            rc |= run("q3-diag", ["q3diag.py"] + (["--run"] if a.diag else []),
                      timeout=3600)
        elif st == "q4":
            rc |= run("q4", ["q4.py"])
            rc |= run("q4-relay3", ["q4_relay3.py"])
        elif st == "exp":
            rc |= run("export", ["export_results.py"])
            rc |= run("verify", ["verify_sim.py"])
        elif st == "fig":
            rc |= run("figs", ["make_figs.py"])
            rc |= run("numbers", ["make_numbers.py"])
            xelatex = ask_bin("xelatex")
            if os.path.exists(xelatex):
                for _ in range(2):
                    subprocess.run([xelatex, "-interaction=nonstopmode",
                                    "-output-directory=paper", "paper/paper.tex"],
                                   cwd=ROOT, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                print("[paper] %s" % os.path.join(ROOT, "paper", "paper.pdf"))
            else:
                print("[paper] 未找到 xelatex，跳过编译")
        elif st == "sens":
            rc |= run("sensitivity", ["sensitivity.py"], timeout=7200)
    print("\n全部阶段完成，累计退出码 %d" % rc)
    return rc


def check_env():
    """环境与路径自检：数据目录、输出目录、依赖、结果文件（审阅 #26/#30）。"""
    print("=" * 78)
    print("run_all.py --check-env  环境与路径自检")
    print("=" * 78)
    ok = True

    def line(k, v, good=True):
        nonlocal ok
        print("  %-22s %s" % (k + "：", v))
        ok = ok and good

    line("Python", "%s (%s)" % (sys.version.split()[0], PY))
    try:
        import dcore as D
    except Exception as e:                                        # noqa: BLE001
        line("导入 dcore", "失败：%r" % (e,), False)
        return 2
    line("BASE", D.BASE)
    line("数据目录 DATA", D.DATA, os.path.isdir(D.DATA))
    line("参数目录", D.PARAM_DIR, os.path.isdir(D.PARAM_DIR))
    line("DEM 文件", D.DEM_MAT, os.path.exists(D.DEM_MAT))
    line("输出目录 RESULTS", D.RESULTS, os.path.isdir(D.RESULTS))
    line("输出目录 FIGS", D.FIGS, os.path.isdir(D.FIGS))
    for mod in ("numpy", "pandas", "scipy", "openpyxl", "matplotlib", "ortools"):
        try:
            __import__(mod)
            line("依赖 " + mod, "OK")
        except Exception as e:                                    # noqa: BLE001
            line("依赖 " + mod, "缺失：%r" % (e,), False)
    xelatex = ask_bin("xelatex")
    line("xelatex", xelatex if os.path.exists(xelatex) else "未找到（论文编译阶段会跳过）",
         True)
    for f in ("solution.json", "结果提交.xlsx", "检查说明.md", "Q4_说明.md",
              "Q3_方案汇总.json", "Q3_诊断汇总.json"):
        p = os.path.join(D.RESULTS, f)
        line("结果 " + f, "存在" if os.path.exists(p) else "缺失（需先跑对应阶段）",
             os.path.exists(p))
    paper_tex = os.path.join(D.BASE, "paper", "paper.tex")
    line("论文源码", paper_tex if os.path.exists(paper_tex) else "未找到（fig 阶段会跳过编译）",
         True)
    print("-" * 78)
    print("自检%s。若「数据目录」指向了非预期位置，可设环境变量 DTI_DATA_DIR 显式指定。"
          % ("全部通过" if ok else "发现问题，请按上面提示处理"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
