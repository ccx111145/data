# -*- coding: utf-8 -*-
"""_patch_chanmd.py —— 给 channel_compare.py 加 `--md-only`（由已有 JSON 重写 Markdown）。"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(BASE, "code", "channel_compare.py")
s = io.open(p, encoding="utf-8").read()

i = s.find('    # ---------------- Markdown ----------------')
j = s.find('    print("\\n已写出：')
assert i > 0 and j > i, (i, j)
s = s[:i] + ('    mp = write_md(payload, models, "", "", a.topks)\n'
             '    jp = os.path.join(OUT, "信道模型对比.json")\n') + s[j:]

s = s.replace('    ap.add_argument("--no-palette", action="store_true",',
              '    ap.add_argument("--md-only", action="store_true",\n'
              '                    help="不重算，仅由已有的 信道模型对比.json 重写 Markdown 报告")\n'
              '    ap.add_argument("--no-palette", action="store_true",')

s = s.replace('''    models = [m.strip() for m in a.models.split(",") if m.strip()]

    t0 = time.time()''',
'''    models = [m.strip() for m in a.models.split(",") if m.strip()]

    if a.md_only:
        with io.open(os.path.join(OUT, "信道模型对比.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
        models = list(payload["results"].keys())
        mp = write_md(payload, models, "", "", a.topks)
        print("已由现有 JSON 重写：%s" % mp)
        return

    t0 = time.time()''')

io.open(p, "w", encoding="utf-8").write(s)
print("channel_compare.py 已加 --md-only")
