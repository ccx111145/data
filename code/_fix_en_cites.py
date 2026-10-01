# -*- coding: utf-8 -*-
"""_fix_en_cites.py —— 给英文稿补 `\\cite{}` 并把参考文献改为可编译的 bibtex 流程。

替换掉旧的占位条目引用，改为引用 `refs.bib` 中可核实的公开文献；
同时在 `main.tex` 里插入 LaTeX → BibTeX → LaTeX ×2 的编译说明注释。
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(BASE, "paper_en", "main.tex")
s = io.open(TEX, encoding="utf-8").read()
n = 0


def rep(old, new, tag):
    global s, n
    c = s.count(old)
    if c != 1:
        print("[MISS] %s（%d）" % (tag, c))
        return
    s = s.replace(old, new)
    n += 1
    print("[OK] %s" % tag)


# ---------------- Related Work 补引用 ----------------
rep(r"""Drone-assisted relief delivery is usually formulated as a vehicle-routing
problem with time windows, augmented by payload, endurance and battery-swap
constraints; heterogeneous fleets and multi-trip schedules are standard. Our""",
    r"""Drone-assisted relief delivery is usually formulated as a vehicle-routing
problem with time windows, augmented by payload, endurance and battery-swap
constraints; heterogeneous fleets and multi-trip schedules are standard
\cite{murray,coutinho,boysen,erdelj}. Our""",
    "RW: 物流引用")

rep(r"""a connected chain. The dominant abstraction is a \emph{coverage} relation
between a relay position and a set of terminals, with relocation either free or
penalised by a motion cost.""",
    r"""a connected chain \cite{zeng,mozaffari,zengtraj}. The dominant abstraction
is a \emph{coverage} relation between a relay position and a set of terminals,
with relocation either free or penalised by a motion cost.""",
    "RW: 中继引用")

rep(r"""studies of low-altitude platforms use either free-space loss with an empirical
excess attenuation, or terrain-aware diffraction models; ITU-R P.~526 is the
standard reference for the latter.""",
    r"""studies of low-altitude platforms use either free-space loss with an empirical
excess attenuation, or terrain-aware diffraction models \cite{matolak}; ITU-R
P.~526 \cite{iturp526} and the Deygout construction \cite{deygout} are the
standard references for the latter.""",
    "RW: 信道引用")

rep(r"""\paragraph{Joint communication-and-trajectory design.}
Co-design of trajectories and communication is well studied for mobile relays
and cellular-connected drones.""",
    r"""\paragraph{Joint communication-and-trajectory design.}
Co-design of trajectories and communication is well studied for mobile relays
and cellular-connected drones \cite{zengtraj,mozaffari}.""",
    "RW: 联合设计引用")

# ---------------- Methodology 补引用 ----------------
rep(r"""\subsection{Constructive verifier and coverage baseline}""",
    r"""\subsection{Constructive verifier and coverage baseline}
\label{sec:verifier}""",
    "标注 verifier 小节")

rep(r"""(exact set cover, solved by CP-SAT), and set""",
    r"""(exact set cover, a classical \NP-hard problem \cite{korte}, solved here by
CP-SAT \cite{cpsat}), and set""",
    "集合覆盖引用")

rep(r"""we therefore use a
constructive verifier that advances cell by cell""",
    r"""we therefore use a
constructive verifier (in the spirit of large-neighbourhood repair heuristics
\cite{alns}) that advances cell by cell""",
    "ALNS 引用")

# ---------------- 编译说明 ----------------
rep(r"""\bibliographystyle{plain}
\bibliography{refs}""",
    r"""% ---- 编译顺序：xelatex -> bibtex -> xelatex -> xelatex -------------------
\bibliographystyle{unsrt}
\bibliography{refs}""",
    "参考文献样式")

io.open(TEX, "w", encoding="utf-8").write(s)
print("共修改 %d 处" % n)
