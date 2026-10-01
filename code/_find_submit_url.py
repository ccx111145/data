# -*- coding: utf-8 -*-
"""_find_submit_url.py —— 从 IEEE ITSS 官方 T-ITS 页面抓出"投稿入口"链接。

为什么值得单独抓：投稿网址我不能凭记忆写。这里直接读官方页面正文，
把所有像投稿入口/作者指南的链接列出来，只把**页面上真实出现**的链接带回来。
"""
from __future__ import annotations

import re
import sys
import urllib.request

URL = "https://ieee-itss.org/pub/t-its/"
PAT = re.compile(
    r"""href=["']([^"']+)["'][^>]*>(.{0,90}?)<""", re.S | re.I)


def main() -> int:
    req = urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    print("页面长度 %d 字节" % len(html))
    print()
    seen = set()
    for m in PAT.finditer(html):
        url = m.group(1).strip()
        txt = re.sub(r"<[^>]+>", "", m.group(2))
        txt = re.sub(r"\s+", " ", txt).strip()
        blob = (url + " " + txt).lower()
        if not re.search(r"submi|author|portal|manuscript|atypon|scholarone|guideline", blob):
            continue
        if url in seen:
            continue
        seen.add(url)
        print("  %-76s | %s" % (url[:76], txt[:52]))
    if not seen:
        print("  （页面上没有匹配到投稿类链接，可能需要登录或由 JS 渲染）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
