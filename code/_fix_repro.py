# -*- coding: utf-8 -*-
"""_fix_repro.py —— 把 `_repro_test.py` 的比对升级为「分段 + 可解释」。

本测试为控制成本**不重跑问题二的随机搜索（ALNS）**，而是以工作区的 `solution.json`
作为输入，复现问题一与问题三之后的全部派生结果。因此 `numbers.tex` / `tables.tex` 中
与问题二有关的宏/表在复现目录里必然为「待补/缺失」——这是取舍而非失败。
新比对分三段：① 关键数值；② `q3_gap.tex` 逐字节（承载问题三全部结论数字）；
③ `numbers.tex`/`tables.tex` 剔除问题二部分后逐字节。另加 `--compare-only` 秒级重跑比对。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "_repro_test.py")
s = io.open(P, encoding="utf-8").read()

NEWCMP = r'''def _compare():
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

    def strip_q2(txt):
        out = [ln for ln in txt.split("\n")
               if not re.match(r"\\newcommand\{\\Qtwo", ln)]
        return re.sub(r"\\begin\{table\}\[htbp\].*?问题二五种权重配置.*?\\end\{table\}",
                      "", "\n".join(out), flags=re.S)

    for f in ("numbers.tex", "tables.tex"):
        pa, pb = os.path.join(SRC, "paper", f), os.path.join(DST, "paper", f)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            checks.append(("paper/%s（剔除问题二部分）" % f, "—", "缺失"))
            continue
        ta = strip_q2(_io.open(pa, encoding="utf-8").read())
        tb = strip_q2(_io.open(pb, encoding="utf-8").read())
        checks.append(("paper/%s（剔除问题二部分）" % f, "—",
                       "一致" if ta == tb else "不一致"))

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
        ok = True if info else ((x == y) or (y == "一致"))
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


'''

i5 = s.find("    # ---------- 5) 比对关键数字 ----------")
i6 = s.find('if __name__ == "__main__":')
assert i5 > 0 and i6 > i5, (i5, i6)
s = s[:i5] + "    # ---------- 5) 比对 ----------\n    return _compare()\n\n\n" + NEWCMP + s[i6:]
s = s.replace('''if __name__ == "__main__":
    sys.exit(main())''', '''if __name__ == "__main__":
    if "--compare-only" in sys.argv:
        sys.exit(compare_only())
    sys.exit(main())''')
if "\nimport re\n" not in s:
    s = s.replace("import filecmp\n", "import filecmp\nimport re\n", 1)
io.open(P, "w", encoding="utf-8").write(s)
print("_repro_test.py 已重构（分段比对 + --compare-only）")
