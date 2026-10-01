# -*- coding: utf-8 -*-
"""_patch_mknum.py —— 给 make_numbers.py 增加两个「未派中继相位」专用宏：
  \\QthreeCompromiseOutagePhaseN / \\QthreeCompromiseOutagePhaseS
避免用「相位时长之和」（6380 s）去覆盖「中断并集」（5534 s，口径 C）这一语义错误。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "code", "make_numbers.py")
s = io.open(P, encoding="utf-8").read()
n = 0

old = '''               ["QthreeCompromiseSorties", "QthreeCompromiseCoverPct",
                "QthreeCompromiseUncoveredS", "QthreeCompromiseLongestS",
                "QthreeCompromiseCoverRate", "QthreeCompromiseEnergy",
                "QthreeCompromiseHover", "QthreeRelayHoverLike"]),'''
new = '''               ["QthreeCompromiseSorties", "QthreeCompromiseCoverPct",
                "QthreeCompromiseUncoveredS", "QthreeCompromiseLongestS",
                "QthreeCompromiseCoverRate", "QthreeCompromiseEnergy",
                "QthreeCompromiseHover", "QthreeRelayHoverLike",
                "QthreeCompromiseOutagePhaseN", "QthreeCompromiseOutagePhaseS"]),'''
assert s.count(old) == 1, ("order", s.count(old))
s = s.replace(old, new); n += 1

old2 = '''    "QthreeCompromiseUncoveredS": "5534",
    "QthreeCompromiseLongestS": "2446",'''
new2 = '''    "QthreeCompromiseUncoveredS": "5534",
    "QthreeCompromiseLongestS": "2446",
    "QthreeCompromiseOutagePhaseN": "3",
    "QthreeCompromiseOutagePhaseS": "6380",'''
assert s.count(old2) == 1, ("default", s.count(old2))
s = s.replace(old2, new2); n += 1

old3 = '''    "QthreeCompromiseUncoveredS": "① 2 架中继折中方案：未覆盖的中断并集 / s",'''
new3 = '''    "QthreeCompromiseUncoveredS": "① 2 架中继折中方案：未覆盖的中断并集 / s（口径 C，与 CommNoneUnionS 同义）",
    "QthreeCompromiseOutagePhaseN": "① 2 架中继折中方案：未派中继的相位数 / 个",
    "QthreeCompromiseOutagePhaseS": "① 2 架中继折中方案：未派中继的相位时长之和 / s（口径不同于中断并集）",'''
assert s.count(old3) == 1, ("note", s.count(old3))
s = s.replace(old3, new3); n += 1

io.open(P, "w", encoding="utf-8").write(s)
print("make_numbers.py 已更新 %d 处" % n)
