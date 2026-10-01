# -*- coding: utf-8 -*-
"""_fix_en_figs.py —— 把 4 张英文稿插图插入 paper_en/main.tex 的对应小节。

图片由 `code/make_figs_en.py` 从结果文件生成，写入 `figs/`，
经 `\\Dfig` 宏（会依次探测 figs/ 、../figs/ 等路径）引用。
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


# ---- 信道小节：插 fig_en_channel ----
rep(r"""\subsection{Handover premium}
\label{sec:baseline}""",
    r"""\Dfig[0.99]{fig_en_channel.png}{Channel-model sensitivity. Panel (a): outage
demand rises by $32.2\%$ once the constant occlusion penalty is replaced by
knife-edge diffraction. Panel (b): the supply of backhaul-feasible hover points
falls by almost half, because the relay-to-gateway link is diffracted as well.
Panel (c): the two effects compound, and the minimum fleet size rises from
$3$ to $4$; the dashed line marks the two-relay inventory.}{fig:channel}

\subsection{Handover premium}
\label{sec:baseline}""",
    "插入 fig_en_channel")

# ---- 基线小节：插 fig_en_baseline ----
rep(r"""\subsection{Is decoupling the cause?}""",
    r"""\Dfig[0.94]{fig_en_baseline.png}{Relay-side baselines. Panel (a): the
coverage abstraction that ignores handovers needs $N_{\mathrm{naive}}=1$ relay,
the rigorous lower bound (minimum covering points of every union of adjacent
phases) is $2$, and the constructive handover-aware verifier finds a schedule
with $3$. The true optimum is bracketed, and the gap between the abstraction and
the executable model --- the \emph{handover premium} --- is $2$ vehicles. Panel
(b): the per-phase-pair lower bound is $2$ throughout, i.e.\ no single phase pair
can be served by one hovering relay.}{fig:baseline}

\subsection{Is decoupling the cause?}""",
    "插入 fig_en_baseline")

# ---- 解耦小节：插 fig_en_feedback ----
rep(r"""\subsection{Baselines and ablations}""",
    r"""\Dfig[0.94]{fig_en_feedback.png}{Co-design feedback loop. Panel (a): the
handover deficiency is identical before and after re-optimising the departure
instants, and the search accepts no shift at all, so a frozen transport schedule
is not the cause of infeasibility. Panel (b): the span profile --- the longest
interval over which one single hover point can carry the whole demand ---
repeatedly falls below the required blackout window (dashed lines), which is the
mechanism behind the obstruction.}{fig:feedback}

\subsection{Baselines and ablations}""",
    "插入 fig_en_feedback")

# ---- 分节标题：信道图归属到信道小节，需要把 channel 图放在「Channel-model sensitivity」小节内 ----
# 上面把 channel 图插在 Handover premium 之前，正好位于信道小节末尾，位置正确。

# ---- 换位模式小节：新增一小节并插 fig_en_modes ----
rep(r"""\subsection{Is decoupling the cause?}""",
    r"""\subsection{Relocation mode: depot return versus air transit}
A natural objection is that infeasibility is an artefact of the depot-return
assumption: if a relay could fly directly from one hover point to another, the
blackout window would shrink and two relays might suffice. We therefore
implemented and compared both modes under the same candidate set and the same
energy budget.

\Dfig[0.90]{fig_en_modes.png}{Relocation modes. Panel (a): air transit cuts the
median blackout window from $1116$\,s to $471$\,s. Panel (b): the necessary
condition of Theorem~\ref{thm:handover} is satisfied on $72.0\%$ of the demand
cells under M1 and on $93.1\%$ under M2 --- a real improvement, but the condition
still fails somewhere, and $N=2$ is infeasible in \emph{both} modes.}{fig:modes}

\noindent The improvement is genuine in magnitude but does not change the
conclusion: with two relays the obstruction survives both relocation models, so
the result is not a consequence of the depot-return assumption.

\subsection{Is decoupling the cause?}""",
    "新增换位模式小节并插入 fig_en_modes")

io.open(TEX, "w", encoding="utf-8").write(s)
print("共插入 %d 张图" % n)
