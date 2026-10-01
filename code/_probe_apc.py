# -*- coding: utf-8 -*-
"""_probe_apc.py —— 找 IEEE OJ-ITS / IEEE 开放获取的 APC 金额原句。找不到就说找不到。"""
from __future__ import annotations

import re
import sys
import urllib.request

URLS = [
    "https://ieee-itss.org/pub/oj-its/",
    "https://open.ieee.org/for-authors/",
    "https://open.ieee.org/",
]


def main() -> int:
    for url in URLS:
        print("=== %s ===" % url)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
        except Exception as e:                                       # noqa: BLE001
            print("    抓取失败：%s" % str(e)[:100])
            continue
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = txt.replace("&nbsp;", " ").replace("&#8217;", "'")
        txt = re.sub(r"\s+", " ", txt)
        found = False
        for m in re.finditer(r"\$\s?\d{3,4}(?:\.\d{2})?", txt):
            seg = txt[max(0, m.start() - 230):m.start() + 200]
            if re.search(r"APC|processing charge|USD|open access", seg, re.I):
                print("    · %s" % " ".join(seg.split())[:400])
                found = True
                break
        if not found:
            # 退一步：找提到 APC 的句子，即使没写金额
            m = re.search(r"[^.]*APC[^.]*\.", txt)
            if m:
                print("    （提 APC 但未见金额）%s" % " ".join(m.group(0).split())[:300])
            else:
                print("    （未找到 APC 金额）")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
