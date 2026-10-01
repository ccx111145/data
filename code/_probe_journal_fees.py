# -*- coding: utf-8 -*-
"""_probe_journal_fees.py —— 抓候选期刊官方页，只挑"页数上限/费用"的原句。

避免凭印象说"某刊不收费"。抓不到就如实说抓不到，不猜。
"""
from __future__ import annotations

import re
import sys

import urllib.request

TARGETS = [
    ("TR-C (Elsevier)", "https://www.sciencedirect.com/journal/transportation-research-part-c-emerging-technologies/publish/guide-for-authors"),
    ("COR (Elsevier)", "https://www.sciencedirect.com/journal/computers-and-operations-research/publish/guide-for-authors"),
    ("RESS (Elsevier)", "https://www.sciencedirect.com/journal/reliability-engineering-and-system-safety/publish/guide-for-authors"),
    ("IEEE OJ-ITS", "https://ieee-itss.org/pub/oj-its/"),
    ("Drones (MDPI)", "https://www.mdpi.com/journal/drones/instructions"),
]

KEY = re.compile(r"page charge|page limit|overlength|excess page|article processing charge|"
                 r"\bAPC\b|no page|length of|maximum of|free of charge", re.I)


def main() -> int:
    for name, url in TARGETS:
        print("=== %s ===" % name)
        print("    %s" % url)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
        except Exception as e:                                       # noqa: BLE001
            print("    抓取失败：%s" % str(e)[:110])
            print()
            continue
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"&nbsp;?", " ", txt)
        txt = re.sub(r"\s+", " ", txt)
        hits = 0
        for m in KEY.finditer(txt):
            seg = txt[max(0, m.start() - 200):m.start() + 280].strip()
            print("    · %s" % seg[:430])
            hits += 1
            if hits >= 4:
                break
        if not hits:
            print("    （未在该页找到页数/费用相关原句）")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
