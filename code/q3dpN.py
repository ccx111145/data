# -*- coding: utf-8 -*-
"""
q3dpN.py —— N 架中继悬停位置状态 DP（q3dp3 的一般化）

状态 = ((p_1, s_1), ..., (p_N, s_N))：每架中继的悬停位置与**到达该位置的时刻（格）**
可行性：N 个位置的覆盖位掩码并集 ⊇ 该格全部失联实例
转移：每次只换一架 i
   * 其余 N-1 架的并集必须在黑障窗口 [k-w, k] 内覆盖全部需求；
   * 被换的第 i 架必须已到位：s_i <= k - w；其余各架也须 s_j <= k - w。
代价：换位/出动次数（= 中继架次数）
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

import dcore as D

IDLE = -1
INF = float("inf")


class StateSpaceOverflow(RuntimeError):
    """精确模式下的状态空间超出内存护栏（max_states）。

    抛出它表示"精确判定未跑完"，此时的"不可行"只对已搜索到的部分成立，
    调用方必须如实记录，不得当作候选集上的不可行性结论。
    """


class PB:
    def __init__(self, ph, grid=10.0, topk=12, inst=None, lookahead=140, mode="base"):
        self.cells = ph["cells"]
        self.mode = mode
        self.inst = inst
        self.alone = ph["alone"]
        self.cov = ph["cov"]
        self.groups = ph["groups"]
        self.palette = ph["palette"]
        self.n = len(self.cells)
        self.P = self.alone.shape[1]
        self.grid = grid
        self.topk = topk
        self.lookahead = int(lookahead)
        self.mask = []
        for g in self.groups:
            sub = self.cov[g]
            m = np.zeros(self.P, dtype=np.int64)
            for i in range(sub.shape[0]):
                m |= (sub[i].astype(np.int64) << i)
            self.mask.append(m)
        self.need = [(1 << int(self.mask[k].max()).bit_length()) - 1 for k in range(self.n)]
        self.run_end = np.full((self.n, self.P), -1, dtype=np.int32)
        self.starts_at: Dict[int, List[int]] = {}
        for j in range(self.P):
            idx = np.nonzero(self.alone[:, j])[0]
            if len(idx) == 0:
                continue
            brk = np.nonzero(np.diff(idx) > 1)[0]
            for seg in np.split(idx, brk + 1):
                self.run_end[seg[0]:seg[-1] + 1, j] = seg[-1]
                self.starts_at.setdefault(int(seg[0]), []).append(int(j))
        self._cand = {}
        self._prepos = {}
        # **完备候选集**：任何"有用"的悬停点必然在某个格上能单独覆盖该格全部需求
        # （N=2 时显然；N≥3 时若某点参与联合覆盖，则它至少要多担一个实例，
        #   即在该格上单独覆盖那一部分——仍属本集合）。故可行性判定只需在本集合上做。
        self.useful = sorted({j for lst in self.starts_at.values() for j in lst})
        self.TO = np.zeros(self.P); self.TB = np.zeros(self.P)
        if inst is not None:
            dem = D.get_dem()
            for j in range(self.P):
                lo, la, alt = self.palette[j]
                agl = float(alt) - float(dem.at(lo, la))
                rf = D.relay_flight(inst.d["rtype"], inst.nodes, lo, la, max(0.0, agl))
                self.TO[j] = rf["t_out"]; self.TB[j] = rf["t_back"]
        self.t_turn = inst.d["rtype"].t_turn if inst is not None else 300.0
        self.t_link = inst.d["rtype"].t_link if inst is not None else 30.0
        self.mask_cache = {}
        self._pair_pref = {}
        self._check_cache = {}
        self._transit = {}
        self._transit_e = {}
        self.cells_t = np.asarray(self.cells, dtype=np.float64)

    def pair_pref(self, a, b):
        """点对 (a,b) 的"并集是否覆盖该格全部需求"前缀和（惰性构建）。"""
        key = (a, b) if a <= b else (b, a)
        hit = self._pair_pref.get(key)
        if hit is not None:
            return hit
        aa, bb = key
        need = np.array(self.need, dtype=np.int64)
        ma = np.array([int(self.mask[k][aa]) if aa >= 0 else 0 for k in range(self.n)], dtype=np.int64)
        mb = np.array([int(self.mask[k][bb]) if bb >= 0 else 0 for k in range(self.n)], dtype=np.int64)
        bad = ((ma | mb) != need).astype(np.int32)
        pref = np.zeros(self.n + 1, dtype=np.int32)
        pref[1:] = np.cumsum(bad)
        self._pair_pref[key] = pref
        if len(self._pair_pref) > 20000:
            self._pair_pref.clear()
            self._pair_pref[key] = pref
        return pref

    def pair_ok(self, a, b, k0, k1):
        k0 = max(0, k0); k1 = min(self.n - 1, k1)
        if k1 < k0:
            return True
        p = self.pair_pref(a, b)
        return p[k1 + 1] - p[k0] == 0

    def w_sec(self, j_old, j_new):
        """由 j_old 换位到 j_new 的黑障窗口（**秒**，逐点对精确计算，**不做任何截断**）。
        Mode 1（base）：返航 O01 + 架次周转 + 再出动；
        Mode 2（air） ：两点间直接转场（爬升 + 巡航 + 下降）+ 建链。
        j_old == IDLE 表示从 O01 首次出动（两种模式相同）。"""
        if j_old == IDLE:
            return self.TO[j_new] + self.t_link
        if self.mode == "air":
            return self.transit_s(j_old, j_new) + self.t_link
        return self.TB[j_old] + self.t_turn + self.TO[j_new] + self.t_link

    def w_cells(self, j_old, j_new):
        """[兼容保留] 仅用于打印统计；判定一律用 w_sec + before。"""
        return max(1, int(math.ceil(self.w_sec(j_old, j_new) / self.grid)))

    def before(self, k, w_sec):
        """返回满足 cells[j] <= cells[k] - w_sec 的最大格号 j（-1 表示窗口完全落在任务期之前）。
        **按真实时间戳计算**——需求格是稀疏的，绝不假设相邻格等间隔 10 s。"""
        if w_sec <= 0:
            return k
        t0 = float(self.cells_t[k]) - float(w_sec)
        return int(np.searchsorted(self.cells_t, t0, side="right")) - 1

    def transit_s(self, j1, j2):
        """Mode 2 的空中直接转场时间（惰性缓存）。"""
        key = (j1, j2)
        hit = self._transit.get(key)
        if hit is not None:
            return hit
        rt = self.inst.d["rtype"] if self.inst is not None else None
        if rt is None:
            return 0.0
        p1 = tuple(float(x) for x in self.palette[j1])
        p2 = tuple(float(x) for x in self.palette[j2])
        t, e, c = D.relay_transit(rt, self.inst.nodes, p1, p2)
        self._transit[key] = t
        self._transit_e[key] = e
        if len(self._transit) > 400000:
            self._transit.clear(); self._transit_e.clear()
        return t

    def union_ok(self, js, k0, k1):
        """js 中位置（非 IDLE）的并集能否在 [k0,k1] 内覆盖全部需求。空区间视为满足。"""
        k0 = max(0, k0); k1 = min(self.n - 1, k1)
        if k1 < k0:
            return True                      # 黑障窗口落在任务期之外
        js = [j for j in js if j != IDLE]
        if not js:
            return False
        if len(js) == 1:
            p = np.zeros(self.n + 1, dtype=np.int32)
            p[1:] = np.cumsum(~self.alone[:, js[0]])
            return p[k1 + 1] - p[k0] == 0
        if len(js) == 2:
            return self.pair_ok(js[0], js[1], k0, k1)
        for k in range(k0, k1 + 1):
            m = 0
            row = self.mask[k]
            for j in js:
                m |= int(row[j])
                if m == self.need[k]:
                    break
            if m != self.need[k]:
                return False
        return True

    def cand(self, k, need_mask):
        """覆盖 need_mask 的候选点。
        topk > 0：按"从 k 起可驻留时长"降序取前 topk（启发式，**可能丢失可行解**）；
        topk = 0：返回**全部**满足条件的点（在完备候选集 self.useful 上），用于精确判定。"""
        key = (k, int(need_mask))
        hit = self._cand.get(key)
        if hit is not None:
            return hit
        if need_mask == 0:
            # 预置位：另一台已覆盖全部需求时，本台可换到任何"将来有用"的点位
            out = list(self.useful) if self.topk <= 0 else self._preposition(k)
        else:
            m = self.mask[k]
            sel = np.nonzero((m & need_mask) == need_mask)[0]
            if len(sel) == 0:
                out = []
            elif self.topk <= 0:
                out = [int(x) for x in sel]
            else:
                order = np.argsort(-self.run_end[k, sel])
                out = [int(sel[i]) for i in order[:self.topk]]
        self._cand[key] = out
        return out

    def _preposition(self, k):
        hit = self._prepos.get(k)
        if hit is not None:
            return hit
        ends = {}
        for kk in range(k, min(self.n, k + self.lookahead + 1)):
            for j in self.starts_at.get(kk, ()):
                e = int(self.run_end[kk, j])
                if e > ends.get(j, -1):
                    ends[j] = e
        for j in np.nonzero(self.alone[k])[0]:
            e = int(self.run_end[k, j])
            if e > ends.get(int(j), -1):
                ends[int(j)] = e
        out = [j for j, _ in sorted(ends.items(), key=lambda kv: (-kv[1], kv[0]))[:self.topk]]
        self._prepos[k] = out
        return out


def solve(ph, N=2, grid=10.0, topk=12, keep_slack=3, max_states=40000, inst=None, verbose=True,
          per_key=2, Wmax_s=None, max_hover_s=None, mode="base", exact=False):
    """
    mode = "base"：Mode 1，基地返航换电——每次换位必须回 O01（含架次周转 τ_turn）；
    mode = "air" ：Mode 2，空中点对点直接转场——省去返航与周转，黑障仅含爬升/巡航/下降。

    状态 = 每架中继 (p, s, r)：悬停位置 / 到达该位置的时刻 / 本轮**离开 O01 的时刻**
      · 驻留上限按 s 判定（Mode 1：一次架次 = 一段驻留）
      · Mode 2 还需按 r 判定（连续在空中，电池容量约束作用于整段在空时长）
    max_hover_s：单次驻留（Mode 1）或在空时长（Mode 2）上限，超过则不合法，必须回 O01 换组件。
    """
    pb = PB(ph, grid=grid, topk=topk, inst=inst, mode=mode)
    n = pb.n
    # Wmax_s 已废弃：黑障窗口按逐点对精确秒数计算，不做任何截断
    cells_t = np.asarray(ph["cells"], dtype=np.float64)
    Hsec = float(max_hover_s) if max_hover_s else None

    def cov_of(state, k):
        m = 0
        row = pb.mask[k]
        for (p, _s, _r) in state:
            if p != IDLE:
                m |= int(row[p])
        return m

    def feasible_age(st, k):
        if Hsec is None:
            return True
        for (p, s, r) in st:
            if p == IDLE:
                continue
            if mode == "base":
                if cells_t[k] - cells_t[s] > Hsec:
                    return False
            else:
                if cells_t[k] - cells_t[r] > Hsec:
                    return False
        return True

    # 首格
    dp = {}
    need = pb.need[0]
    for j in pb.cand(0, need):
        dp[tuple((j if i == 0 else IDLE, 0, 0) for i in range(N))] = 1
    if not dp:
        m = pb.mask[0]
        for a in np.nonzero(m)[0]:
            rem = need & ~int(m[a])
            for b in pb.cand(0, rem):
                if int(b) == int(a):
                    continue
                dp[tuple(([int(a), int(b)][i] if i < 2 else IDLE, 0, 0) for i in range(N))] = \
                    2 if N >= 2 else 1
    if not dp:
        return None, "首格无可行配置", pb, None
    parents = [dict()]

    for k in range(1, n):
        need = pb.need[k]
        cur, par = {}, {}
        diag = dict(k=k, t=float(pb.cells[k]), n_state=len(dp), cand_empty=0,
                    rej_pnew_eq=0, rej_old_arrival=0, rej_other_arrival=0,
                    rej_union=0, rej_age=0, accepted=0)
        for st, c in dp.items():
            if not feasible_age(st, k):
                diag["rej_age"] += 1
                continue
            if cov_of(st, k) == need:
                if cur.get(st, INF) > c:
                    cur[st] = c; par[st] = st
            for i in range(N):
                p_old, s_old, r_old = st[i]
                others = [st[j][0] for j in range(N) if j != i]
                if not others or all(o == IDLE for o in others):
                    continue
                mo = 0
                for o in others:
                    if o != IDLE:
                        mo |= int(pb.mask[k][o])
                rem = need & ~mo
                tg = pb.cand(k, rem)
                if not tg:
                    diag["cand_empty"] += 1
                for p_new in tg:
                    if p_new == p_old:
                        diag["rej_pnew_eq"] += 1
                        continue
                    # 黑障窗口：逐点对精确、**不截断**；边界格按真实时间戳定位
                    wsec = pb.w_sec(p_old, p_new)
                    kb = pb.before(k, wsec)          # cells[kb] <= cells[k] - wsec
                    if kb < s_old:
                        diag["rej_old_arrival"] += 1
                        continue
                    if any(kb < st[j][1] for j in range(N) if j != i):
                        diag["rej_other_arrival"] += 1
                        continue
                    if not pb.union_ok(others, kb + 1, k - 1):
                        diag["rej_union"] += 1
                        continue
                    r_new = k if (mode == "base" or p_old == IDLE) else r_old
                    lst = list(st)
                    lst[i] = (p_new, k, r_new)
                    st2 = tuple(lst)
                    nc = c + 1
                    diag["accepted"] += 1
                    if cur.get(st2, INF) > nc:
                        cur[st2] = nc; par[st2] = st
        if not cur:
            return None, "第 %d 格（t=%.0f s）无可行状态" % (k, pb.cells[k]), pb, diag
        if exact:
            # 精确模式：不做任何按代价/数量的状态删除，保证不丢可行解。
            # max_states 在此仅作为**内存护栏**：一旦某格状态数超限就抛出
            # StateSpaceOverflow，由调用方记录"精确判定未跑完"的事实，
            # 绝不静默剪枝（静默剪枝会让"不可行"结论失去意义）。
            if max_states and len(cur) > max_states:
                raise StateSpaceOverflow(
                    "cell %d: |S_k| = %d > max_states = %d" % (k, len(cur), max_states))
            dp = cur
            parents.append(par)
            if verbose and k % 200 == 0:
                print("    cell %4d/%d 状态 %6d（精确模式，无剪枝）" % (k, n, len(dp)))
            continue
        mn = min(cur.values())
        cur = {s: v for s, v in cur.items() if v <= mn + keep_slack}
        bykey = {}
        for s, v in cur.items():
            key = tuple(sorted(p for p, _s, _r in s))
            bykey.setdefault(key, []).append((s, v))
        cur2, par2 = {}, {}
        for key, lst in bykey.items():
            lst.sort(key=lambda sv: (sv[1], sum(x[1] for x in sv[0]),
                                     sum(x[2] for x in sv[0])))
            for s, v in lst[:per_key]:
                cur2[s] = v; par2[s] = par[s]
        if max_states and len(cur2) > max_states:
            items = sorted(cur2.items(), key=lambda kv: kv[1])[:max_states]
            cur2 = dict(items)
            par2 = {s: v for s, v in par2.items() if s in cur2}
        dp = cur2
        parents.append(par2)
        if verbose and k % 200 == 0:
            print("    cell %4d/%d 状态 %5d 最优代价 %d" % (k, n, len(dp), mn))

    end = min(dp, key=lambda s: dp[s])
    seq = [None] * n
    st = end
    for k in range(n - 1, -1, -1):
        seq[k] = st
        if k == 0:
            break
        st = parents[k].get(st)
        if st is None:
            return None, "回溯失败 k=%d" % k, pb, None
    return seq, dp[end], pb, None


def to_sorties(inst, seq, pb, N=2, grid=10.0, mode="base"):
    """把位置序列转成中继架次表。

    两种模式对"一个架次"的定义不同：
      · Mode 1（base）：一次架次 = 一个悬停点的一次驻留（换位必须回 O01，
        因此相邻但不同点位的两段属于两个架次）；
      · Mode 2（air） ：一次架次 = 从 O01 出动到返回 O01 的**一整段在空时间**，
        期间可在多个悬停点之间直接转场。
    必须保留 IDLE 段——中继回 O01 换组件再回到同一点位时，序列是「点位 → IDLE → 同一点位」。
    """
    rtype = inst.d["rtype"]
    dem = D.get_dem()
    cells = pb.cells
    out = []
    for slot in range(N):
        segs = []
        cur = None
        for k, st in enumerate(seq):
            p = st[slot][0]
            if cur is not None and cur["j"] == p:
                cur["k1"] = k
                continue
            if cur is not None:
                segs.append(cur)
            cur = dict(j=p, k0=k, k1=k)
        if cur is not None:
            segs.append(cur)
        # 计算每段的到位/离站时刻
        for idx, sg in enumerate(segs):
            sg["t_arr"] = float(cells[sg["k0"]])
            nxt = segs[idx + 1] if idx + 1 < len(segs) else None
            if nxt is None or nxt["j"] == IDLE:
                sg["t_leave"] = float(cells[sg["k1"]])
            else:
                w = pb.w_cells(sg["j"], nxt["j"])
                sg["t_leave"] = max(sg["t_arr"],
                                    float(cells[min(nxt["k0"], pb.n - 1)]) - w * grid)
        # 按模式归并
        if mode == "air":
            stints, cur_st = [], []
            for sg in segs:
                if sg["j"] == IDLE:
                    if cur_st:
                        stints.append(cur_st); cur_st = []
                    continue
                cur_st.append(sg)
            if cur_st:
                stints.append(cur_st)
        else:
            stints = [[sg] for sg in segs if sg["j"] != IDLE]
        for st_i, stint in enumerate(stints):
            first, last = stint[0], stint[-1]
            j0 = first["j"]
            lo0, la0, alt0 = pb.palette[j0]
            agl0 = float(alt0) - float(dem.at(lo0, la0))
            rf0 = D.relay_flight(rtype, inst.nodes, lo0, la0, max(0.0, agl0))
            e_fly = rf0["e_fly"]
            if mode == "air":
                # 段间空中直接转场能耗
                for a, b in zip(stint[:-1], stint[1:]):
                    _, e_tr, _ = D.relay_transit(rtype, inst.nodes,
                                                 tuple(float(x) for x in pb.palette[a["j"]]),
                                                 tuple(float(x) for x in pb.palette[b["j"]]))
                    e_fly += e_tr
            else:
                # 每一段都是一次独立的往返架次
                pass
            hover = sum(max(0.0, sg["t_leave"] - sg["t_arr"]) for sg in stint)
            e_h = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
            e_t = e_fly + e_h
            soc = 1.0 - e_t / rtype.e_use
            t_arr = first["t_arr"]
            t_leave = last["t_leave"]
            out.append(dict(slot=slot, j=int(j0), lon=lo0, lat=la0,
                            ground=float(dem.at(lo0, la0)), agl=agl0, hover_alt=float(alt0),
                            t_link_done=t_arr, t_end=t_leave, hover=hover,
                            t_out=rf0["t_out"] if mode == "base" or st_i == 0 else 0.0,
                            t_back=rf0["t_back"] if mode == "base" else 0.0,
                            e_fly=e_fly, e_hover=e_h, e_total=e_t, soc=soc,
                            chg=float(D.charge_time(soc, inst.d["rbatt"][1])),
                            t_depart=max(0.0, t_arr - rf0["t_out"] - rtype.t_link),
                            mode=mode, n_pos=len(stint),
                            positions=[(float(pb.palette[sg["j"]][0]), float(pb.palette[sg["j"]][1]),
                                        float(pb.palette[sg["j"]][2])) for sg in stint]))
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]] if s["slot"] < len(inst.d["rfleet"]) \
            else "R%02d" % (s["slot"] + 1)
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out


def check_timing(inst, sorties, mode="base"):
    """Mode 1：同一条中继的架次占用 [depart, 返航+周转) 不得重叠；
    Mode 2：同一条中继的在空区间 [出动, 返航) 不得重叠。"""
    rtype = inst.d["rtype"]
    bad = []
    slots = sorted({s["slot"] for s in sorties})
    for slot in slots:
        seq = sorted([s for s in sorties if s["slot"] == slot], key=lambda s: s["t_link_done"])
        free = 0.0
        for s in seq:
            if s["t_depart"] < free - 1e-6:
                bad.append(dict(slot=slot, t=s["t_link_done"], need=round(s["t_depart"], 1),
                                free=round(free, 1), gap=round(free - s["t_depart"], 1)))
            tail = rtype.t_turn if mode == "base" else 0.0
            free = max(free, s["t_end"] + s["t_back"] + tail)
    return bad
