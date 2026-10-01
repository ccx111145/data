# -*- coding: utf-8 -*-
"""_check_uncoverable.py —— 核查「地形平移/峡谷族出现几何不可覆盖失联点」是否为
候选集窗口或悬停高度上限造成的假象。

判据：把候选窗口 pad 与悬停离地高度档位显著放大后，若不可覆盖实例数降为 0，
则原结论只是候选集规模的产物；若仍 >0，则是**真实几何不可覆盖**（该失联点在任何
允许的悬停高度与合理水平范围内都无视线），此时中继层无论配几架都不可行。
"""
from __future__ import annotations

import io
import time

import numpy as np

import comm as C
import dcore as D
import q2 as Q
import q3 as Q3
import terrain as T
import terrain_benchmark as TB

CASES = [(1.0, 0.0, (0, 0), "base"),
         (1.0, 0.0, (40, 40), "shift40"),
         (1.0, 1.0, (0, 0), "canyon1.0")]
CFG = [dict(pad=0.024, agl=(80.0, 160.0, 300.0), tag="默认(pad=0.024,AGL<=300)"),
       dict(pad=0.060, agl=(80.0, 160.0, 300.0), tag="大窗口(pad=0.060,AGL<=300)"),
       dict(pad=0.060, agl=(80.0, 160.0, 300.0, 500.0, 800.0), tag="大窗口+高悬停(AGL<=800)")]

_, spec = TB.load_transport_spec()
base = D.DEM()
for a, c, sh, name in CASES:
    dem = T.make_dem(alpha=a, cut=c, base=base, shift=sh)
    D.set_dem(dem)
    import q2 as _q2
    _q2._COVER[0] = None
    inst = Q.Instance()
    sorties, assign = TB.rebuild(spec)
    link = C.Link(inst, dem=dem, channel_model="observed")
    print("\n=== %s ===" % name)
    for cfg in CFG:
        t0 = time.time()
        ph = Q3.relay_phases(inst, sorties, assign, None, link=link, verbose=False,
                             min_phase_s=1400.0, max_phase_s=5400.0,
                             spacing=0.0035, pad=cfg["pad"], agl=cfg["agl"])
        ok = ph.get("ok")
        msg = ph.get("msg") if not ok else ""
        n_inst = (len(ph["T"]) if ok and ph.get("T") is not None else None)
        print("  %-34s ok=%-5s 实例=%s  %s (%.0f s)"
              % (cfg["tag"], ok, n_inst, (msg or "")[:44], time.time() - t0))
D.set_dem(None)
