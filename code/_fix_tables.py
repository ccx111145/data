# -*- coding: utf-8 -*-
"""_fix_tables.py —— 修正审读发现的三处表格缺陷（直接改生成器，保证重跑不回归）：
  表5 ρ 灵敏度：ρ=40% 不可行时应写「不可行」而不是 nan；
  表6 问题二方案对比：补上权重列（正文称"权重见表内"但表里没有）；
  表7 问题三中继架次明细：表题与数据源过期（"仅列前 14 个"实际 3 行、引用已废弃的 Q3_中继试算.xlsx）。
"""
P = r"R:\claude\bitget_grid\国赛路嗯嗯\D题\code\make_numbers.py"
s = open(P, encoding="utf-8").read()

# ---- 表 5：nan -> 不可行 ----
old5 = '''                "%s" % (int(r["最少架次数"]) if r.get("最少架次数") == r.get("最少架次数") else "—"),
                "%.2f" % float(r.get("最少架次方案总能耗_kWh", float("nan"))),
            ])
        table(r"返航安全余量 $\\rho$ 灵敏度：载荷上限与全场景架次数",'''
new5 = '''                "%s" % (int(r["最少架次数"]) if r.get("最少架次数") == r.get("最少架次数") else "不可行"),
                ("%.2f" % float(r["最少架次方案总能耗_kWh"]))
                if r.get("最少架次方案总能耗_kWh") == r.get("最少架次方案总能耗_kWh") else "不可行",
            ])
        table(r"返航安全余量 $\\rho$ 灵敏度：载荷上限与全场景架次数"
              r"（「不可行」表示该 $\\rho$ 下 S004/S008 连空载往返都不满足能量约束，全场景无可行组批方案）",'''
if old5 not in s:
    print("MISS table5")
s = s.replace(old5, new5)

# ---- 表 6：补权重列 ----
old6 = '''        rows = []
        for nm, v in sorted(summ.items(), key=lambda kv: kv[1].get("count", 0)):
            rows.append([TEX(nm), "%d" % int(v.get("count", 0)),'''
new6 = '''        WTXT = {
            "P1-架次优先": "4:1:1:1",
            "P2-及时优先": "0.5:1:0.5:6",
            "P3-能耗优先": "1:6:1:1",
            "P4-完工优先": "0.5:0.5:6:1",
            "P5-均衡": "1.5:2:2:2",
        }
        rows = []
        for nm, v in sorted(summ.items(), key=lambda kv: kv[1].get("count", 0)):
            rows.append([TEX(nm), WTXT.get(nm, "—"), "%d" % int(v.get("count", 0)),'''
if old6 not in s:
    print("MISS table6")
s = s.replace(old6, new6)

old6b = '''              [r"方案", r"架次数", r"能耗/kWh", r"完工时间/h", r"延误量/h",
               r"及时率", r"覆盖箱数", r"硬约束违反"],
              rows, align="lrrrrrrr", size=r"\\footnotesize")'''
new6b = '''              [r"方案", r"权重$^*$", r"架次数", r"能耗/kWh", r"完工时间/h", r"延误量/h",
               r"及时率", r"覆盖箱数", r"硬约束违反"],
              rows, align="lrrrrrrrr", size=r"\\footnotesize",
              note=r"$^*$ 权重顺序为「架次数 : 能耗 : 完工时间 : 加权延误」。"
                   r"五组权重下得到的均为**非支配解**，不构成全局 Pareto 前沿的证明。")'''
if old6b not in s:
    print("MISS table6b")
s = s.replace(old6b, new6b)

# ---- 表 7：表题与数据源 ----
old7 = '''        table(r"问题三中继架次明细（按起飞时刻排序，仅列前 14 个；完整表见 results/Q3\\_中继试算.xlsx）",'''
new7 = '''        table(r"问题三中继架次明细 —— \\textbf{库存口径（2 架中继）下的最优折中方案}，共 %d 个架次；"
              r"达成全程连续通信所需的 3 架增配方案见 results/结果提交.xlsx 的"
              r"「Q3\\_中继架次\\_增配方案」表" % len(rl),'''
if old7 not in s:
    print("MISS table7")
s = s.replace(old7, new7)
s = s.replace('        for r in sorted(rl, key=lambda x: float(x.get("depart", 0)))[:14]:',
              '        for r in sorted(rl, key=lambda x: float(x.get("depart", 0))):')
open(P, "w", encoding="utf-8").write(s)
print("patched make_numbers.py")
