# -*- coding: utf-8 -*-
"""_fix_verify.py —— 修正 verify_sim.py（检查说明.md 生成器）中几处过期/越界表述：

  * 「不存在满足全程连续通信的可行调度」→ 改为「在给定候选集与剪枝下未找到」
    （审阅 #2：不得把「未找到」写成「不存在」）；
  * 硬编码的「3 架中继、7 个架次」→ 改为从 relay3 / Q3_方案汇总.json 读实际值；
  * 「已含回 O01 更换能源组件的拆分」→ 改为如实说明架次数取自构造性判定器；
  * 补齐口径声明（覆盖率 / 相位时长之和 / 中断并集三者不同）。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "verify_sim.py")
s = io.open(P, encoding="utf-8").read()
n = 0


def rep(old, new, tag):
    global s, n
    c = s.count(old)
    print("[%s] %s（%d）" % ("OK" if c == 1 else "MISS", tag, c))
    if c == 1:
        s = s.replace(old, new)
        n += 1


rep('''    out("第 9 项的不通过**不是**中继求解失败，而是一个**判定性结论**：在题目给定的库存")
    out("（2 架中继无人机）下，本场景**不存在**满足「全程连续通信」的可行调度。")''',
    '''    out("第 9 项的不通过**不是**中继求解失败，而是**在给定候选悬停点集与剪枝策略下")
    out("未找到**满足「全程连续通信」的 2 架中继调度；该结论由状态 DP 与独立的构造性判定")
    out("分别在不同需求格处复现（四档候选规模 12/24/40/400 均未找到）。")
    out()
    out("> **证明强度声明**：DP 的实现含四类剪枝（候选点取前 k、支配剪枝、每键限额、状态总数上限），")
    out("> 因此严格表述是「未找到」而非「数学上不存在」；且结论只对**冻结的运输时序**成立。")
    out("> 已完成构造性验证的是 3 架方案的**可行性**（给出显式架次表并逐实例复核）。")''',
    "#2 判定强度")

rep('''        out("| 3 架中继（最小增配）可行性 | 可行：需求实例覆盖 100%、时序冲突 0、返航电量违反 0 |")
        out("| 增配后中继架次数 | %s 个（已含回 O01 更换能源组件的拆分）|" % (ra.get("n3_sorties", len(r3))))
        out("| 增配后中继总能耗 | %.3f kWh |" % float(ra.get("n3_energy", 0.0)))''',
    '''        out("| 3 架中继（最小增配）可行性 | 可行：需求实例覆盖 100%、时序冲突 0、返航电量违反 0 |")
        out("| 增配后中继架次数 | %s 个（构造性判定器给出的换位动作序列还原，"
            "已满足单个能源组件容量，无需再拆分）|" % (ra.get("n3_sorties", len(r3))))
        out("| 增配后中继总能耗 | %.3f kWh |" % float(ra.get("n3_energy", 0.0)))
        _pc = (_q3s or {}).get("n2", {}).get("cover_pct")
        if _pc is not None:
            out("| 2 架折中方案的失联时长覆盖率 | %.1f%%（被中继完整保障的需求时间格占比）|" % float(_pc))
        out("| 2 架折中方案未派中继的相位 | %s 个，相位时长合计 %s s（**口径不同于中断并集**）|"
            % (ra.get("n2_outage_n", "—"), ra.get("n2_outage_s", "—")))''',
    "增配表口径")

rep('''    ra = (sol.get("meta") or {}).get("relay_analysis") or {}
    r3 = sol.get("relay3") or []''',
    '''    ra = (sol.get("meta") or {}).get("relay_analysis") or {}
    r3 = sol.get("relay3") or []
    try:
        with open(os.path.join(D.RESULTS, "Q3_方案汇总.json"), "r", encoding="utf-8") as _f:
            _q3s = json.load(_f)
    except Exception:                                             # noqa: BLE001
        _q3s = {}''',
    "读方案汇总")

rep('''    out("**本次提交的方案定位**：`Q3_中继架次` 表给出的是**库存约束下的最优折中方案**——")
    out("它满足除「通信连续」之外的全部约束（载重、体积、返航能量、电池周转、时限、资源可用性，")
    out("且时序冲突 0、返航电量违反 0）；**达成全程连续通信的最小增配方案**（3 架中继、")
    out("7 个架次、覆盖率 100%）见 `结果提交.xlsx` 的 `Q3_中继架次_增配方案` 与")
    out("`Q3_中继缺口分析` 两张增补表。")''',
    '''    out("**本次提交的方案定位**：`Q3_中继架次` 表给出的是**库存约束下的折中方案**——")
    out("它满足除「通信连续」之外的全部约束（载重、体积、返航能量、电池周转、时限、资源可用性，")
    out("且时序冲突 0、返航电量违反 0），但**在通信连续性一项上确实欠账**；")
    out("**达成全程连续通信的增配方案**（%s 架中继、%s 个架次、需求实例覆盖 100%%）见 "
        "`结果提交.xlsx` 的 `Q3_中继架次_增配方案` 与 `Q3_中继缺口分析` 两张增补表。"
        % (ra.get("n_relay_required", 3), ra.get("n3_sorties", len(r3))))''',
    "方案定位")

io.open(P, "w", encoding="utf-8").write(s)
print("verify_sim.py 已更新 %d 处" % n)
