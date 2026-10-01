# -*- coding: utf-8 -*-
"""q3diag.py —— 把问题三的**诊断类结果文件**（DP 阻塞诊断、构造性贪心、跨度黑障、
结构诊断、换位模式对比）合并成一份 `results/Q3_诊断汇总.json`。

动机（对应审阅 #28）：此前论文数字依赖解析运行日志（_q3final.log 等），
日志一旦过期就会把旧物理模型下的数字写进论文。本脚本只读**结果文件**，
产出 make_numbers.py 可直接消费的权威汇总，从根上切断"过期日志污染论文"的路径。

用法：python q3diag.py
"""
from __future__ import annotations

import glob
import io
import json
import os
import re

import dcore as D

OUT = D.RESULTS
SUMMARY = os.path.join(OUT, "Q3_诊断汇总.json")


def rd(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:                                        # noqa: BLE001
        print("  ! 读取 %s 失败：%r" % (name, e))
        return None


def from_reason(txt):
    m = re.search(r"第\s*(\d+)\s*格（t=([\d.]+)\s*s）", txt or "")
    return (int(m.group(1)), float(m.group(2))) if m else (None, None)


def run_diagnostics(verbose=True):
    """先把产生诊断结果文件的脚本跑一遍，再合并。

    这些脚本（fail_diag / mode_compare / span_blackout / struct_diag / recompute_relay）
    不是主求解链路的必经步骤，但论文的稳健性数字全部来自它们，
    因此 `--run` 让"全新目录复现"也能得到同一套诊断结论。
    """
    import subprocess
    import sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHONIOENCODING"] = "utf-8"
    steps = [
        (["fail_diag.py", "--N", "2", "--mode", "base", "--topk", "12"], 1800),
        (["fail_diag.py", "--N", "2", "--mode", "base", "--topk", "24"], 1800),
        (["fail_diag.py", "--N", "2", "--mode", "base", "--topk", "40"], 1800),
        # 空中模式的 DP 状态空间显著更大，本机实测可超过 20 分钟；这里限时 600 s，
        # 超时则该诊断文件保持缺失，make_numbers.py 会在 paper/q3_gap_sources.txt 中
        # 把对应宏标为\u300c内置默认\u300d并告警，不会静默写错。
        (["fail_diag.py", "--N", "2", "--mode", "air", "--topk", "24"], 600),
        (["mode_compare.py"], 3600),
        (["span_blackout.py"], 3600),
        (["struct_diag.py"], 3600),
        (["recompute_relay.py"], 3600),
        (["greedy_relay.py", "--N", "3", "--mode", "base", "--topk", "400"], 3600),
    ]
    for cmd, to in steps:
        if verbose:
            print("  -> %s" % " ".join(cmd))
        try:
            r = subprocess.run([sys.executable] + cmd, cwd=HERE, env=env, timeout=to,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode:
                print("     ! 退出码 %d：%s" % (r.returncode,
                                            r.stdout.decode("utf-8", "replace").strip()[-300:]))
        except Exception as e:                                    # noqa: BLE001
            print("     ! 执行失败：%r" % (e,))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="合并问题三诊断类结果文件")
    ap.add_argument("--run", action="store_true",
                    help="先运行产生诊断文件的脚本（fail_diag/mode_compare/span_blackout/"
                         "struct_diag/recompute_relay/greedy_relay），再合并")
    a = ap.parse_args()
    if a.run:
        print("先运行诊断脚本…")
        run_diagnostics()

    out, src = {}, {}

    def put(key, val, source):
        if val in (None, ""):
            return
        out[key] = val
        src[key] = source

    # ---------------- ① DP 阻塞诊断（N=2，base，逐档候选规模） ----------------
    cells = {}
    for p in sorted(glob.glob(os.path.join(OUT, "DP阻塞诊断_N2_*.json"))):
        js = rd(os.path.basename(p))
        if not js:
            continue
        tag = "%s_topk%d" % (js.get("mode", "?"), int(js.get("topk", 0)))
        k, t = from_reason(js.get("reason"))
        if k is None and js.get("diag"):
            k, t = js["diag"].get("k"), js["diag"].get("t")
        cells[tag] = dict(k=k, t=t, feasible=bool(js.get("feasible")),
                          rej=dict((kk, vv) for kk, vv in (js.get("diag") or {}).items()
                                   if kk.startswith("rej_")))
        print("  · DP诊断 %s → k=%s t=%s" % (tag, k, t))
    if cells:
        put("dp_cells", cells, "DP阻塞诊断_N2_*.json")
        base12 = cells.get("base_topk12") or {}
        if base12.get("k") is not None:
            put("QthreeDpInfeasibleCell", int(base12["k"]), "DP阻塞诊断_N2_base_topk12.json")
            put("QthreeDpInfeasibleT", int(round(float(base12["t"]))),
                "DP阻塞诊断_N2_base_topk12.json")
        ks = [v["k"] for v in cells.values() if v.get("k") is not None]
        if ks:
            put("QthreeFailCellLow", int(min(ks)), "DP阻塞诊断_N2_*.json")
            put("QthreeFailCellHigh", int(max(ks)), "DP阻塞诊断_N2_*.json")

    # ---------------- ② 构造性贪心判定（当前文件只保留最后一次运行） ----------------
    g = rd("构造性贪心判定.json")
    if g:
        put("greedy_last", dict(N=g.get("N"), mode=g.get("mode"),
                                feasible=g.get("feasible"),
                                fail_k=g.get("fail_k"), fail_t=g.get("fail_t"),
                                reason=g.get("reason")),
            "构造性贪心判定.json")

    # ---------------- ③ 跨度—黑障不等式（★） ----------------
    sb = rd("跨度黑障不等式.json")
    if sb:
        put("span_blackout", sb, "跨度黑障不等式.json")
        bm = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 1") or {}
        am = ((sb.get("by_mode") or {}).get("全候选点对") or {}).get("Mode 2") or {}
        def _pct(blk):
            """优先用 n_ok/n 精确比值（避免 rate 先四舍五入再乘 100 的二次误差）。"""
            p50 = blk.get("p50") or {}
            n_ok, n = p50.get("n_ok"), p50.get("n")
            if n_ok is not None and n:
                return round(100.0 * n_ok / n, 1)
            return round(100.0 * float(p50.get("rate", 0.0)), 1)

        if bm.get("p50"):
            put("QthreeSpanBlackoutBasePct", _pct(bm), "跨度黑障不等式.json")
            put("QthreeDpBlackoutMedianS", int(round(bm["p50"]["w_s"])), "跨度黑障不等式.json")
        if am.get("p50"):
            put("QthreeSpanBlackoutAirPct", _pct(am), "跨度黑障不等式.json")
            put("QthreeDpBlackoutAirMedianS", int(round(am["p50"]["w_s"])), "跨度黑障不等式.json")
        if sb.get("fail"):
            put("QthreeFailBaseT", int(round(float(sb["fail"]["t"]))), "跨度黑障不等式.json")
        if bm.get("p50", {}).get("deficit_s") is not None:
            put("QthreeSpanDeficitBaseS", round(float(bm["p50"]["deficit_s"]), 1),
                "跨度黑障不等式.json")
        if am.get("p50", {}).get("deficit_s") is not None:
            put("QthreeSpanDeficitAirS", round(float(am["p50"]["deficit_s"]), 1),
                "跨度黑障不等式.json")
        wd = sb.get("w_base_dist_all") or {}
        if wd:
            put("QthreeDpBlackoutMinS", int(round(wd["min_s"])), "跨度黑障不等式.json")
            put("QthreeDpBlackoutMeanS", int(round(wd["mean_s"])), "跨度黑障不等式.json")
            put("QthreeDpBlackoutMaxS", int(round(wd["max_s"])), "跨度黑障不等式.json")
            put("QthreeDpBlackoutGePct", float(wd["ge1100_pct"]), "跨度黑障不等式.json")
            put("QthreeDpBlackoutPairs", int(wd["n"]), "跨度黑障不等式.json")
        # 换位模式对比表（论文 §7.7）用到的四个中位数与四个 (★) 成立率
        for key, field in (("QthreeWBaseMedS", "w_base_median_all_s"),
                           ("QthreeWAirMedS", "w_air_median_all_s"),
                           ("QthreeWBaseStrongS", "w_base_median_strong_s"),
                           ("QthreeWAirStrongS", "w_air_median_strong_s")):
            if sb.get(field) is not None:
                put(key, int(round(float(sb[field]))), "跨度黑障不等式.json")
        for nm, tag in (("全候选点对", ""), ("强点对", "Strong")):
            blk = (sb.get("by_mode") or {}).get(nm) or {}
            for lbl, sfx in (("Mode 1", "Base"), ("Mode 2", "Air")):
                blk2 = blk.get(lbl) or {}
                p50b = blk2.get("p50") or {}
                if p50b.get("rate") is not None or p50b.get("n_ok") is not None:
                    n_ok, nn = p50b.get("n_ok"), p50b.get("n")
                    val = (round(100.0 * n_ok / nn, 1) if (n_ok is not None and nn)
                           else round(100.0 * float(p50b["rate"]), 1))
                    put("QthreeStar%s%sPct" % (sfx, tag), val,
                        "跨度黑障不等式.json")

    # ---------------- ③b 物理修正后的重算结果（黑障 + (★) + 贪心，含 Mode 2） ----------------
    rc = rd("重算_物理修正后.json")
    if rc:
        put("recompute_physics", rc, "重算_物理修正后.json")

        def put_gap(key, val, source):
            """只在权威来源（跨度黑障不等式.json）没有给出该键时才补位，
            避免两个脚本的小数级差异让论文数字随执行顺序漂移。"""
            if val in (None, "") or key in out:
                return
            put(key, val, source)

        bk = rc.get("blackout") or {}
        if bk.get("base_med") is not None:
            put_gap("QthreeDpBlackoutMedianS", int(round(bk["base_med"])), "重算_物理修正后.json")
        if bk.get("air_med") is not None:
            put_gap("QthreeDpBlackoutAirMedianS", int(round(bk["air_med"])), "重算_物理修正后.json")
        star = rc.get("star") or {}
        if star.get("base_rate") is not None:
            put_gap("QthreeSpanBlackoutBasePct", round(100.0 * float(star["base_rate"]), 1),
                    "重算_物理修正后.json")
        if star.get("air_rate") is not None:
            put_gap("QthreeSpanBlackoutAirPct", round(100.0 * float(star["air_rate"]), 1),
                    "重算_物理修正后.json")
        gr = (rc.get("greedy") or {}).get("N2_air") or {}
        if gr.get("fail"):
            put("QthreeFailAirT", int(round(float(gr["fail"]["t"]))), "重算_物理修正后.json")
        grb = (rc.get("greedy") or {}).get("N2_base") or {}
        if grb.get("fail"):
            put("QthreeFailBaseT", int(round(float(grb["fail"]["t"]))), "重算_物理修正后.json")
        if rc.get("hover_cap_s") is not None:
            put("QthreeHoverCapS", round(float(rc["hover_cap_s"]), 1), "重算_物理修正后.json")

    # ---------------- ④ 结构诊断 ----------------
    sd = rd("结构诊断.json")
    if sd:
        put("struct_diag", sd, "结构诊断.json")
        bh = sd.get("blackout") or {}
        if bh.get("base_median_s") is not None:
            put("QthreeBlackoutBaseMedianS", int(round(bh["base_median_s"])), "结构诊断.json")
        if bh.get("air_median_s") is not None:
            put("QthreeBlackoutAirMedianS", int(round(bh["air_median_s"])), "结构诊断.json")

    # ---------------- ⑤ 换位模式对比 ----------------
    mc = rd("换位模式对比.json")
    if mc:
        put("mode_compare", mc, "换位模式对比.json")
        put("QthreeHoverCapS", round(float(mc.get("hover_cap_s", 0.0)), 1),
            "换位模式对比.json")

    # ---------------- ⑥ 最优增配/贪心可行解（N=3） ----------------
    s3 = rd("Q3_方案汇总.json")
    if s3:
        put("q3_summary", s3, "Q3_方案汇总.json")

    with io.open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(dict(generated=__import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                       note="问题三诊断类结果文件的合并汇总；make_numbers.py 的权威来源之一",
                       values=out, sources=src), f, ensure_ascii=False, indent=1, default=float)
    print("\n已写出：%s（%d 个条目）" % (SUMMARY, len(out)))
    return SUMMARY


if __name__ == "__main__":
    main()
