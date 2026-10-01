# -*- coding: utf-8 -*-
"""_repack.py —— 把最新论文/结果/程序刷新到桌面交付包（v3 布局）。

与 `make_submission_pack.py`（投稿包）的区别
--------------------------------------------
交付包是**复现用**：含全部代码/结果/数据，体积大，不是给期刊上传的。
投稿包只含稿件、源码、投稿文书。

本脚本的失败语义（本轮修）
--------------------------
以前 `cp()` 遇到缺失输入只打印 `! 缺失，跳过` 然后**照常返回 0**：
包看着是"刷新完成"，实际少了一整章（例如 `paper_en/main.pdf` 不在就是
少了 06_英文SCI稿）。审计的结论是——打包脚本不能有"静默部分成功"这种状态。
现在：

  1. 先跑 `code/check_consistency.py`，退出码非 0 立即中止；
  2. **预检**全部必需输入，缺任何一个就在动 D 之前中止（不留半成品包）；
  3. 复制过程再报一次缺失（异常路径），最后以非零退出。

用法：python _repack.py [--out "C:\\Users\\ASUS\\Desktop\\D题_完整交付"]
      （也可用环境变量 PKG_DST，--out 优先）
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.dirname(HERE)                                   # .../D题
DEFAULT_DST = r"C:\Users\ASUS\Desktop\D题_完整交付"

N_PY = 0
MISSING = []            # 复制阶段才发现的缺失（预检之后）
REQUIRED_MISSING = []   # 预检发现的缺失


def cp(src, dst):
    if not os.path.exists(src):
        print("  ! 缺失，跳过：%s" % src)
        REQUIRED_MISSING.append(src)
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def cpsrc(name):
    """复制单个脚本到 03_程序/。"""
    global N_PY
    if cp(os.path.join(S, "code", name), os.path.join(D, "03_程序", name)):
        N_PY += 1


# ---------------- 输入清单（预检用，与下面的复制严格对应）----------------
PAPER_FILES = ("paper.pdf", "paper.tex", "numbers.tex", "tables.tex",
               "q3_gap.tex", "q3_gap_sources.txt")
EN_FILES = ("main.pdf", "main.tex", "refs.bib", "numbers_en.tex",
            "numbers_en_sources.txt", "README_en.md",
            "main_elsarticle.tex", "main_elsarticle.pdf",
            "main_ieee.tex", "main_ieee.pdf")
RES_FLAT = ["结果提交.xlsx", "检查说明.md", "Q4_说明.md", "Q4_分区配置.xlsx",
            "Q4_中继增配情景.md", "Q4_中继增配情景.json",
            "灵敏度分析.md", "灵敏度分析.xlsx",
            "防线1_换位模式对比.md", "Q1_最大安全载荷.xlsx",
            "标准解_solution.json", "Q3_方案汇总.json", "Q3_诊断汇总.json",
            # —— SCI 新增结果 ——
            "信道模型对比.md", "信道模型对比.json",
            "多地形基准.md", "多地形基准.json",
            "中继基线与下界.md", "中继基线与下界.json",
            "协同再调度.md", "协同再调度.json",
            "基线与消融.md", "基线与消融.json",
            # —— 理论量：span / alibi 放行率 / 机队规模下界 ——
            "局部阻塞证书.json",
            # —— 方法学交叉验证：相位级整数规划区间松弛 ——
            "中继ILP松弛.json",
            # —— 运输侧教科书级外部基线：Clarke–Wright 节约算法 ——
            "文献启发式对照.json", "文献启发式对照.md",
            # —— 参考文献核实原始返回（Crossref API）——
            "文献核实.json",
            # —— 审稿意见核实报告 ——
            "审稿意见核实报告.md",
            # —— 参数无关证书检验 ——
            "参数无关证书.json",
            # —— P.526 下 N=4 的完整轨迹 ——
            "P526_N4_轨迹.json",
            "SCI增补实验报告.md"]


def _res_src(f):
    return os.path.join(S, "results", "solution.json" if f == "标准解_solution.json" else f)


def preflight():
    """动 D 之前把必需输入点一遍名。返回缺失清单。"""
    req = [os.path.join(S, "交付包说明.md"),
           os.path.join(S, "交付说明.md"),
           os.path.join(S, "审题笔记.md")]
    req += [os.path.join(S, "paper", f) for f in PAPER_FILES]
    req += [os.path.join(S, "paper_en", f) for f in EN_FILES]
    req += [_res_src(f) for f in RES_FLAT]
    return [p for p in req if not os.path.exists(p)]


def main():
    global D
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("PKG_DST") or DEFAULT_DST)
    ap.add_argument("--no-gate", action="store_true",
                    help="跳过一致性体检（默认**不跳过**；只在明确知道自己在"
                         "干什么时用，跳过的包不得当投稿材料用）")
    a = ap.parse_args()
    D = a.out
    t0 = time.time()

    # ---------------- 0) 一致性体检：失败即中止（非零退出）----------------
    gate = os.path.join(HERE, "check_consistency.py")
    if a.no_gate:
        print("!! 已按 --no-gate 跳过一致性体检——本次产出的包不保证与稿件同源。")
    else:
        if not os.path.exists(gate):
            print("!! 找不到一致性体检脚本 %s" % gate)
            return 2
        print("== 一致性体检（code/check_consistency.py）==")
        r = subprocess.run([sys.executable, gate], cwd=S)
        if r.returncode != 0:
            print("\n!! 一致性体检未通过（退出码 %d）——已中止刷新交付包。"
                  % r.returncode)
            return 1
        print()

    # ---------------- 1) 预检必需输入：缺任何一个都不动 D ----------------
    miss = preflight()
    if miss:
        print('!! 必需输入缺失 %d 个——**没有动交付包**（不做"静默部分成功"）：'
              % len(miss))
        for p in miss:
            print("   - %s" % p)
        return 3
    print("预检通过：必需输入全部在场\n")

    # ---------------- 00 请先读我 ----------------
    cp(os.path.join(S, "交付包说明.md"), os.path.join(D, "00_请先读我.md"))

    # ---------------- 01 论文 ----------------
    cp(os.path.join(S, "paper", "paper.pdf"),
       os.path.join(D, "01_论文", "论文_山区洪涝灾害下无人机运输与通信协同优化.pdf"))
    for f in PAPER_FILES[1:]:
        cp(os.path.join(S, "paper", f), os.path.join(D, "01_论文", f))
    os.makedirs(os.path.join(D, "01_论文", "图"), exist_ok=True)
    for f in os.listdir(os.path.join(S, "figs")):
        if f.endswith(".png"):
            cp(os.path.join(S, "figs", f), os.path.join(D, "01_论文", "图", f))

    # ---------------- 01b 英文 SCI 稿 ----------------
    EN = os.path.join(D, "06_英文SCI稿")
    cp(os.path.join(S, "paper_en", "main.pdf"), os.path.join(EN, "main.pdf"))
    for f in EN_FILES[1:]:
        cp(os.path.join(S, "paper_en", f), os.path.join(EN, f))
    os.makedirs(os.path.join(EN, "figs"), exist_ok=True)
    # 英文稿引用的是 figs/xxx.png，且它的 fig 目录比中文稿多出 fig_en_theory.png，
    # 因此以 paper_en/figs 为准复制（而不是以 figs 为准），否则会漏图或放错层级。
    _en_figs = os.path.join(S, "paper_en", "figs")
    if os.path.isdir(_en_figs):
        for f in sorted(os.listdir(_en_figs)):
            if f.endswith(".png"):
                cp(os.path.join(_en_figs, f), os.path.join(EN, "figs", f))
    else:
        print("  ! 缺失目录，跳过：%s" % _en_figs)
        REQUIRED_MISSING.append(_en_figs)

    # ---------------- 02 结果 ----------------
    os.makedirs(os.path.join(D, "02_结果", "诊断明细"), exist_ok=True)
    for f in RES_FLAT:
        cp(_res_src(f), os.path.join(D, "02_结果", f))
    RES = os.path.join(S, "results")
    for f in os.listdir(RES):
        if f.endswith(".json") and f.startswith(("换位模式", "构造性贪心", "跨度黑障",
                                                 "结构诊断", "DP阻塞", "DP_air",
                                                 "DP_base", "协同再调度",
                                                 "Q1_前沿", "重算_物理修正后",
                                                 "局部阻塞证书", "中继ILP松弛")):
            cp(os.path.join(RES, f), os.path.join(D, "02_结果", "诊断明细", f))

    # ---------------- 03 程序 ----------------
    os.makedirs(os.path.join(D, "03_程序"), exist_ok=True)
    for f in sorted(os.listdir(os.path.join(S, "code"))):
        if f.endswith(".py"):
            cpsrc(f)

    # ---------------- 05 审题与说明 ----------------
    cp(os.path.join(S, "交付说明.md"), os.path.join(D, "05_审题与说明", "交付说明.md"))
    cp(os.path.join(S, "审题笔记.md"), os.path.join(D, "05_审题与说明", "审题笔记.md"))
    cp(os.path.join(S, "交付包说明.md"), os.path.join(D, "05_审题与说明", "版本修订说明_v3.md"))
    REV = os.path.join(S, "审阅意见处理对照表.md")
    if os.path.exists(REV):
        cp(REV, os.path.join(D, "05_审题与说明", "审阅意见处理对照表.md"))
        cp(REV, os.path.join(D, "审阅意见处理对照表.md"))
    else:
        print("  -- 可选文件不在场，跳过：%s" % REV)
    rep = os.path.join(os.path.dirname(S), "_repro_test.log")
    if os.path.exists(rep):
        cp(rep, os.path.join(D, "05_审题与说明", "全新目录复现测试日志.txt"))
    else:
        print("  -- 可选文件不在场，跳过：%s" % rep)

    # ---------------- 汇总 ----------------
    if REQUIRED_MISSING:
        print("\n!! 复制阶段仍有 %d 个必需输入缺失——交付包**不完整**："
              % len(REQUIRED_MISSING))
        for p in REQUIRED_MISSING:
            print("   - %s" % p)
        return 1
    if not os.path.isdir(D):
        print("\n!! 目标目录未生成：%s" % D)
        return 1

    n = sum(len(fs) for _, _, fs in os.walk(D))
    sz = sum(os.path.getsize(os.path.join(r, f))
             for r, _, fs in os.walk(D) for f in fs)
    print("刷新完成：%d 个文件，%.1f MB（本脚本复制 %d 个 .py，用时 %.0f s）"
          % (n, sz / 1048576, N_PY, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
