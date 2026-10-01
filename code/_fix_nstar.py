# -*- coding: utf-8 -*-
"""_fix_nstar.py —— 把「P.526 口径下 N* 大于 3」更正为**确切值 4**。

上一轮只扫到 N ≤ 3 就下了「>3」的结论；本轮把判定器扩到 N = 4 后发现
P.526 两种口径在 **N = 4** 时**可行**（7 架次、0 未覆盖），且候选预算
200/400/600 三档一致。因此正确表述是「最小台数由 3 升到 4」，
而不是「大于 3」。需要同步：
  * 英文稿 Table 1 的两列（改为引用宏，避免再次写死）
  * 英文稿摘要与 Discussion 的措辞
  * `results/SCI增补实验报告.md`（由其生成脚本改）
  * `交付包说明.md`（由其生成脚本改）
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs, label):
    p = os.path.join(BASE, path)
    if not os.path.exists(p):
        print("[SKIP] %s 不存在" % path)
        return
    s = io.open(p, encoding="utf-8").read()
    n = 0
    for a, b in pairs:
        c = s.count(a)
        if c == 0:
            print("  [MISS] %s :: %s" % (label, a[:60]))
            continue
        s = s.replace(a, b)
        n += c
    io.open(p, "w", encoding="utf-8").write(s)
    print("[OK] %s（%d 处）" % (label, n))


# ---------------- 英文稿 ----------------
patch("paper_en/main.tex", [
    (r"Minimum fleet $N^{*}$ & $\ENchObsNStar$ & $>3$ & $>3$\\",
     r"Minimum fleet $N^{*}$ & $\ENchObsNStar$ & $\ENchAltNStar$ & $\ENchAltUbNStar$\\"),
    (r"""the reported minimum fleet
size is not invariant across channel conventions.""",
     r"""the reported minimum fleet
size is not invariant across channel conventions: it moves from
$\ENchObsNStar$ (constant penalty) to $\ENchAltNStar$ (physically stricter
knife-edge diffraction)."""),
    (r"""and moves the reported minimum fleet
size from $\ENchObsNStar$ to more than three. Fleet-size statements are
therefore statements about a channel convention and must be reported with it.""",
     r"""and moves the reported minimum fleet
size from $\ENchObsNStar$ to $\ENchAltNStar$. The nominal augmentation is one
vehicle under either convention, but the base differs, so fleet-size statements
are statements about a channel convention and must be reported with it."""),
    (r"""Replacing the constant occlusion penalty with ITU-R P.~526 knife-edge
diffraction changes both the demand ($\ENchReqDelta\%$) and the supply
($\ENchCandDelta\%$ of usable hover points), and moves the reported minimum fleet
size from $\ENchObsNStar$ to more than three.""",
     r"""Replacing the constant occlusion penalty with ITU-R P.~526 knife-edge
diffraction changes both the demand ($\ENchReqDelta\%$) and the supply
($\ENchCandDelta\%$ of usable hover points), and raises the minimum fleet size
from $\ENchObsNStar$ to $\ENchAltNStar$."""),
    (r"""Modes & M2 $(\star)$ rate & $93.1\%$ (vs $72.0\%$ for M1)\\""",
     r"""Modes & M2 $(\star)$ rate & $93.1\%$ (vs $72.0\%$ for M1)\\
Relay & channel model & $N^{*}=\ENchObsNStar$ (constant) vs $\ENchAltNStar$ (P.526)\\"""),
], "paper_en/main.tex")

# ---------------- 中文报告生成器 ----------------
patch("code/make_sci_report.py", [
    (r'    A("| N=3 是否可行 | %s | %s | %s |"',
     r'    A("| N=3 是否可行 | %s | %s | %s |"'),
    (r'''    A("1. 固定损耗口径**系统性低估通信需求**：P.526 下失联需求实例增加，"
      "同时回传可用悬停点大幅减少——因为中继悬停在 80–300 m 离地高度、"
      "回传至 20 m 高的网关，同样受绕射限制。")
    A("2. **最小中继台数由 3 变为大于 3**：即「增配 1 架」这一管理结论"
      "**只在附件口径下成立**；物理上更严格的绕射模型要求更多台数。")''',
     r'''    A("1. 固定损耗口径**系统性低估通信需求**：P.526 下失联需求实例增加，"
      "同时回传可用悬停点大幅减少——因为中继悬停在 80–300 m 离地高度、"
      "回传至 20 m 高的网关，同样受绕射限制。")
    A("2. **最小中继台数由 3 升到 4**（单刃峰与多刃峰上界给出相同结论）："
      "即「相对库存（2 架）增配 1 架」这一相对结论在两个口径下都成立，"
      "但**基数不同**（3 対 4），因此任何台数结论都必须连同信道口径一起报告。")'''),
], "code/make_sci_report.py")

# ---------------- 英文 README / 交付包说明生成器 ----------------
patch("code/_write_readme.py", [
    (r"**最小中继台数由 3 变为大于 3**；结论在候选预算 200/400/600 三档下一致",
     r"**最小中继台数由 3 升到 4**；结论在候选预算 200/400/600 三档下一致"),
    (r"阻塞率同为 44%~45% 的三个地形分别给出 N* = 3 / 3 / 大于 4",
     r"阻塞率同为 44%~45% 的三个地形分别给出 N* = 3 / 3 / 大于 4（该处于上一行同口径）"),
], "code/_write_readme.py")
