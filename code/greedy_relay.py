# -*- coding: utf-8 -*-
"""
greedy_relay.py —— 构造性贪心判定：给定中继台数 N 与换位模式，是否存在**可行解**？

与状态 DP 的分工
----------------
* 状态 DP 是"精确判定"，但对候选悬停点集的大小敏感（候选越多状态越多，需截断）；
* 本贪心是"构造性下界"：只要它给出一个 0 未覆盖、0 时序冲突的完整方案，
  就**证明了可行**（存在性证据），可用来排除"DP 因候选截断而误判不可行"的风险。

规则
----
沿时间格前进；若当前 N 架的覆盖并集已覆盖该格全部需求则继续；
否则选择一次"最省的换位"：把某一架从旧点位 a 换到新点位 a'，使得
  1) 换位后覆盖并集满足需求；
  2) 换位黑障窗口内其余 N-1 架能**联合**覆盖全部需求；
  3) 该架已完成上一段驻留（可离站）；
  4) 新点位的可行驻留跨度足够长（避免频繁换位）；
换位动作按"新点位可驻留时长"降序贪心，若所有候选都失败则报不可行并给出首个失败时刻。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import numpy as np

import dcore as D
import q2 as Q
import q3 as Q3
import q3dpN as DN
import solution_io as SIO

OUT = D.RESULTS
GRID = 10.0
IDLE = -1


def build():
    inst = Q.Instance()
    sol = SIO.load()
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = list(r["route"][1:-1])
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"]) for a in areas for b in r["boxes"][a]}
        sorties.append(Q.Sortie(g=r["type"], areas=areas, load=load,
                                dur=float(r["end"]) - float(r["start"]),
                                E=float(r["energy"]), offs=offs))
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=0.0, soc=1.0)
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    return inst, ph


def _age_deadline(cells, pos, arr, r0, k, mode, cap_s, n):
    """预测「哪一架、在第几格会触顶在空/驻留上限」。返回 (slot, k_dead) 或 (None, None)。"""
    worst, wk = None, None
    for i, p in enumerate(pos):
        if p == IDLE:
            continue
        ref = arr[i] if mode == "base" else r0[i]
        # 二分找首个 cells[k'] - cells[ref] > cap_s 的 k'
        lo, hi = k, n - 1
        if cells[hi] - cells[ref] <= cap_s:
            continue
        while lo < hi:
            mid = (lo + hi) // 2
            if cells[mid] - cells[ref] > cap_s:
                hi = mid
            else:
                lo = mid + 1
        if wk is None or lo < wk:
            worst, wk = i, lo
    return worst, wk


def try_preposition(inst, ph, pb, cells, pos, arr, r0, k, need, mode, cap_s, n,
                    lead_cells=400, safety=0.85):
    """预防性换位：在**当前覆盖仍然成立**时，提前把一架空闲中继派到"接管时刻"所需的位置。

    动机（诊断 α=0.35 地形时发现）：当失联需求在时间上**稀疏但跨度很长**时，
    单架中继会在 7233 s 的在空上限处触顶；若等到触顶那一刻才换位，
    换位黑障窗口内没有第二架在位，贪心必然失败。正确做法是**提前预置**第二架。

    时机的两个必要条件（必须同时成立才动作）：
      1. **来得及**：$t_k + t^{\\rm out}(p) + t_{\\rm link} \\le t_{k_{\\rm dead}}$；
      2. **不白耗**：$t_{k_{\\rm dead}} - t_{\\rm arr} \\le \\eta\\, T^{\\rm cap}$——
         到位后不能空等太久，否则第二架自己也会触顶（这正是"越早预置越好"的直觉陷阱）。
    """
    slot_dead, k_dead = _age_deadline(cells, pos, arr, r0, k, mode, cap_s, n)
    if slot_dead is None or k_dead is None or k_dead > k + lead_cells:
        return None
    idle = [j for j in range(len(pos)) if pos[j] == IDLE and j != slot_dead]
    if not idle:
        return None
    hi = min(n - 1, k_dead + 60)
    cand = list(pb.cand(k_dead, pb.need[k_dead]))
    if not cand:
        return None
    t_dead = float(cells[k_dead])
    best = None
    for p_new in cand:
        t_arr = float(cells[k]) + float(pb.TO[p_new]) + float(pb.t_link)
        if t_arr > t_dead - 1e-9:                     # 来不及到位
            continue
        if t_dead - t_arr > safety * cap_s:           # 太早：会把自己的在空预算耗光
            continue
        span = 0
        for kk in range(k_dead, hi + 1):
            if pb.need[kk] and (int(pb.mask[kk][p_new]) & pb.need[kk]) == pb.need[kk]:
                span += 1
            elif pb.need[kk]:
                break
        if span < 1:
            continue
        if best is None or span > best[0]:
            best = (span, p_new, t_arr)
    if best is None:
        return None
    span, p_new, t_arr = best
    j = idle[0]
    others = [pos[m] for m in range(len(pos)) if m != j]
    # （1）换位期间由其余各架顶住 —— 注意 slot_dead 仍在 others 里，
    #     所以这一步只证明"换位动作本身不制造黑障"。
    if not pb.union_ok(others, k, k - 1):
        return None
    # （2）换位动作本身的黑障窗口也必须逐格验证。
    #     从当前位置前往 p_new 的飞行期间该架不转发，窗口按**真实时间戳**算：
    #     k0 = before(k, w_sec)，与正常换位路径（第 183 行那种）用同一把尺子。
    #     原实现只做了 (1) 就返回动作，而调用方紧接着无条件 k += 1 —— 这段窗口
    #     **从未被验证**，于是可能产生"某格覆盖不成立却继续推进"的非法轨迹，
    #     并表现为验证器在 N 上非单调（N=3 成功而 N=4 失败）。
    p_from = pos[j] if pos[j] != IDLE else IDLE
    w_s = float(pb.w_sec(p_from, p_new)) if p_from != IDLE else float(pb.TO[p_new])
    k0 = int(pb.before(k, w_s))
    if not pb.union_ok(others, k0, k - 1):
        return None
    return dict(slot=j, k=k, t=float(cells[k]), from_=int(p_from), to=int(p_new),
                lead_cells=k - k0, span_cells=int(span), preposition=True,
                t_arrive=round(t_arr, 1))


def greedy(inst, ph, N=2, mode="air", cap_s=7233.0, topk=400, verbose=True,
           preposition=True, preposition_lead=400):
    pb = DN.PB(ph, grid=GRID, topk=topk, inst=inst, mode=mode)
    n = pb.n
    cells = np.asarray(ph["cells"], dtype=np.float64)
    pos = [IDLE] * N                 # 当前悬停点（-1 = 在 O01）
    arr = [0] * N                    # 到位格
    r0 = [0] * N                     # 本轮离开 O01 的格
    actions = []
    k = 0
    fail = None
    while k < n:
        need = pb.need[k]
        m = 0
        for p in pos:
            if p != IDLE:
                m |= int(pb.mask[k][p])
        cover_ok = (m == need)
        age_ok_now = age_ok(cells, pos, arr, r0, k, mode, cap_s)
        if cover_ok and age_ok_now:
            # 覆盖仍然成立：先考虑是否需要在触顶前**预置**一架接管
            if preposition:
                act = try_preposition(inst, ph, pb, cells, pos, arr, r0, k, need,
                                      mode, cap_s, n, lead_cells=preposition_lead)
                if act is not None:
                    actions.append(act)
                    pos[act["slot"]] = int(act["to"])
                    arr[act["slot"]] = k
                    r0[act["slot"]] = k
                    k += 1
                    continue
            k += 1
            continue
        # 选择换位 / 返航动作
        best = None
        for i in range(N):
            others = [pos[j] for j in range(N) if j != i]
            mo = 0
            for o in others:
                if o != IDLE:
                    mo |= int(pb.mask[k][o])
            rem = need & ~mo
            # 候选目标：覆盖剩余需求的点 + （若其余各架已能覆盖）返回 O01 换组件
            targets = list(pb.cand(k, rem))
            if rem == 0 and pos[i] != IDLE:
                targets = targets + [IDLE]
            for p_new in targets:
                if p_new == pos[i]:
                    continue
                w = min(pb.w_cells(pos[i], p_new), int(round(1500.0 / GRID)))
                k0 = max(0, k - w)
                if pos[i] != IDLE and k0 < arr[i]:
                    continue
                if any(pos[j] != IDLE and k0 < arr[j] for j in range(N) if j != i):
                    continue
                if not pb.union_ok(others, k0, k - 1):
                    continue
                # 换位后的覆盖检查
                m2 = 0
                for jj in range(N):
                    pj = p_new if jj == i else pos[jj]
                    if pj != IDLE:
                        m2 |= int(pb.mask[k][pj])
                if m2 != need:
                    continue
                # 年龄检查（Mode 1 换位后重新计时；Mode 2 仅在返航时重置）
                r_new = k if (mode == "base" or pos[i] == IDLE) else r0[i]
                if p_new == IDLE:
                    r_new = k
                if p_new != IDLE and cells[k] - cells[r_new] > cap_s:
                    continue
                if p_new == IDLE:
                    span = 10 ** 6          # 返航优先用于重置计时
                else:
                    span = int(pb.run_end[k][p_new]) - k + 1
                if span < 1:
                    continue
                urgent = 1 if (not age_ok_now) else 0
                key = (-urgent, -span, pb.w_cells(pos[i], p_new))
                if best is None or key < best[0]:
                    best = (key, i, p_new, k0, span, r_new)
        if best is None:
            fail = (k, float(cells[k]),
                    "无可行换位" if cover_ok is False else "在空/驻留超时且无可行换位")
            break
        _, i, p_new, k0, span, r_new = best
        actions.append(dict(slot=i, k=k, t=float(cells[k]), from_=pos[i], to=int(p_new),
                            lead_cells=k - k0, span_cells=int(span)))
        pos[i] = int(p_new)
        arr[i] = k
        r0[i] = r_new
        k += 1
    ok = (k >= n)
    return dict(ok=ok, n_actions=len(actions), fail=fail, actions=actions, pb=pb,
                cells=cells, reached_cell=k, n_cells=n)


def age_ok(cells, pos, arr, r0, k, mode, cap_s):
    for i, p in enumerate(pos):
        if p == IDLE:
            continue
        ref = arr[i] if mode == "base" else r0[i]
        if cells[k] - cells[ref] > cap_s:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=2)
    ap.add_argument("--mode", default="air", choices=["base", "air"])
    ap.add_argument("--topk", type=int, default=400)
    ap.add_argument("--no-preposition", action="store_true",
                    help="关闭「预防性换位」（默认开启）")
    a = ap.parse_args()
    t0 = time.time()
    inst, ph = build()
    rtype = inst.d["rtype"]
    cap = ((1 - rtype.rho) * rtype.e_use - 0.35) / (rtype.p_hover + rtype.p_comm) * 3600.0
    r = greedy(inst, ph, N=a.N, mode=a.mode, cap_s=cap, topk=a.topk,
               preposition=not a.no_preposition)
    print("\n=== 构造性贪心：N=%d，mode=%s，悬停候选上限 %d，在空上限 %.0f s ==="
          % (a.N, a.mode, a.topk, cap))
    print("  结果：%s；换位动作 %d 次；推进到第 %d/%d 格"
          % ("**可行**" if r["ok"] else "不可行", r["n_actions"], r["reached_cell"], r["n_cells"]))
    if r["fail"]:
        print("  首个失败：k=%d t=%.0f s —— %s" % (r["fail"][0], r["fail"][1], r["fail"][2]))
    # 从动作序列还原架次并做完整校验
    if r["ok"]:
        ss = actions_to_sorties(inst, ph, r["actions"], a.N, a.mode)
        bad = DN.check_timing(inst, ss, mode=a.mode)
        v = Q3.verify(inst, ph, [dict(t_link_done=s["t_link_done"], t_end=s["t_end"],
                                      lon=s["lon"], lat=s["lat"], hover_alt=s["hover_alt"])
                                 for s in ss], link=ph.get("link"))
        print("  架次 %d 个 | 时序冲突 %d | 未覆盖实例 %d/%d | 能耗 %.3f kWh | SOC 最低 %.1f%%"
              % (len(ss), len(bad), v["miss"], v["n"],
                 sum(s["e_total"] for s in ss), 100 * min(s["soc"] for s in ss)))
        print("  中继台数 %d，悬停点 %d 个" % (len({s['drone'] for s in ss}), len({s['j'] for s in ss})))
        out = dict(N=a.N, mode=a.mode, feasible=bool(v["miss"] == 0 and not bad),
                   sorties=len(ss), timing=len(bad), miss=int(v["miss"]),
                   energy=round(float(sum(s["e_total"] for s in ss)), 3),
                   soc_min=round(100 * min(s["soc"] for s in ss), 1),
                   actions=r["n_actions"])
    else:
        out = dict(N=a.N, mode=a.mode, feasible=False, fail_k=r["fail"][0],
                   fail_t=r["fail"][1], reason=r["fail"][2], actions=r["n_actions"])
    # 参数化文件名：N 与换位模式都要保留，否则后一次运行会覆盖前一次，
    # 导致"两种模式下 N=3 各是什么结果"无法同时进入结果文件与论文宏。
    out_name = "构造性贪心判定_N%d_%s.json" % (a.N, a.mode)
    out_path = os.path.join(OUT, out_name)
    json.dump(out, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 兼容旧路径：仍写一份不带参数的，供既有脚本读取
    json.dump(out, open(os.path.join(OUT, "构造性贪心判定.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写出：%s" % out_path)
    print("总耗时 %.0f s" % (time.time() - t0))


def actions_to_sorties(inst, ph, actions, N, mode):
    """把贪心产生的"换位动作"还原成中继架次表。"""
    rtype = inst.d["rtype"]
    dem = D.get_dem()
    cells = np.asarray(ph["cells"], dtype=np.float64)
    tb = {}
    for a in actions:
        tb.setdefault(a["slot"], []).append(a)
    # 每个 slot 的段序列由动作决定
    segs = {}
    for slot in range(N):
        lst = tb.get(slot, [])
        if not lst:
            continue
        segs.setdefault(slot, [])
        curp = lst[0]["from_"]
        if curp != IDLE and lst[0]["k"] > 0:
            segs[slot].append(dict(j=curp, k0=0, k1=lst[0]["k"] - 1))
        for i, a in enumerate(lst):
            if a["to"] == IDLE:
                continue                      # 返航段不产生悬停架次
            if i + 1 < len(lst):
                k1 = lst[i + 1]["k"] - lst[i + 1]["lead_cells"] - 1
            else:
                k1 = len(cells) - 1
            k1 = max(a["k"], min(int(k1), len(cells) - 1))
            segs[slot].append(dict(j=a["to"], k0=a["k"], k1=k1))
    out = []
    for slot, lst in segs.items():
        for sg in lst:
            j = sg["j"]
            if j == IDLE or sg["k1"] < sg["k0"]:
                continue
            lo, la, alt = ph["palette"][j]
            agl = float(alt) - float(dem.at(lo, la))
            rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
            t_arr, t_leave = float(cells[sg["k0"]]), float(cells[sg["k1"]])
            hover = max(0.0, t_leave - t_arr)
            e_h = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
            e_t = rf["e_fly"] + e_h
            soc = 1.0 - e_t / rtype.e_use
            out.append(dict(slot=slot, j=int(j), lon=lo, lat=la, ground=float(dem.at(lo, la)),
                            agl=agl, hover_alt=float(alt), t_link_done=t_arr, t_end=t_leave,
                            hover=hover, t_out=rf["t_out"], t_back=rf["t_back"],
                            e_fly=rf["e_fly"], e_hover=e_h, e_total=e_t, soc=soc,
                            chg=float(D.charge_time(soc, inst.d["rbatt"][1])),
                            t_depart=max(0.0, t_arr - rf["t_out"] - rtype.t_link)))
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]] if s["slot"] < len(inst.d["rfleet"]) \
            else "R%02d" % (s["slot"] + 1)
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out


if __name__ == "__main__":
    main()
