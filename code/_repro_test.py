# -*- coding: utf-8 -*-
"""_repro_test.py —— 全新目录复现测试（审阅 #30）。

在**交付包的目录布局**下（03_程序/ + 04_数据与模板/数据/ + 02_结果/）
把流水线从「问题三中继重算」一路跑到「论文编译」，并逐项比对工作区结果，
用日志证明"换一台机器、换一个目录也能跑出同一套数字"。

设计取舍：问题二的 ALNS 是随机搜索（受 PYTHONHASHSEED 与运行时预算影响），
逐位复现代价高且非本次回归目标，因此本测试**以工作区的 solution.json 为输入**，
复现 q3 之后的所有派生结果（中继方案、结果表、校验报告、Q4、论文数字宏、插图、PDF）。
"""
from __future__ import annotations

import filecmp
import re
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)                     # 本脚本所在 code/ 的上一级 = 工作区根
DST = os.environ.get("REPRO_DST") or os.path.join(os.path.dirname(SRC), "_repro_test")
PY = sys.executable
LOG = os.path.join(os.path.dirname(DST), "_repro_test.log")


def sh(cmd, cwd, timeout=3600):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt = r.stdout.decode("utf-8", errors="replace")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 78 + "\n$ (%s) %s\n" % (cwd, " ".join(cmd)))
        f.write(txt)
    print("  -> %s  rc=%d  %.0f s" % (" ".join(cmd[:1]) + " " + " ".join(cmd[1:2]), r.returncode,
                                      time.time() - t0))
    return r.returncode, txt


def main():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    open(LOG, "w", encoding="utf-8").write("全新目录复现测试 %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))

    # ---------- 1) 按交付包布局搭目录 ----------
    os.makedirs(os.path.join(DST, "03_程序"))
    os.makedirs(os.path.join(DST, "04_数据与模板"))
    os.makedirs(os.path.join(DST, "02_结果"))
    os.makedirs(os.path.join(DST, "paper"))
    for f in os.listdir(os.path.join(SRC, "code")):
        if f.endswith(".py"):
            shutil.copy2(os.path.join(SRC, "code", f), os.path.join(DST, "03_程序", f))
    shutil.copytree(os.path.join(SRC, "数据"), os.path.join(DST, "04_数据与模板", "数据"))
    # 官方结果提交模板（与交付包布局一致：放在 04_数据与模板/ 下）
    tpl = os.path.join(SRC, "结果提交模板.xlsx")
    if os.path.exists(tpl):
        shutil.copy2(tpl, os.path.join(DST, "04_数据与模板", "结果提交模板.xlsx"))
    else:
        print("  ! 工作区未找到 结果提交模板.xlsx，复现时 export_results.py 会走降级路径")
    os.makedirs(os.path.join(DST, "results"), exist_ok=True)
    shutil.copy2(os.path.join(SRC, "results", "solution.json"),
                 os.path.join(DST, "results", "solution.json"))
    for f in ("paper.tex",):
        shutil.copy2(os.path.join(SRC, "paper", f), os.path.join(DST, "paper", f))
    shutil.copytree(os.path.join(SRC, "figs"), os.path.join(DST, "figs"))
    print("已搭建交付包布局：%s" % DST)

    CODE = os.path.join(DST, "03_程序")
    rc_all = 0

    # ---------- 2) 环境自检 ----------
    # 注意：全新目录里 results/ 尚未产出，check-env 会如实报「结果缺失」并以 rc=1 退出，
    # 这是**预期行为**而非失败——这里只校验路径与依赖是否解析正确。
    rc, txt = sh([PY, "run_all.py", "--check-env"], CODE)
    data_line = [l for l in txt.splitlines() if "数据目录 DATA" in l]
    print("  %s" % (data_line[0].strip() if data_line else "未打印数据目录"))
    env_bad = [l.strip() for l in txt.splitlines()
               if ("缺失：" in l and "结果 " not in l) or "失败：" in l]
    if env_bad:
        print("  !! 环境自检发现真实问题：")
        for l in env_bad:
            print("     " + l)
        rc_all |= 1
    else:
        print("  -> 环境自检通过（仅 results/ 待生成，符合预期），路径与依赖均解析正确")

    # ---------- 3) 顺序复现派生结果 ----------
    steps = [
        ("q1.py", 3600),                     # 问题一：最大安全载荷 + 组批（产物 Q1_最大安全载荷.xlsx）
        ("vq1.py", 3600),                    # CP-SAT 交叉验证
        ("q3refresh.py --topk 400", 3600),   # 问题三中继方案（修正物理后）
        ("q3diag.py --run", 3600),   # 连诊断脚本一起跑，保证稳健性数字可复现
        ("q4.py", 900),
        ("q4_relay3.py", 600),
        ("export_results.py", 900),
        ("verify_sim.py", 900),
        ("make_numbers.py", 900),
        ("make_figs.py", 1800),
    ]
    for cmd, to in steps:
        rc, _ = sh([PY] + cmd.split(), CODE, timeout=to)
        rc_all |= rc

    # ---------- 4) 编译论文 ----------
    from dcore import find_bin as _fb
    xelatex = _fb("xelatex")
    if os.path.exists(xelatex):
        for _ in range(2):
            sh([xelatex, "-interaction=nonstopmode", "paper/paper.tex"], DST, timeout=1200)
        pdfs = [os.path.join(DST, "paper", "paper.pdf"), os.path.join(DST, "paper.pdf")]
        found = [p for p in pdfs if os.path.exists(p)]
        print("  -> paper.pdf：%s" % (found[0] if found else "未生成"))

    # ---------- 5) 比对 ----------
    return _compare()


def _compare():
    """分段比对：① 关键数值；② q3_gap.tex 逐字节；③ 剔除问题二部分后的宏文件逐字节。"""
    import io as _io

    def load(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:                                          # noqa: BLE001
            return None

    checks = []
    a = load(os.path.join(SRC, "results", "solution.json")) or {}
    b = load(os.path.join(DST, "results", "solution.json")) or {}
    for key in ("relay", "relay3"):
        ra, rb = a.get(key) or [], b.get(key) or []
        checks.append(("solution.%s 架次数" % key, len(ra), len(rb)))
        if ra and rb:
            checks.append(("solution.%s 总能耗(kWh)" % key,
                           round(sum(x["e_total"] for x in ra), 3),
                           round(sum(x["e_total"] for x in rb), 3)))
            checks.append(("solution.%s 逐架次能耗序列" % key, "—",
                           "一致" if [round(x["e_total"], 4) for x in ra]
                           == [round(x["e_total"], 4) for x in rb] else "不一致"))
    sa = load(os.path.join(SRC, "results", "Q3_方案汇总.json")) or {}
    sb = load(os.path.join(DST, "results", "Q3_方案汇总.json")) or {}
    for lbl, k1, k2 in (("Q3 N=2 未覆盖实例", "n2", "miss"),
                        ("Q3 N=3 架次数", "n3", "sorties"),
                        ("Q3 N=3 能量(kWh)", "n3", "energy"),
                        ("Q3 N=3 单架次最大悬停(s)", "n3", "max_hover"),
                        ("Q3 相位数", "struct", "phases"),
                        ("Q3 单次驻留上限(s)", "struct", "energy_cap_s"),
                        ("Q3 N=2 覆盖率(%)", "n2", "cover_pct")):
        checks.append((lbl, sa.get(k1, {}).get(k2), sb.get(k1, {}).get(k2)))

    pa, pb = os.path.join(SRC, "paper", "q3_gap.tex"), os.path.join(DST, "paper", "q3_gap.tex")
    same = os.path.exists(pa) and os.path.exists(pb) and filecmp.cmp(pa, pb, shallow=False)
    checks.append(("paper/q3_gap.tex（问题三全部结论宏）", "—",
                   "一致" if same else "不一致"))

    def macros_of(p):
        r"""解析 newcommand{Name}{Value} 为 {name: value}，剔除问题二的 Qtwo* 宏。"""
        t = _io.open(p, encoding="utf-8").read()
        d = {}
        for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{([^}]*)\}", t):
            if m.group(1).startswith("Qtwo"):
                continue
            d[m.group(1)] = m.group(2)
        return d

    def tables_of(p):
        """各 table 的 (label, caption)；剔除标题含「问题二」的表。"""
        t = _io.open(p, encoding="utf-8").read()
        out = []
        for m in re.finditer(r"\\begin\{table\}.*?\\end\{table\}", t, flags=re.S):
            blk = m.group(0)
            lab = re.search(r"\\label\{([^}]*)\}", blk)
            cap = re.search(r"\\caption\{([^}]*)\}", blk)
            if cap and "问题二" in cap.group(1):
                continue
            out.append((lab.group(1) if lab else "", cap.group(1) if cap else ""))
        return out

    for f in ("numbers.tex", "tables.tex"):
        pa, pb = os.path.join(SRC, "paper", f), os.path.join(DST, "paper", f)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            checks.append(("paper/%s 宏与表（剔除问题二）" % f, "—", "缺失"))
            continue
        ma, mb = macros_of(pa), macros_of(pb)
        diff = [k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k)]
        checks.append(("paper/%s 宏（剔除 \\Qtwo*）共 %d 个" % (f, len(ma)),
                       "工作区", "%d 处不同" % len(diff) if diff else "全部一致"))
        if f == "tables.tex":
            ta, tb = tables_of(pa), tables_of(pb)
            checks.append(("paper/%s 表标题/标签（剔除问题二表）" % f, "工作区",
                           "一致" if ta == tb else "%d vs %d 张不同" % (len(ta), len(tb))))

    n_pending = 0
    pn = os.path.join(DST, "paper", "numbers.tex")
    if os.path.exists(pn):
        n_pending = len(re.findall(r"\\newcommand\{\\Qtwo[A-Za-z]*\}\{待补\}",
                                   _io.open(pn, encoding="utf-8").read()))
    checks.append(("问题二相关宏为「待补」（设计取舍，不计失败）",
                   "工作区已产出", "%d 个待补" % n_pending))

    print("\n" + "-" * 94)
    print("%-48s %-18s %-18s %s" % ("检查项", "工作区", "复现目录", "结论"))
    print("-" * 94)
    bad = 0
    for name, x, y in checks:
        info = str(y).endswith("个待补")
        ok = bool(info or (x == y) or (str(y) in ("一致", "全部一致")))
        bad += 0 if ok else 1
        print("%-48s %-18s %-18s %s" % (name, x, y, "OK" if ok else "**不一致**"))
    print("-" * 94)
    print("不一致 %d 项（问题二部分按设计跳过，仅作说明）。日志：%s" % (bad, LOG))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n\n===== 复现比对结果 =====\n")
        f.write("不一致 %d 项（问题二部分按设计跳过）\n" % bad)
        for name, x, y in checks:
            f.write("  %-48s %-18s %-18s\n" % (name, x, y))
    return 0 if bad == 0 else 1


def compare_only():
    """复用已生成的 _repro_test 目录，只重跑比对（秒级）。"""
    print("--compare-only：复用现有 %s" % DST)
    return _compare()


if __name__ == "__main__":
    if "--compare-only" in sys.argv:
        sys.exit(compare_only())
    sys.exit(main())
