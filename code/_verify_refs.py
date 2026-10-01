# -*- coding: utf-8 -*-
"""
_verify_refs.py —— 用 Crossref 核实候选参考文献的元数据（标题/作者/期刊/年/卷/期/页/DOI），
并给出可直接粘进 `paper_en/refs.bib` 的 BibTeX 片段。

为什么需要它
------------
补引用时**不允许凭记忆写 DOI 或作者名单**——那与伪造数据同性质。本脚本对每条候选
按标题查 Crossref，只输出**权威返回**里的字段；同时会把"查到的标题与查询标题不一致"
的条目显式标出来，避免把 A 论文的 DOI 挂到 B 论文上（本轮就抓到并修掉了两处：
一条 DOI 指向完全不同的论文、一条作者名单张冠李戴）。

用法：
  python _verify_refs.py                 # 核实 CANDIDATES 里的全部条目
  python _verify_refs.py --bib           # 额外输出 BibTeX 片段
  python _verify_refs.py --out results/文献核实.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata

import requests

CANDIDATES = [
    # —— 车辆路径与启发式 ——
    "Algorithms for the vehicle routing and scheduling problems with time window constraints",
    "The vehicle routing problem",
    "Hybrid genetic search for the CVRP: Open-source implementation and SWAP* neighborhood",
    "Scheduling of vehicles from a central depot to a number of delivery points",
    # —— 无人机配送 ——
    "The vehicle routing problem with drones: Extended models and connections",
    "Optimization approaches for civil applications of unmanned aerial vehicles (UAVs) "
    "or aerial drones: A survey",
    "Models for drone delivery of medications and other healthcare items",
    # —— 应急物流 ——
    "Challenges of emergency logistics management",
    "Optimization models in emergency logistics: A literature review",
    # —— 中继与连通性 ——
    "Wireless communications with unmanned aerial vehicles: Opportunities and challenges",
    "A tutorial on UAVs for wireless networks: Applications, challenges, and open problems",
    "Energy-efficient UAV communication with trajectory optimization",
    "Throughput maximization for UAV-enabled mobile relaying systems",
    # —— 空对地传播与部署 ——
    "Optimal LAP altitude for maximum coverage",
    "Efficient deployment of multiple unmanned aerial vehicles for optimal wireless coverage",
    "Air-ground channel characterization for unmanned aircraft systems - Part II: "
    "Hilly and mountainous settings",
    # —— 组合优化 ——
    "An adaptive large neighborhood search heuristic for the pickup and delivery problem "
    "with time windows",
]

# 额外一批（本轮为把引用密度补到 Q1 常规水平而增补）
EXTRA = [
    "Joint trajectory and communication design for multi-UAV enabled wireless networks",
    "3D trajectory optimization in Rician fading for UAV-enabled data harvesting",
    "A survey on the vehicle routing problem with drones",
    "Drone-aided routing: A literature review",
    "Delivery by drone: An evaluation of unmanned aerial vehicle technology in reducing "
    "CO2 emissions in the delivery service industry",
    "The multiple traveling salesman problem with drones",
    "UAV-enabled wireless power transfer: Trajectory design and energy optimization",
    "Spectrum sharing for UAV communications",
    "Energy minimization in UAV-aided networks: A survey",
    "Post-disaster assessment routing problem",
    "Aerial base stations with opportunistic links for next generation emergency communications",
    "Multi-UAV enabled integrated sensing and communication",
    "Terrain-aware path planning for UAVs in mountainous environments",
    "An overview of the knife-edge diffraction theory",
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def query(title, rows=3):
    last = None
    for _ in range(3):
        try:
            r = requests.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": title, "rows": rows,
                        "select": "title,container-title,author,issued,volume,issue,"
                                  "page,DOI,type"},
                timeout=30,
                headers={"User-Agent": "ref-verify/1.0 (mailto:anonymous@example.org)"})
            r.raise_for_status()
            return r.json()["message"]["items"]
        except Exception as e:                                     # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def bibtex(rec, key):
    au = " and ".join(rec["authors_list"]) if rec.get("authors_list") else "Unknown"
    ttl = rec["title"].replace("&", r"\&")
    return ("@article{%s,\n  title   = {%s},\n  author  = {%s},\n  journal = {%s},\n"
            "  volume  = {%s},\n  number  = {%s},\n  pages   = {%s},\n  year    = {%s},\n"
            "  doi     = {%s}\n}"
            % (key, ttl, au, rec["journal"].replace("&amp;", r"\&"), rec["volume"],
               rec["issue"], rec["page"], rec["year"], rec["doi"]))


# ---------------------------------------------------------------------------
#  反查 `refs.bib` 里**已经存在**的条目（--audit-bib）
#
#  为什么必须补这一步：上面的 CANDIDATES/EXTRA 是"按标题正向查询"，只能核实
#  **准备新加**的条目。已经躺在 refs.bib 里的条目从不经过 API，于是三类错误
#  可以长期存活，直到审稿人点开 DOI：
#    * DOI 指向**另一篇论文**（bib 的题名与 Crossref 返回的题名完全不符）；
#    * DOI 是真的，但题名/作者是拼上去的（作者姓氏集合与 Crossref **零交集**）；
#    * 作者名单多列或漏列（例如把同一课题组的另一位作者串进条目）。
#  本函数把 refs.bib 的每条 DOI 反查 Crossref，比对 题名/年/卷/作者集合。
#  2026-09 用它抓出并随后修正了三处：deygout(DOI 指到 Yee 1966)、
#  relay5g(DOI 实为 Namuduri 的章节)、zengtraj(多列作者 Xu, J.)。
# ---------------------------------------------------------------------------

_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{")


def _parse_bib(path):
    """极简 BibTeX 解析：返回 [(key, {field: value}), ...]，跳过 % 注释行。"""
    text = "\n".join(l for l in open(path, encoding="utf-8").read().splitlines()
                     if not l.strip().startswith("%"))
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),", text):
        depth, i, start = 1, m.end(), m.end()
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body, j, fields = text[start:i - 1], 0, {}
        while True:
            fm = _BIB_FIELD_RE.search(body, j)
            if not fm:
                break
            d, k = 1, fm.end()
            while k < len(body) and d > 0:
                if body[k] == "{":
                    d += 1
                elif body[k] == "}":
                    d -= 1
                k += 1
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", body[fm.end():k - 1]).strip()
            j = k
        out.append((m.group(2).strip(), fields))
    return out


def _surname(name):
    """把 BibTeX/Crossref 的姓名归一到纯小写姓氏，去掉重音与 LaTeX 转义。"""
    n = name.split(",")[0]
    n = n.replace("\\", "").replace("{", "").replace("}", "")
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", n.lower())


def lookup_doi(doi):
    """按 DOI 直查 Crossref；404 返回 None。"""
    last = None
    for _ in range(3):
        try:
            r = requests.get("https://api.crossref.org/works/" + doi,
                             timeout=30,
                             headers={"User-Agent":
                                      "ref-verify/1.0 (mailto:anonymous@example.org)"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()["message"]
        except Exception as e:                                     # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def audit_bib(path, out=None):
    rows = _parse_bib(path)
    ok = bad = skipped = 0
    results = []
    for key, f in rows:
        doi = f.get("doi")
        if not doi:
            print("[SKIP] %-16s 无 DOI" % key)
            skipped += 1
            continue
        try:
            it = lookup_doi(doi)
        except Exception as e:                                     # noqa: BLE001
            print("[ERR ] %-16s %r" % (key, e))
            bad += 1
            continue
        if it is None:
            print("[404 ] %-16s DOI 无法解析：%s" % (key, doi))
            bad += 1
            continue
        ct = (it.get("title") or [""])[0]
        yr = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        # 印刷年与在线优先年常常不同（如 OR Spectrum 卷 43(1) 在线 2020、印刷 2021）：
        # 两者任一吻合即不算错，避免把通行做法误报成缺陷。
        yr_alt = [((it.get(k) or {}).get("date-parts") or [[None]])[0][0]
                  for k in ("published-print", "published-online")]
        # Crossref 对**机构作者**（dataset、标准、报告）只给 name 字段，
        # 不给 family/given。只读 family/given 会把这类条目一律误报成缺作者。
        def _cr_name(a):
            if a.get("family") or a.get("given"):
                return _surname("%s, %s" % (a.get("family", ""), a.get("given", "")))
            return _surname(a.get("name", ""))
        cr_au = [n for n in (_cr_name(a) for a in (it.get("author") or [])) if n]
        who = f.get("author") or f.get("editor") or ""
        truncated = "others" in who.lower()
        bib_au = [_surname(x) for x in who.split(" and ")
                  if x.strip() and x.strip().lower() != "others"]
        flags = []
        bt = norm(re.sub(r"\\[a-zA-Z]+|\{|\}|\$|_", "", f.get("title", "")))
        nt = norm(ct)
        if bt and bt[:45] not in nt and nt[:45] not in bt:
            flags.append("TITLE-MISMATCH")
        if f.get("year") and str(f["year"]) not in ([str(yr)] + [str(x) for x in yr_alt if x]):
            flags.append("YEAR(%s!=%s)" % (f["year"], yr))
        if f.get("volume") and str(f["volume"]) != str(it.get("volume") or ""):
            flags.append("VOLUME(%s!=%s)" % (f["volume"], it.get("volume")))
        # Crossref 没登记作者时（部分 @book 只登记编者）无法比对，跳过而非误报。
        miss = [x for x in bib_au if x not in cr_au] if cr_au else []
        extra = [] if (truncated or not cr_au) else [x for x in cr_au if x not in bib_au]
        if miss:
            flags.append("AUTHOR-NOT-IN-CROSSREF(%s)" % ",".join(miss))
        if extra:
            flags.append("MISSING-AUTHORS(%s)" % ",".join(extra))
        results.append(dict(key=key, doi=doi, flags=flags, crossref_title=ct,
                            bib_title=f.get("title", ""), year=yr))
        if flags:
            bad += 1
            print("[CHK ] %-16s %s" % (key, "; ".join(flags)))
            print("         bib      : %s" % f.get("title", "")[:88])
            print("         crossref : %s | %s"
                  % (ct[:88], (it.get("container-title") or [""])[0][:52]))
        else:
            ok += 1
            print("[OK  ] %-16s %s" % (key, ct[:68]))
        time.sleep(0.25)
    print("\n反查结果：%d 一致 / %d 有问题 / %d 无 DOI 可查（共 %d 条）"
          % (ok, bad, skipped, len(rows)))
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        json.dump(results, open(out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("已写出：%s" % out)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--bib", action="store_true")
    ap.add_argument("--extra", action="store_true", help="同时核实 EXTRA 一批")
    ap.add_argument("--audit-bib", action="store_true",
                    help="反查 refs.bib 中已有的全部 DOI + 作者名单（抓 DOI 张冠李戴/串作者）")
    ap.add_argument("--bib-path", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "paper_en", "refs.bib"))
    a = ap.parse_args()

    if a.audit_bib:
        n = audit_bib(a.bib_path,
                      out=a.out or os.path.join("results", "文献审计_反查.json"))
        raise SystemExit(1 if n else 0)

    todo = list(CANDIDATES) + (list(EXTRA) if a.extra else [])
    out = []
    for t in todo:
        try:
            items = query(t)
        except Exception as e:                                     # noqa: BLE001
            print("[ERR ] %s -> %r" % (t[:58], e))
            out.append(dict(query=t, status="ERROR", error=repr(e)))
            continue
        nt = norm(t)
        hit, exact = None, False
        for it in items:
            cand = norm((it.get("title") or [""])[0])
            if nt[:40] and nt[:40] in cand:
                hit, exact = it, True
                break
        if hit is None and items:
            hit = items[0]
        if hit is None:
            print("[NONE] %s" % t[:70])
            out.append(dict(query=t, status="NOT_FOUND"))
            continue
        yr = (hit.get("issued", {}).get("date-parts") or [[None]])[0][0]
        authors_list = ["%s, %s" % (x.get("family", ""), x.get("given", ""))
                        for x in (hit.get("author") or [])]
        rec = dict(query=t, status="OK" if exact else "TITLE_MISMATCH",
                   title=(hit.get("title") or [""])[0],
                   journal=(hit.get("container-title") or [""])[0],
                   year=yr, volume=hit.get("volume"), issue=hit.get("issue"),
                   page=hit.get("page"), doi=hit.get("DOI"), type=hit.get("type"),
                   authors="; ".join(authors_list),
                   authors_list=authors_list)
        out.append(rec)
        flag = "OK  " if exact else "MISM"
        print("[%s] %-55s | %s %s;%s(%s):%s | %s"
              % (flag, t[:55], (rec["journal"] or "")[:30], yr, rec["volume"],
                 rec["issue"], rec["page"], rec["doi"]))
        if not exact:
            print("        查到的标题是：%s（与查询不同，请人工确认）" % rec["title"][:90])
        time.sleep(0.35)

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n已写出：%s" % a.out)
    if a.bib:
        print("\n% ---- BibTeX（请人工确认 key 与相关性后再粘贴）----")
        for i, rec in enumerate(r for r in out if r["status"] == "OK"):
            print(bibtex(rec, "ref%02d" % (i + 1)))
            print()
    ok = sum(1 for r in out if r["status"] in ("OK",))
    print("核实结果：%d/%d 条标题精确命中 Crossref" % (ok, len(out)))


if __name__ == "__main__":
    main()
