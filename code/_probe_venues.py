# -*- coding: utf-8 -*-
"""_probe_venues.py —— 候选期刊的官方页：页数限制 / 费用 / 定位。

只带回官方页面上真实出现的原句；抓不到就如实说抓不到。
"""
from __future__ import annotations

import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}

TARGETS = [
    ("TR-C (Elsevier)", "https://www.sciencedirect.com/journal/transportation-research-part-c-emerging-technologies"),
    ("COR (Elsevier)", "https://www.sciencedirect.com/journal/computers-and-operations-research"),
    ("RESS (Elsevier)", "https://www.sciencedirect.com/journal/reliability-engineering-and-system-safety"),
    ("Networks (Wiley)", "https://onlinelibrary.wiley.com/journal/10970037"),
    ("JOITS (Springer)", "https://link.springer.com/journal/13177"),
    ("IJITSR (Springer)", "https://link.springer.com/journal/13177"),
]

KEY = re.compile(r"page charge|page limit|overlength|excess page|no page|"
                 r"article processing charge|\bAPC\b|open access|"
                 r"subscription|hybrid|free to publish", re.I)

FEE = re.compile(r"\$\s?\d{3,4}|EUR\s?\d{3,4}|USD\s?\d{3,4}|€\s?\d{3,4}", re.I)


def grab(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    except Exception as e:                                           # noqa: BLE001
        print("    抓取失败：%s" % str(e)[:100])
        return None
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&#8217;", "'")
          .replace("&amp;", "&").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", t)


def main() -> int:
    for name, url in TARGETS:
        print("=== %s ===" % name)
        print("    %s" % url)
        t = grab(url)
        if not t:
            print()
            continue
        shown = 0
        for m in KEY.finditer(t):
            seg = " ".join(t[max(0, m.start() - 190):m.start() + 250].split())
            if FEE.search(seg) or re.search(r"no page|page limit|overlength|excess page", seg, re.I):
                print("    · %s" % seg[:400])
                shown += 1
                if shown >= 3:
                    break
        if not shown:
            print("    （未见页数限制/费用原句）")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
