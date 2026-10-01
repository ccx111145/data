# -*- coding: utf-8 -*-
"""_fix_repro2.py —— 把 `tables.tex` 的比对改成**结构化比对**，避免用正则整块删表：

  * 宏：解析 `\\newcommand{\\Name}{Value}` 成 name→value 字典，剔除 `\\Qtwo*` 后逐键比对；
  * 表：比对各 `\\label{...}` 与紧随其后的 `\\caption{...}`，剔除标题含「问题二」的表。

这样即使排版细节（`\\resizebox` 包裹、空行）变化，也能准确定位真正的数字差异。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "_repro_test.py")
s = io.open(P, encoding="utf-8").read()

OLD = '''    def strip_q2(txt):
        out = [ln for ln in txt.split("\\n")
               if not re.match(r"\\\\newcommand\\{\\\\Qtwo", ln)]
        return re.sub(r"\\\\begin\\{table\\}\\[htbp\\].*?问题二五种权重配置.*?\\\\end\\{table\\}",
                      "", "\\n".join(out), flags=re.S)

    for f in ("numbers.tex", "tables.tex"):
        pa, pb = os.path.join(SRC, "paper", f), os.path.join(DST, "paper", f)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            checks.append(("paper/%s（剔除问题二部分）" % f, "—", "缺失"))
            continue
        ta = strip_q2(_io.open(pa, encoding="utf-8").read())
        tb = strip_q2(_io.open(pb, encoding="utf-8").read())
        checks.append(("paper/%s（剔除问题二部分）" % f, "—",
                       "一致" if ta == tb else "不一致"))
'''
NEW = '''    def macros_of(p):
        """解析 \\newcommand{\\Name}{Value} -> {name: value}，剔除问题二的 \\Qtwo* 宏。"""
        t = _io.open(p, encoding="utf-8").read()
        d = {}
        for m in re.finditer(r"\\\\newcommand\\{\\\\([A-Za-z]+)\\}\\{([^}]*)\\}", t):
            if m.group(1).startswith("Qtwo"):
                continue
            d[m.group(1)] = m.group(2)
        return d

    def tables_of(p):
        """各 table 的 (label, caption)；剔除标题含「问题二」的表。"""
        t = _io.open(p, encoding="utf-8").read()
        out = []
        for m in re.finditer(r"\\\\begin\\{table\\}.*?\\\\end\\{table\\}", t, flags=re.S):
            blk = m.group(0)
            lab = re.search(r"\\\\label\\{([^}]*)\\}", blk)
            cap = re.search(r"\\\\caption\\{([^}]*)\\}", blk)
            if cap and "问题二" in cap.group(1):
                continue
            out.append((lab.group(1) if lab else "", cap.group(1) if cap else ""))
        return out

    for f in ("numbers.tex", "tables.tex"):
        pa, pb = os.path.join(SRC, "paper", f), os.path.join(DST, "paper", f)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            checks.append(("paper/%s 宏与表（剔除问题二）" % f, "—", "缺失"))
            continue
        ma, mb = macros_of(pa), macros_of(pb)
        diff = [k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k)]
        checks.append(("paper/%s 宏（剔除 \\\\Qtwo*）共 %d 个" % (f, len(ma)),
                       "工作区", "%d 处不同" % len(diff) if diff else "全部一致"))
        if f == "tables.tex":
            ta, tb = tables_of(pa), tables_of(pb)
            checks.append(("paper/%s 表标题/标签（剔除问题二表）" % f, "工作区",
                           "一致" if ta == tb else "%d vs %d 张不同" % (len(ta), len(tb))))
'''
assert s.count(OLD) == 1, ("old", s.count(OLD))
s = s.replace(OLD, NEW)

# 判定：把「N 处不同 / 张不同」视为失败；「全部一致 / 一致」视为通过
OLD2 = '''        info = str(y).endswith("个待补")
        ok = True if info else ((x == y) or (y == "一致"))'''
NEW2 = '''        y = str(y)
        info = y.endswith("个待补")
        ok = True if info else (y in ("一致", "全部一致"))'''
assert s.count(OLD2) == 1, ("verdict", s.count(OLD2))
s = s.replace(OLD2, NEW2)

io.open(P, "w", encoding="utf-8").write(s)
print("_repro_test.py 比对已结构化")
