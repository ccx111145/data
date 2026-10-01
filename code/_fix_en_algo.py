# -*- coding: utf-8 -*-
"""_fix_en_algo.py —— 给英文稿补三段算法伪代码（状态 DP / 构造性判定 / 协同再调度）。

使用 `algorithm` + `algpseudocode`（TeXLive 已含）。算法步骤与
`code/q3dpN.py`、`code/greedy_relay.py`、`code/cofeedback.py` 的实现一一对应，
包括：状态三分量、四类转移条件、预防性换位的两个时机条件、阈值接受的接受准则。
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


# ---------------- 宏包 ----------------
rep(r"""\usepackage{xcolor}
\usepackage{caption}""",
    r"""\usepackage{xcolor}
\usepackage{caption}
\usepackage{algorithm}
\usepackage{algpseudocode}
\algrenewcommand\algorithmicrequire{\textbf{Input:}}
\algrenewcommand\algorithmicensure{\textbf{Output:}}
\floatname{algorithm}{Algorithm}""",
    "加入 algorithm 宏包")

# ---------------- 算法 1：精确状态 DP ----------------
rep(r"""\noindent Theorem~\ref{thm:exact} is the reason we can speak of a
\emph{decision} rather than a search failure:""",
    r"""Algorithm~\ref{alg:dp} states the recursion exactly as it is implemented.
Its only approximations are the ones discussed after Theorem~\ref{thm:exact}:
a finite candidate set and, in the runnable version, state pruning.

\begin{algorithm}[htbp]
\caption{Handover-aware relay feasibility (exact, pruning disabled)}
\label{alg:dp}
\begin{algorithmic}[1]
\Require demand cells $t_0<\dots<t_{n-1}$ with sets $\mathcal{D}_k$; candidate
points $\mathcal{C}$ with coverage $\mathrm{cov}[k,c]$; blackout $W$; cap
$T^{\mathrm{cap}}$; fleet size $N$
\Ensure a feasible schedule, or the first cell with no feasible state
\State $S_0 \gets \bigl\{\,((\mathrm{IDLE},t_0,t_0))_{i=1}^{N}\,\bigr\}$
\For{$k=0$ to $n-1$}
  \State $S_k \gets \{\,s\in S_k:\ \bigcup_{i:\,p_i\neq\mathrm{IDLE}}\mathrm{cov}[\cdot,p_i]\supseteq\mathcal{D}_k\,\}$ \Comment{(V)}
  \If{$S_k=\emptyset$} \State \Return ``no feasible state at cell $k$''
  \EndIf
  \ForAll{$s\in S_k$, $i\in\{1..N\}$, $p'\in\mathcal{C}\cup\{\mathrm{IDLE}\}$, $p'\neq p_i$}
    \State $w \gets \lceil W(p_i,p')/\Delta\rceil$
    \If{(T1) $\sigma_i\le t_k-w$ \textbf{and} (T2) $\sigma_j\le t_k-w\ \forall j\neq i$}
      \If{(T3) $\bigcup_{j\neq i}\mathrm{cov}[\cdot,p_j]\supseteq\mathcal{D}_{k'}\ \forall k'\in[k-w,k-1]$}
        \If{(T4) $\bigcup_{j}\mathrm{cov}[\cdot,p_j]\supseteq\mathcal{D}_k$ \textbf{and}
             (T5) $t_k-\varrho_i^{(k)}\le T^{\mathrm{cap}}\ \forall i$}
          \State $S_{k+1}\gets S_{k+1}\cup\{\,s\ \text{with}\ (p_i,\sigma_i)\gets(p',t_k),\ \varrho_i\gets t_k\ \text{iff mode M1 or }p_i=\mathrm{IDLE}\,\}$
        \EndIf
      \EndIf
    \EndIf
  \EndFor
\EndFor
\State \Return any state path in $S_{n-1}$
\end{algorithmic}
\end{algorithm}

\noindent\textbf{Cost.} One transition sweep touches $|S_k|\cdot N\cdot|\mathcal{C}|$
candidates and evaluates (T3) over $w$ cells, so the per-cell work is
$O(|S_k|\,N\,|\mathcal{C}|\,w)$; without pruning $|S_k|$ grows as
$|\mathcal{C}|^{N}$. This is why the runnable implementation prunes, and why the
pruning policy is reported with every infeasibility claim.

\noindent Theorem~\ref{thm:exact} is the reason we can speak of a
\emph{decision} rather than a search failure:""",
    "插入算法 1")

# ---------------- 算法 2：构造性判定 ----------------
rep(r"""The non-executable baseline ignores handovers entirely:""",
    r"""Algorithm~\ref{alg:greedy} is the constructive verifier. Two heuristic
variants are run --- with and without the pre-positioning branch (lines
\ref{line:pre}--\ref{line:preend}) --- and whichever returns a complete schedule
certifies feasibility. The pre-positioning branch was added after diagnosing a
terrain realisation in which a single, long, \emph{sparse} outage exhausted the
incumbent relay's airborne budget: the successor must be dispatched late enough
to arrive fresh, but early enough to be in place, which is exactly the timing
window tested on lines \ref{line:pre}--\ref{line:preend}.

\begin{algorithm}[htbp]
\caption{Constructive verifier for $N$ hovering relays}
\label{alg:greedy}
\begin{algorithmic}[1]
\Require as in Algorithm~\ref{alg:dp}; candidate budget $K$; safety factor $\eta$
\Ensure a complete schedule (a proof of feasibility) or the first failing cell
\State $k\gets0$;\ \ $p_i\gets\mathrm{IDLE}$,\ $\mathrm{arr}_i\gets0$,\ $\varrho_i\gets0$ for all $i$
\While{$k<n$}
  \If{$\bigcup_i \mathrm{cov}[\cdot,p_i]\supseteq\mathcal{D}_k$ \textbf{and} $\varrho$ within $T^{\mathrm{cap}}$}
    \State $k_{\mathrm{dead}}\gets$ first cell at which some relay exceeds $T^{\mathrm{cap}}$
    \If{$k_{\mathrm{dead}}$ exists, an idle relay exists, and $k_{\mathrm{dead}}-k\le$ lead}
    \label{line:pre}
      \State $p'\gets\arg\max_{p\in\mathrm{cand}(k_{\mathrm{dead}})}\ \mathrm{run}(p,k_{\mathrm{dead}})$
      \State $t_{\mathrm{arr}}\gets t_k+t^{\mathrm{out}}(p')+t_{\mathrm{link}}$
      \If{$t_{\mathrm{arr}}\le t_{k_{\mathrm{dead}}}$ \textbf{and}
          $t_{k_{\mathrm{dead}}}-t_{\mathrm{arr}}\le \eta\,T^{\mathrm{cap}}$}
        \State dispatch the idle relay to $p'$; \ $k\gets k+1$; \textbf{continue}
      \EndIf
    \label{line:preend}
    \EndIf
    \State $k\gets k+1$; \textbf{continue}
  \EndIf
  \State enumerate admissible moves $(i,p')$ satisfying (T1)--(T5), score by
         $(-\text{urgency},\,-\text{run length},\,W)$, keep the best
  \If{none is admissible} \State \Return $k$ \Comment{first failing cell}
  \EndIf
  \State perform the move; \ $k\gets k+1$
\EndWhile
\State \Return the reconstructed sortie list
\end{algorithmic}
\end{algorithm}

\noindent The non-executable baseline ignores handovers entirely:""",
    "插入算法 2")

# ---------------- 算法 3：协同再调度 ----------------
rep(r"""\subsection{Controlled terrain family}""",
    r"""Algorithm~\ref{alg:code} minimises the deficiency of
Corollary~\ref{cor:deficiency} over departure instants only.

\begin{algorithm}[htbp]
\caption{Co-design feedback loop (threshold accepting on departure instants)}
\label{alg:code}
\begin{algorithmic}[1]
\Require frozen batching, routes, aircraft types and assignments; feasible
departure window $[l_i,u_i]$ for each sortie $i$; deficiency oracle $D(\cdot)$
\Ensure best departure vector and its deficiency
\State $s\gets s^{0}$;\ \ $D^{*}\gets D(s^{0})$;\ \ $s^{*}\gets s^{0}$
\For{$r=1$ to $R$} \Comment{restarts}
  \State $s\gets$ perturb($s^{0}$)
  \For{$\mathrm{it}=1$ to $I$}
    \State pick $i$; \ $s'\gets s$ with $s_i\gets\mathrm{clip}(s_i+\mathcal{N}(0,\sigma),\,l_i,\,u_i-d_i)$
    \State $T\gets T_0\,(1-\mathrm{it}/I)$
    \If{$D(s')\le D(s)$ \textbf{or} $\mathrm{rand}()<\exp\!\bigl(-(D(s')-D(s))/T\bigr)$}
      \State $s\gets s'$
    \EndIf
    \If{$D(s)<D^{*}$} \State $D^{*}\gets D(s)$;\ \ $s^{*}\gets s$ \EndIf
  \EndFor
\EndFor
\State \Return $s^{*},D^{*}$
\end{algorithmic}
\end{algorithm}

\noindent The deficiency oracle is evaluated by mapping every outage sample to
its demand cell, forming the (cell\,$\times$\,point) matrix of single-point
coverage, taking the longest run per point (\texttt{span\_util.span\_cells}), and
then applying the time-window test of Corollary~\ref{cor:deficiency}. The
transport cost (makespan, weighted tardiness, hard-deadline violation) is
evaluated exactly at every accepted move, so no Pareto point in
Figure~\ref{fig:feedback} is estimated.

\subsection{Controlled terrain family}""",
    "插入算法 3")

io.open(TEX, "w", encoding="utf-8").write(s)
print("共修改 %d 处" % n)
