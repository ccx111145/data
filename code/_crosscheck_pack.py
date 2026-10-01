# -*- coding: utf-8 -*-
"""_crosscheck_pack.py —— 把投稿包文本文件里的数字与论文宏逐条对齐。

为什么需要：正文改过 5 轮，而 03_Highlights.txt / 04_Cover_Letter.txt 这类
"外围文件"从来没进过检查闸门（check_consistency.py 只扫 main.tex 与两个变体）。
结果就是正文已撤回的说法，在外围文件里原封不动地留着——审稿人一对照就露。
本脚本把外围文件里出现的可辨认数值逐条与 numbers_en.tex 的宏做比对。
"""
from __future__ import annotations

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_EN = os.path.join(BASE, "paper_en")
DESK = r"C:\Users\ASUS\Desktop\D题_投稿包"

# 外围文件里的"数值表述" -> 应与之相符的宏（None 表示该值不对应宏，人工核）
CHECKS = [
    ("understates the fleet by 2 vehicles", "ENrbPremium", "2"),
    ("raises outage demand 32.2%", "ENchReqDelta", "32.2"),
    ("raises outage demand by 32.2 percent", "ENchReqDelta", "32.2"),
    ("removes 49.2 percent", "ENchCandDeltaAbs", "49.2"),
    ("moves the minimum fleet from 3 to 4", None, None),
    ("reaches 13 sorties", "ENcwSorties", "13"),
    ("61.26 kWh", "ENcwEnergy", "61.26"),
    # 注意：这里的 20 / 76.04 是 **文献启发式对照实验** 里 ALNS 那一臂的宏
    # （ENcwAlns*），不是消融实验里的 ALNS 无 CP-SAT（那个是 17 / 67.90，
    # 见 ENbaseAlns*）。两者跑批预算不同，不能互相核对——早先我用
    # ENbaseAlns* 去比，误报了两条"不符"。
    ("our 20 sorties", "ENcwAlnsSorties", "20"),
    ("76.04 kWh", "ENcwAlnsEnergy", "76.04"),
    ("30111 s", "ENcwHard", "30111"),
]


def macros() -> dict:
    t = io.open(os.path.join(PAPER_EN, "numbers_en.tex"), encoding="utf-8").read()
    return dict(re.findall(r"\\newcommand\{\\([A-Za-z0-9]+)\}\{([^}]*)\}", t))


def _num(s: str) -> float:
    try:
        return float(str(s).strip().lstrip("+"))
    except ValueError:
        return float("nan")


def main() -> int:
    mac = macros()
    files = []
    for n in os.listdir(DESK):
        if n.endswith(".txt"):
            files.append(os.path.join(DESK, n))
    bad = 0
    for path in files:
        t = io.open(path, encoding="utf-8").read()
        name = os.path.basename(path)
        for phrase, macro, expect in CHECKS:
            if phrase not in t:
                continue
            if macro is None:
                print("  [手工核] %-28s %-34s" % (name, phrase[:32]))
                continue
            got = mac.get(macro, "(缺)")
            # 宏可能带正号（\ENchReqDelta 是 "+32.2"，供正文写 "up by" 用）；
            # 外围文件写裸数字，比较时把符号与首尾空白归一化。
            g = str(got).strip().lstrip("+")
            ok = g == str(expect).strip() or abs(
                _num(g) - _num(str(expect))) < 1e-9
            print("  [%s] %-28s %-34s 宏 %s=%s" % ("OK " if ok else "!! ", name,
                                                   phrase[:32], macro, got))
            if not ok:
                bad += 1
    print()
    print("数值不符 %d 条" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
