# -*- coding: utf-8 -*-
"""
q3dp3.py —— 双中继悬停位置状态 DP（可用资源驱动的正确模型）

状态：cell k 上两架中继各自的悬停位置 (a, b)，a/b ∈ 悬停候选点 ∪ {IDLE}
可行性：a 与 b 的覆盖位掩码并集 ⊇ 该 cell 全部失联实例
转移（每步至多一台换位）：
  * 保持：两架都不动（代价 0）
  * 换第一台 a→a'：第二台 b 必须在换位窗口 [k-T, k] 内**单独**覆盖全部需求
    （b 换位、a 保持同理）；换位或出动计 1 个中继架次
目标：最少中继架次数 → 等价于最少换位/出动次数

与前两版的关键差别
------------------
* 不再预设"相位"，而是直接以两架的位置为状态，避免"配对相无法接力"的死结；
* 候选点从**当前状态出发**按需生成（覆盖剩余需求 + 可驻留最久者优先），
  状态空间可控。
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

import dcore as D

IDLE = -1
INF = float("inf")


class Problem:
    def __init__(self, ph, grid=10.0, topk=14, inst=None, lookahead=140):
        self.cells = ph["cells"]
        self.lookahead = int(lookahead)
        self.alone = ph["alone"]                 # (n_cell, n_point)
        self.cov = ph["cov"]                     # (n_inst, n_point)
        self.groups = ph["groups"]
        self.palette = ph["palette"]
        self.n = len(self.cells)
        self.P = self.alone.shape[1]
        self.grid = grid
        self.topk = topk
        # 每格的实例覆盖位掩码
        self.mask = []
        for g in self.groups:
            sub = self.cov[g]
            m = np.zeros(self.P, dtype=np.int64)
            for i in range(sub.shape[0]):
                m |= (sub[i].astype(np.int64) << i)
            self.mask.append(m)
        self.full = [int(self.mask[k].max()).bit_length() for k in range(self.n)]
        self.need = [(1 << self.full[k]) - 1 for k in range(self.n)]
        # alone 前缀和
        self.pref = np.zeros((self.P, self.n + 1), dtype=np.int32)
        for j in range(self.P):
            self.pref[j, 1:] = np.cumsum(~self.alone[:, j])
        # 每个点在各格的"可驻留到哪一格"（用于候选点排序）与"从哪一格开始可用"
        self.run_end = np.full((self.n, self.P), -1, dtype=np.int32)
        self.run_start = np.full((self.n, self.P), self.n, dtype=np.int32)
        self.starts_at: Dict[int, List[int]] = {}
        for j in range(self.P):
            col = self.alone[:, j]
            idx = np.nonzero(col)[0]
            if len(idx) == 0:
                continue
            brk = np.nonzero(np.diff(idx) > 1)[0]
            for seg in np.split(idx, brk + 1):
                self.run_end[seg[0]:seg[-1] + 1, j] = seg[-1]
                self.run_start[seg[0]:seg[-1] + 1, j] = seg[0]
                self.starts_at.setdefault(int(seg[0]), []).append(int(j))
        self._prepos: Dict[int, List[int]] = {}
        self._cand: Dict[Tuple[int, int], List[int]] = {}
        # 各候选点的往返飞行时间（用于逐点对精确计算换位黑障窗口）
        self.TO = np.zeros(self.P)
        self.TB = np.zeros(self.P)
        if inst is not None:
            dem = D.get_dem()
            for j in range(self.P):
                lo, la, alt = self.palette[j]
                agl = float(alt) - float(dem.at(lo, la))
                rf = D.relay_flight(inst.d["rtype"], inst.nodes, lo, la, max(0.0, agl))
                self.TO[j] = rf["t_out"]
                self.TB[j] = rf["t_back"]
        self.t_turn = inst.d["rtype"].t_turn if inst is not None else 300.0
        self.t_link = inst.d["rtype"].t_link if inst is not None else 30.0

    # -- 工具 ---------------------------------------------------------------
    def alone_ok(self, j, k0, k1):
        k0 = max(0, k0); k1 = min(self.n - 1, k1)
        if k1 < k0:
            return True
        return self.pref[j, k1 + 1] - self.pref[j, k0] == 0

    def mask_of(self, j, k):
        return 0 if j == IDLE else int(self.mask[k][j])

    def w_cells(self, j_old, j_new):
        """由 j_old 换位到 j_new 的黑障窗口（格数）。j_old = IDLE 表示从 O01 直接出动。"""
        if j_old == IDLE:
            sec = self.TO[j_new] + self.t_link
        else:
            sec = self.TB[j_old] + self.t_turn + self.TO[j_new] + self.t_link
        return max(1, int(math.ceil(sec / self.grid)))

    def cand(self, k, need_mask):
        """覆盖 need_mask 的全部候选点，按"从 k 起可驻留时长"降序取前 topk。
        need_mask = 0（另一台已覆盖全部需求）时改为"预置位候选"：
        允许换到**当前用不上、但即将需要**的点位。"""
        key = (k, int(need_mask))
        hit = self._cand.get(key)
        if hit is not None:
            return hit
        if need_mask == 0:
            out = self._preposition(k)
            self._cand[key] = out
            return out
        m = self.mask[k]
        sel = np.nonzero((m & need_mask) == need_mask)[0]
        if len(sel) == 0:
            self._cand[key] = []
            return []
        order = np.argsort(-self.run_end[k, sel])
        out = [int(sel[i]) for i in order[:self.topk]]
        self._cand[key] = out
        return out

    def _preposition(self, k):
        """预置位候选：在 [k, k+lookahead] 内即将开始可用的点位，按可驻留时长降序。"""
        hit = self._prepos.get(k)
        if hit is not None:
            return hit
        LA = self.lookahead
        ends = {}
        for kk in range(k, min(self.n, k + LA + 1)):
            for j in self.starts_at.get(kk, ()):
                e = int(self.run_end[kk, j])
                if e > ends.get(j, -1):
                    ends[j] = e
        # 当前已可用的强点也纳入
        col = self.alone[k]
        for j in np.nonzero(col)[0]:
            e = int(self.run_end[k, j])
            if e > ends.get(int(j), -1):
                ends[int(j)] = e
        out = [j for j, _ in sorted(ends.items(), key=lambda kv: (-kv[1], kv[0]))[:self.topk]]
        self._prepos[k] = out
        return out


def solve(ph, T_move=1300.0, grid=10.0, topk=14, keep_slack=3, max_states=20000, verbose=True,
          inst=None, per_pair=3):
    """
    状态 = (a, b, sa, sb)：两台中继的悬停位置，以及各自**到达该位置的时刻（格）**。
    换位约束：
      * 第二台 b 必须在黑障窗口 [k-w, k] 内单独覆盖全部需求；
      * 被换的第一台必须已经到位：sa <= k-w（同样要求 sb <= k-w，保证第二台确在站）。
    返回 (seq, cost, prob)；seq[k] = (a, b)。
    """
    pb = Problem(ph, grid=grid, topk=topk, inst=inst)
    n = pb.n
    Wmax = max(1, int(round(T_move / grid)))

    def base_cost(st):
        return (1 if st[0] >= 0 else 0) + (1 if st[1] >= 0 else 0)

    # 首格
    dp = {}
    need = pb.need[0]
    for j in pb.cand(0, need):
        dp[(j, IDLE, 0, 0)] = 1
        dp[(IDLE, j, 0, 0)] = 1
    if not dp:
        m = pb.mask[0]
        for a in np.nonzero(m)[0]:
            rem = need & ~int(m[a])
            for b in pb.cand(0, rem):
                if int(b) != int(a):
                    dp[(int(a), int(b), 0, 0)] = 2
    if not dp:
        return None, "首格无可行配置", pb
    parents = [dict()]

    for k in range(1, n):
        need = pb.need[k]
        cur, par = {}, {}
        for (a, b, sa, sb), c in dp.items():
            ma, mb = pb.mask_of(a, k), pb.mask_of(b, k)
            if (ma | mb) == need:
                st = (a, b, sa, sb)
                if cur.get(st, INF) > c:
                    cur[st] = c
                    par[st] = st
            # 换第一台
            if b != IDLE and sb <= k:
                rem = need & ~mb
                for a2 in pb.cand(k, rem):
                    if a2 == a:
                        continue
                    w = min(pb.w_cells(a, a2), Wmax)
                    if k - w < sa or k - w < sb:
                        continue
                    if not pb.alone_ok(b, k - w, k):
                        continue
                    st = (a2, b, k, sb)
                    nc = c + 1
                    if cur.get(st, INF) > nc:
                        cur[st] = nc
                        par[st] = (a, b, sa, sb)
            # 换第二台
            if a != IDLE and sa <= k:
                rem = need & ~ma
                for b2 in pb.cand(k, rem):
                    if b2 == b:
                        continue
                    w = min(pb.w_cells(b, b2), Wmax)
                    if k - w < sb or k - w < sa:
                        continue
                    if not pb.alone_ok(a, k - w, k):
                        continue
                    st = (a, b2, sa, k)
                    nc = c + 1
                    if cur.get(st, INF) > nc:
                        cur[st] = nc
                        par[st] = (a, b, sa, sb)
        if not cur:
            return None, "第 %d 格（t=%.0f s）无可行状态" % (k, pb.cells[k]), pb
        mn = min(cur.values())
        cur = {s: v for s, v in cur.items() if v <= mn + keep_slack}
        # 支配剪枝：同一 (a,b) 只保留 sa+sb 最小的若干条
        byab = {}
        for s, v in cur.items():
            byab.setdefault((s[0], s[1]), []).append((s, v))
        cur2, par2 = {}, {}
        for ab, lst in byab.items():
            lst.sort(key=lambda sv: (sv[1], sv[0][2] + sv[0][3]))
            for s, v in lst[:per_pair]:
                cur2[s] = v
                par2[s] = par[s]
        if len(cur2) > max_states:
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
        seq[k] = (st[0], st[1])
        if k == 0:
            break
        st = parents[k].get(st)
        if st is None:
            return None, "回溯失败 k=%d" % k, pb
    return seq, dp[end], pb


def to_sorties(inst, seq, pb, T_move=1300.0, grid=10.0):
    """把位置序列转成中继架次表。

    关键：某架在位置 p 的驻留区间不是"状态连续段"，而是
        [到位时刻, 下一次换位的**离站时刻**]
    其中离站时刻 = 下一段到位时刻 - 换位黑障窗口 w(p→p')。
    DP 已保证在该黑障窗口内另一架可独立保障，因此这样重建与 DP 的可行性判定一致。
    """
    rtype = inst.d["rtype"]
    dem = D.get_dem()
    cells = pb.cells
    palette = pb.palette
    out = []
    for slot in (0, 1):
        # 找出该架的"状态段"
        segs = []
        cur = None
        for k, st in enumerate(seq):
            j = st[slot]
            if cur is not None and cur["j"] == j:
                cur["k1"] = k
                continue
            if cur is not None:
                segs.append(cur)
            cur = dict(j=j, k0=k, k1=k)
        if cur is not None:
            segs.append(cur)
        segs = [s for s in segs if s["j"] != IDLE]
        for idx, sg in enumerate(segs):
            j = sg["j"]
            t_arrive = float(cells[sg["k0"]])
            if idx + 1 < len(segs):
                jn = segs[idx + 1]["j"]
                k_next = segs[idx + 1]["k0"]
                w = pb.w_cells(j, jn)
                t_leave = max(t_arrive, float(cells[min(k_next, pb.n - 1)]) - w * grid)
            else:
                t_leave = float(cells[sg["k1"]])
            lo, la, alt = palette[j]
            agl = float(alt) - float(dem.at(lo, la))
            rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
            hover = max(0.0, t_leave - t_arrive)
            e_hover = (rtype.p_hover + rtype.p_comm) * hover / 3600.0
            e_tot = rf["e_fly"] + e_hover
            soc = 1.0 - e_tot / rtype.e_use
            out.append(dict(slot=slot, j=int(j), lon=lo, lat=la, ground=float(dem.at(lo, la)),
                            agl=agl, hover_alt=float(alt), t_link_done=t_arrive, t_end=t_leave,
                            hover=hover, t_out=rf["t_out"], t_back=rf["t_back"],
                            e_fly=rf["e_fly"], e_hover=e_hover, e_total=e_tot, soc=soc,
                            chg=float(D.charge_time(soc, inst.d["rbatt"][1])),
                            t_depart=max(0.0, t_arrive - rf["t_out"] - rtype.t_link)))
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]]
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out


def check_timing(inst, sorties):
    """同一条中继的架次占用 [depart, back+周转) 不得重叠。"""
    rtype = inst.d["rtype"]
    bad = []
    for slot in (0, 1):
        seq = sorted([s for s in sorties if s["slot"] == slot], key=lambda s: s["t_link_done"])
        free = 0.0
        for s in seq:
            dep = s["t_depart"]
            if dep < free - 1e-6:
                bad.append(dict(slot=slot, t=s["t_link_done"], need=round(dep, 1),
                                free=round(free, 1), gap=round(free - dep, 1)))
            free = max(free, s["t_end"] + s["t_back"] + rtype.t_turn)
    return bad


# ---------------------------------------------------------------------------
# 电池容量：单架次悬停过长必须回 O01 换能源组件
# ---------------------------------------------------------------------------
def max_hover(inst, e_fly=0.25):
    rt = inst.d["rtype"]
    return max(0.0, ((1 - rt.rho) * rt.e_use - e_fly) / (rt.p_hover + rt.p_comm) * 3600.0)


def split_long_sorties(inst, seq, pb, sorties, T_move=1300.0, grid=10.0, verbose=True):
    """把悬停时长超过能源组件容量的架次在"另一台可独立保障"的窗口处拆分
    （表现为回 O01 换组件后再出动），从而满足返航电量下限。"""
    rtype = inst.d["rtype"]
    H = max_hover(inst)
    W = int(round(T_move / grid))
    out = []
    for s in sorties:
        lim_cells = int(H / grid)
        k0 = int(np.searchsorted(pb.cells, s["t_link_done"]))
        k1 = int(np.searchsorted(pb.cells, s["t_end"]))
        if (k1 - k0) <= lim_cells:
            out.append(dict(s))
            continue
        # 在 [k0+lim*0.6, k1-lim*0.4] 中找另一台可独立覆盖 [ks-W, ks+W] 的拆分点
        other = 1 - s["slot"]
        best = None
        for ks in range(k0 + max(1, int(lim_cells * 0.6)),
                        min(k1 - 1, k0 + lim_cells) + 1):
            if ks - W < 0 or ks + W >= pb.n:
                continue
            jo = int(seq[ks][other])
            if jo == IDLE:
                continue
            if pb.alone_ok(jo, ks - W, ks + W):
                best = ks
                break
        if best is None:
            out.append(dict(s))
            if verbose:
                print("    ! 架次 #%d 悬停 %.0f s 超限且找不到可拆分窗口" % (s["rid"], s["hover"]))
            continue
        ks = best
        a = dict(s); b = dict(s)
        a["t_end"] = float(pb.cells[ks - 1])
        b["t_link_done"] = float(pb.cells[ks])
        out.extend([a, b])
        if verbose:
            print("    · 架次 #%d 在 t=%.0f s 拆分为换电架次（悬停 %.0f + %.0f s）"
                  % (s["rid"], pb.cells[ks], a["t_end"] - a["t_link_done"],
                     b["t_end"] - b["t_link_done"]))
    # 重算能耗/SOC/时刻
    dem = D.get_dem()
    for s in out:
        lo, la, alt = pb.palette[s["j"]]
        agl = float(alt) - float(dem.at(lo, la))
        rf = D.relay_flight(rtype, inst.nodes, lo, la, max(0.0, agl))
        s["hover"] = max(0.0, s["t_end"] - s["t_link_done"])
        s["e_hover"] = (rtype.p_hover + rtype.p_comm) * s["hover"] / 3600.0
        s["e_total"] = rf["e_fly"] + s["e_hover"]
        s["soc"] = 1.0 - s["e_total"] / rtype.e_use
        s["chg"] = float(D.charge_time(s["soc"], inst.d["rbatt"][1]))
        s["t_out"], s["t_back"], s["e_fly"] = rf["t_out"], rf["t_back"], rf["e_fly"]
        s["t_depart"] = max(0.0, s["t_link_done"] - rf["t_out"] - rtype.t_link)
        s.pop("rid", None)
    out.sort(key=lambda s: (s["t_link_done"], s["slot"]))
    for i, s in enumerate(out, 1):
        s["rid"] = i
        s["drone"] = inst.d["rfleet"][s["slot"]]
        s["comp"] = "R-E%d" % (((i - 1) % inst.d["rbatt"][0]) + 1)
    return out
