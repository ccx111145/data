# -*- coding: utf-8 -*-
"""rdiag2.py —— 诊断相位覆盖结构：每相时长、点位、合并失败原因。"""
from __future__ import annotations
import time
import numpy as np
import dcore as D
import q2 as Q
import q3 as Q3
import solution_io as SIO


def main():
    inst = Q.Instance()
    sol = SIO.load()
    # 用 solution.json 的运输方案重建 Sortie 对象
    sorties, assign = [], {}
    for i, r in enumerate(sol["transport"]):
        areas = [a for a in r["route"][1:-1]]
        load = {a: list(r["boxes"][a]) for a in areas}
        offs = {a: float(r["deliver"][b]) - float(r["start"]) for a in areas for b in r["boxes"][a]}
        s = Q.Sortie(g=r["type"], areas=areas, load=load, dur=float(r["end"]) - float(r["start"]),
                     E=float(r["energy"]), offs=offs)
        sorties.append(s)
        assign[i] = dict(start=float(r["start"]), end=float(r["end"]), drone=r["drone"],
                         battery=r["battery"], chg=float(r.get("chg", 0.0)),
                         soc=float(r.get("soc", 1.0)))
    print("运输架次 %d" % len(sorties))
    ph = Q3.relay_phases(inst, sorties, assign, Q._cover(inst).palette, verbose=True,
                         min_phase_s=1400.0, max_phase_s=5400.0)
    cells = ph["cells"]; alone = ph["alone"]; Pn = alone.shape[1]
    print("\n相结构：")
    for i, (k0, k1, js) in enumerate(ph["intervals"]):
        dur = (k1 - k0 + 1) * 10.0
        print("  相%02d  %7.0f–%7.0f s  时长%6.0f s  点位%s  %s"
              % (i + 1, cells[k0], cells[k1], dur, js, "偏短" if dur < 1400 else ""))
    # 逐相检查：是否存在单点覆盖"相邻两相并集"
    pref = np.zeros((Pn, len(cells) + 1), dtype=np.int32)
    for j in range(Pn):
        pref[j, 1:] = np.cumsum(~alone[:, j])

    def single_cover(k0, k1):
        return np.nonzero(pref[:, k1 + 1] - pref[:, k0] == 0)[0]

    iv = ph["intervals"]
    print("\n相邻相合并可行性：")
    for i in range(len(iv) - 1):
        k0, k1 = iv[i][0], iv[i + 1][1]
        sc = single_cover(k0, k1)
        uni = tuple(sorted(set(iv[i][2]) | set(iv[i + 1][2])))
        print("  相%02d+%02d 并集时长%6.0f s | 单点可覆盖: %s (%d 个点) | 点集并集大小 %d %s"
              % (i + 1, i + 2, (k1 - k0 + 1) * 10.0, "是" if len(sc) else "否", len(sc),
                 len(uni), "" if len(uni) <= 2 else "→ 超 2 点，无法合并"))
    return ph


if __name__ == "__main__":
    t0 = time.time()
    main()
    print("\n耗时 %.0f s" % (time.time() - t0))
