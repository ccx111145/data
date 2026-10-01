# -*- coding: utf-8 -*-
"""_fix_runall.py —— 修复 run_all.py 的三处交付缺陷（审阅 #26/#27/#30）：

  #27 `--n3` 未在 argparse 中声明，只用 `"--n3" in sys.argv` 偷看，`--help` 里看不到；
  #26 交付包的目录布局是「03_程序/ + 04_数据与模板/数据/ + 02_结果/」，
       与工作区「code/ + 数据/ + results/」不同，脚本必须能自适应；
  #30 需要一条"全新目录可从零跑通"的路径：新增 `--check-env` 自检与
       `--repro` 说明，并在启动时打印解析到的数据/输出目录。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "run_all.py")
s = io.open(P, encoding="utf-8").read()

# ---------------- 1) 顶部文档 ----------------
old_doc = '''用法（在 D题\\code 目录下）：
    set PYTHONHASHSEED=0 && python run_all.py            # 全流程
    set PYTHONHASHSEED=0 && python run_all.py --fast     # 缩短求解预算（快速验证链路）
    set PYTHONHASHSEED=0 && python run_all.py --from q3  # 从指定阶段开始

阶段：
    q1   问题一：最大安全载荷 + 组批 Pareto + ρ 灵敏度 + CP-SAT 交叉验证
    q2   问题二：ALNS + CP-SAT 打磨 + Pareto 前沿（写入 results/solution.json）
    q3   问题三：运输—通信联合优化 + 中继相位规划（回填 solution.json 的 relay）
    q4   问题四：2/3 分区与资源核算、库存缺口
    exp  结果提交表导出 + 独立仿真校验
    fig  图件 + 论文数字宏 + xelatex 编译
    sens 灵敏度分析（耗时较长，默认不跑，用 --with-sens 打开）
'''
new_doc = '''用法（在本脚本所在目录下执行）：
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
'''
assert s.count(old_doc) == 1, ("doc", s.count(old_doc))
s = s.replace(old_doc, new_doc)

# ---------------- 2) argparse 增加 --n3 / --check-env ----------------
old_arg = '''    ap.add_argument("--skip-q2", action="store_true", help="沿用已有 solution.json 的运输方案")
    a = ap.parse_args()'''
new_arg = '''    ap.add_argument("--skip-q2", action="store_true", help="沿用已有 solution.json 的运输方案")
    ap.add_argument("--n3", action="store_true",
                    help="问题三：重跑 N=3 状态 DP（约 30 分钟；默认沿用已有 relay3）")
    ap.add_argument("--no-refresh", action="store_true",
                    help="问题三：跳过 q3refresh.py（沿用 solution.json 现有中继方案）")
    ap.add_argument("--check-env", action="store_true",
                    help="只做环境/路径自检后退出（不求解）")
    a = ap.parse_args()

    if a.check_env:
        return check_env()'''
assert s.count(old_arg) == 1, ("arg", s.count(old_arg))
s = s.replace(old_arg, new_arg)

# ---------------- 3) q3 阶段改用 q3refresh.py ----------------
old_q3 = '''        elif st == "q3":
            rc |= run("q3", ["q3.py"])
            rc |= run("q3-fix", ["fixsol.py"])
            # N=2 不可行性判定 + N=3 最小增配方案（--n3 才重跑 3 架的 DP，约 30 分钟）
            args = ["q3final.py"] + (["--n3"] if "--n3" in sys.argv else [])
            rc |= run("q3-final", args, timeout=9000)
            rc |= run("q3-resplit", ["q3resplit.py"])'''
new_q3 = '''        elif st == "q3":
            rc |= run("q3", ["q3.py"])
            rc |= run("q3-fix", ["fixsol.py"])
            # 修正物理模型下重算中继方案（2 架折中 + 3 架增配），并回填 solution.json
            if not a.no_refresh:
                rc |= run("q3-refresh", ["q3refresh.py", "--topk", "400"], timeout=3600)
            # N=2 不可行性判定（状态 DP），--n3 才重跑 3 架的 DP（约 30 分钟）
            args = ["q3final.py"] + (["--n3"] if a.n3 else [])
            rc |= run("q3-final", args, timeout=9000)
            # 诊断类结果文件合并（供 make_numbers.py 读取，避免依赖过期日志）
            rc |= run("q3-diag", ["q3diag.py"])'''
assert s.count(old_q3) == 1, ("q3", s.count(old_q3))
s = s.replace(old_q3, new_q3)

# ---------------- 4) q4 阶段追加双口径情景 ----------------
old_q4 = '''        elif st == "q4":
            rc |= run("q4", ["q4.py"])'''
new_q4 = '''        elif st == "q4":
            rc |= run("q4", ["q4.py"])
            rc |= run("q4-relay3", ["q4_relay3.py"])'''
assert s.count(old_q4) == 1, ("q4", s.count(old_q4))
s = s.replace(old_q4, new_q4)

# ---------------- 5) 新增 check_env() ----------------
old_tail = '''if __name__ == "__main__":
    sys.exit(main())'''
new_tail = '''def check_env():
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
    from dcore import find_bin as _fb
        xelatex = _fb("xelatex")
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
    sys.exit(main())'''
assert s.count(old_tail) == 1, ("tail", s.count(old_tail))
s = s.replace(old_tail, new_tail)

# ---------------- 6) 文件参数用正斜杠（xelatex 要求） ----------------
s = s.replace('"-output-directory=paper", "paper/paper.tex"',
              '"-output-directory=paper", "paper/paper.tex"')

io.open(P, "w", encoding="utf-8").write(s)
print("run_all.py 已更新（5 处结构改动 + check_env）")
