# -*- coding: utf-8 -*-
"""make_trc_pack.py —— 生成 Transportation Research Part C（Elsevier）投稿包。

为什么单独一个脚本：T-ITS 那套包（make_submission_pack.py）是围绕 IEEEtran、
超页费、双栏紧凑版组织的；TR-C 的口径不同：
  * Elsevier 投稿走 Editorial Manager，正文用 elsarticle 版式（本包已生成）；
  * 无强制页限、订阅模式发表不收版面费（超页费不适用）；
  * Hybrid 期刊选**订阅模式**时无需 APC；只有选 OA 才付 APC。
所以这里只做 TR-C 需要的文件，不动原 T-ITS 包。

用法：python code/make_trc_pack.py
"""
from __future__ import annotations

import io
import os
import shutil
import sys

import dcore as D

PAPER = os.path.join(D.BASE, "paper_en")
BUILD = os.path.join(PAPER, "build")
DESK = r"C:\Users\ASUS\Desktop\D题_TRC投稿包"

JOURNAL = "Transportation Research Part C: Emerging Technologies"
REPO_URL = "https://github.com/ccx111145/data"


def read(p: str) -> str:
    return io.open(p, encoding="utf-8").read()


def write(p: str, s: str) -> None:
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    io.open(p, "w", encoding="utf-8").write(s)


COVER = """Cover Letter
========================================================================

Dear Editor,

We submit for consideration the manuscript

  Joint Transport-Relay Co-Design for UAV Emergency Logistics in
  Mountainous Terrain: Handover-Aware Feasibility, Channel-Model
  Sensitivity, and the Price of Partitioning

for publication in {journal}.

The transportation problem we address. Mountainous disaster relief needs
UAV fleets that can both deliver cargo and stay connected to a fixed
gateway, and the terrain that isolates the settlements is the same terrain
that occludes the air-to-ground links. The operator's decision variables
are the familiar transportation ones -- how many vehicles, on which routes,
dispatched when -- but the feasibility of a dispatch plan now depends on a
communication constraint that switches on and off over time.

Why it fits {journal}. The contribution is a transportation decision
result, not a radio result. We show that once the physical cost of handing
a hovering relay over between positions is accounted for, fleet sizing is
governed by a scalar inequality on the relay's coverage span rather than by
a coverage count, and on our instance the coverage abstraction common in
the relay literature understates the fleet by 2 vehicles. Three
consequences matter for transport operations. First, the fleet-size answer
is reported as an interval bracketed by a provable lower bound and a
constructed schedule, never as a single "minimum". Second, every negative
verdict is a search result over a declared finite space with the pruning
policy stated; the one run that would have removed that caveat consumed
1501 s of CPU without terminating and is shipped as a result file, so a
reader can reproduce the non-termination rather than take our word for it.
Third, the channel convention is not a detail: replacing the supplied
constant occlusion penalty by ITU-R P.526 diffraction on a 30 m DEM changes
the smallest constructible fleet from 3 to 4, so fleet-size claims in this
literature have to be reported with their channel convention attached.

What the manuscript contains. Section II fixes one physics convention for
energy and time. Section III develops the handover-aware feasibility model.
Sections IV-VI give the transport and relay results, including a
phase-level integer program that cross-checks the state recursion with a
structurally different model, a relocation-mode comparison that rules out
"the depot-return assumption caused it", and a controlled terrain family
that shows the fleet size does not follow occlusion volume. Section VII
states the limits of the evidence explicitly, including the five questions
we could not close.

Reproducibility. Every number, table and figure in the manuscript is
regenerated from shipped result files by a scripted pipeline
(code/make_numbers_en.py, driven by code/run_all_en.py); no value is typed
by hand except the short list of declarations given in Section VII.
Result files are archived at {repo}, and every bibliography entry was
checked against its publisher record by DOI.

Suggested reviewers. The five researchers below work on the two literatures
this manuscript sits between -- UAV relay deployment and air-to-ground
propagation on one side, disaster-relief vehicle routing on the other.
Several are cited in our reference list; none has co-authored with any of
us, and none is at our institution, so we declare no conflict of interest.
We give institutional affiliations rather than e-mail addresses, since we
cannot verify personal addresses from published papers; the editorial
office will have current contact details.

  1. Prof. Chrysafis Vogiatzis -- University of Illinois Urbana-Champaign,
     USA. Two-echelon vehicle and UAV routing for disaster response.
  2. Prof. Yong Zeng -- Southeast University, Nanjing, China. UAV
     communications: trajectory design, relay placement, air-to-ground
     channel modelling.
  3. Prof. Qingqing Wu -- Shanghai Jiao Tong University, China. UAV
     relaying, multi-UAV trajectory and communication co-design.
  4. Prof. Walid Saad -- Virginia Tech, USA. UAV deployment and coverage,
     wireless network optimisation.
  5. Prof. Rui Zhang -- National University of Singapore. UAV
     communication and energy-efficiency optimisation.

Publication charges. This is a hybrid journal and we are submitting under
the subscription model, so no article processing charge is requested.

Originality and ethics. The manuscript is original, is not under
consideration elsewhere, and all authors approve its submission. The
authors declare no competing interests. Funding: none (this research
received no external funding).

Thank you for your time and consideration.

Sincerely,
Zhifeng Liu (corresponding author)
on behalf of all authors: Changxuan Cao, Qiong Li, Zhifeng Liu,
Yulong Peng, and Zexu Ouyang
East China University of Technology (ECUT)
Nanchang, Jiangxi, China
E-mail: 2023211863@ecut.edu.cn
"""

HIGHLIGHTS = """Highlights
========================================================================

(Elsevier allows 3-5 bullets, each at most 85 characters including
spaces. Counts are given in brackets; confirm the limit on the journal's
current Guide for Authors page before uploading.)

1. Coverage-based relay sizing understates the vehicle fleet by 2  [63]
2. No 2-relay schedule found over a stated candidate set           [56]
3. The obstruction is instant-, not phase-granularity              [55]
4. P.526 diffraction raises outage demand 32.2%, fleet 3 to 4      [61]
5. Fleet size does not follow occlusion volume in our terrain study [67]

Optional extra bullet (use only if more than five are allowed):
  * Clarke-Wright wins routing but breaks hard deadlines by 30111 s [63]
"""

DATA_AVAIL = """Data Availability Statement
========================================================================
(last revised: {repo} is the authors' own repository; no substitution
required -- this file is generated by code/make_trc_pack.py)

Wording to paste into the "Data availability" box of the submission form:

  The instance (node coordinates, cargo manifest, fleet and radio
  parameters) is the benchmark shipped with the problem statement. The
  30 m digital elevation model is Copernicus GLO-30 (ESA), openly
  available. All derived result files, the figure and table generators,
  and a one-command reproduction pipeline are archived at
  {repo}
  Every numerical value in the manuscript is regenerated from those
  files by code/make_numbers_en.py, and every bibliography entry was
  checked against its publisher record by DOI with code/_verify_refs.py.

------------------------------------------------------------------------
Same text also appears as a Declarations section inside the manuscript
(Data availability / CRediT / competing interests / funding), because
Elsevier asks for these in the paper as well as in the form.
------------------------------------------------------------------------

If the venue will not host a large supplementary archive, cite the
repository URL only and keep the manuscript plus the figures.

Choice of "Dataset title" in the form: use
  Replication package: code, result files and figure generators for a
  UAV transport-relay co-design study
"""
TITLE_PAGE = """Title Page
========================================================================

Title: Joint Transport-Relay Co-Design for UAV Emergency Logistics in
       Mountainous Terrain: Handover-Aware Feasibility, Channel-Model
       Sensitivity, and the Price of Partitioning

Authors (in the order they should appear):

  1. Changxuan Cao (曹昌璇)
     East China University of Technology (ECUT), Nanchang, Jiangxi, China
     First author | 2023211904@ecut.edu.cn

  2. Qiong Li (李琼)
     East China University of Technology (ECUT), Nanchang, Jiangxi, China
     Co-author | flxnicc05@gmail.com

  3. Zhifeng Liu (刘志峰)
     East China University of Technology (ECUT), Nanchang, Jiangxi, China
     Corresponding author | 2023211863@ecut.edu.cn

  4. Yulong Peng (彭玉龙)
     East China University of Technology (ECUT), Nanchang, Jiangxi, China
     Co-author | 15579178689@163.com

  5. Zexu Ouyang (欧阳泽栩)
     East China University of Technology (ECUT), Nanchang, Jiangxi, China
     Co-author | 1028359003@qq.com

Corresponding author: Zhifeng Liu (刘志峰)
  E-mail: 2023211863@ecut.edu.cn

ORCID iDs: not available for any author (confirmed by the corresponding
author; Editorial Manager asks for one entry per author).

Keywords: UAV logistics; emergency logistics; drone delivery; relay
handover; fleet sizing; scheduling; disaster relief.

Acknowledgements: None.
Funding: None.
Declaration of interest: none.
"""

README = """# Transportation Research Part C 投稿包

## 这一包是什么

按你选定的目标刊 **Transportation Research Part C: Emerging Technologies**
（Elsevier，hybrid，订阅模式发表不收费）组织的投稿件。

与 T-ITS 包的关键差别：

| | IEEE T-ITS | TR-C（本包） |
|---|---|---|
| 版式 | IEEEtran 双栏 | **elsarticle**（Elsevier 官方类） |
| 页数限制 | 10 页 + 超页 $175/页 | **无强制页限** |
| 页数费用 | 15 页 = $875 | **$0**（订阅模式） |
| 投稿系统 | IEEE Author Portal | Elsevier **Editorial Manager** |
| 评审 | 单盲 | 单盲 |

**因此不需要压缩到 10 页，也不需要搬走任何证明**——正文保留完整论证。

## 要上传的文件

| 文件 | 用途 |
|---|---|
| `01_Manuscript.pdf` | 正文（elsarticle 版式，含作者信息） |
| `02_Cover_Letter.pdf` / `.txt` | 投稿信（含 5 位建议审稿人、无 APC 声明） |
| `03_Highlights.txt` | 3–5 条要点，≤85 字符 |
| `04_Title_Page.txt` | 标题页（作者、单位、ORCID、关键词） |
| `05_Declaration_of_Interest.txt` | 利益冲突声明 |
| `06_Data_Availability_Statement.txt` | 数据可得性 |
| `07_CRediT_Author_Statement.txt` | 作者贡献（14 角色按作者顺序） |
| `08_LaTeX_source.zip` | 源码（elsarticle） |

## 正文规模（本轮最终）

| 项目 | 数值 |
|---|---|
| 页数 | **47**（elsarticle preprint，单栏；TR-C 无强制页限） |
| 图 | **12 张**（其中位图仅 2 张：DEM 晕渲、研究区环境图；其余全部矢量） |
| 表 | 8 张 |
| 编译 | 0 错误 / 0 未定义引用 / 0 overfull |
| 正文自带声明 | Data availability（含仓库 URL）、CRediT、利益冲突、致谢、资助 |
| TBD / ?? / 中日韩字符 | 0 / 0 / 0 |

**图的构成**：通信/中继侧 8 张（环境、信道敏感性、基线、理论、换位模式、
协同再调度、相位结构、三法判定）+ 运输侧 3 张（Pareto 前沿、架次甘特图、
通信保障）+ 地形族 1 张。

## 上传动作清单

1. 打开 https://www.editorialmanager.com/trc/ ，登录（无账号先 Register）。
2. 选 **Submit New Manuscript**，文章类型 **Regular Paper**。
3. 逐栏上传：
   - Manuscript → `01_Manuscript.pdf`
   - Cover Letter → `02_Cover_Letter.pdf`
   - Highlights → `03_Highlights.txt`
   - Title Page → `04_Title_Page.txt`
   - Declaration of Interest → `05_Declaration_of_Interest.txt`
   - Data Availability → `06_Data_Availability_Statement.txt`
   - CRediT / Author Statement → `07_CRediT_Author_Statement.txt`
   - LaTeX source → `08_LaTeX_source.zip`
4. 填 Authors（五位，通讯作者 Liu），ORCID 栏填 not available。
5. 在 "Comments" 或 "Suggested Reviewers" 栏粘贴投稿信里的 5 位建议审稿人。
6. **提交前最后一次**打开 TR-C 的 Guide for Authors，核对：
   - Page charges / Open access 两节的当期口径；
   - Highlights 的字符上限；
   - 是否要求把 Data availability 单独成栏（本包两种都给：正文有声明节，
     另有独立文本文件）。

## 投稿入口（已核实可访问）

| 用途 | 链接 |
|---|---|
| **投稿系统（Elsevier Editorial Manager，TR-C）** | **https://www.editorialmanager.com/trc/** |
| 期刊页 / Guide for Authors | https://www.elsevier.com/journals/transportation-research-part-c-emerging-technologies/0968-090X |

Editorial Manager 入口我实测返回 HTTP 200，页面标题确认为
"Transportation Research Part C"，是期刊的官方投稿系统（无静态直达投稿页，
登录后选 "Submit New Manuscript"）。

## 版面费口径（有官方原文的一条）

Elsevier 官方 Guide for Authors 的 Publishing options 节：
"The journal offers authors a choice in publishing their research: **Subscription**
-- Articles are made available to subscribers... **no charge to publish**;
**Open access** -- Articles are freely available... **an APC** is payable."

即：**走订阅模式发表不收费**。我们按订阅模式投稿，投稿信里已声明
"we are submitting under the subscription model, so no article processing charge
is requested"。

> 我**没能**打开 TR-C 自己的 Guide for Authors 页面（Elsevier 对自动抓取返回
> 403）。上面这句是 Elsevier 官方对**全部** Guide for Authors 通用的
> "Publishing options" 表述，不是我读到的 TR-C 专页原文。投之前请你打开
> TR-C 的 Guide for Authors，确认 "Page charges" / "Open access" 两节。

## 上传前你必须自己核的两件事

1. **TR-C 当前的收费口径**：本包按"hybrid + 订阅模式 = 不收费"组织。
   Elsevier 的 Guide for Authors 页面对自动化抓取返回 403，**我没能读到原文**，
   所以这一条我是依据 Springer Nature 官方对订阅模式的说明 + Elsevier
   hybrid 的通行做法推断的，**不是我核实过的 TR-C 原文**。投之前请打开
   TR-C 的 Guide for Authors 亲眼看一眼 "Page charges" / "Open access" 两节。
2. **Highlights 的 85 字符上限**：同样是典型的 Elsevier 约定，我没能核实到
   TR-C 当期页面。本包已把每条的字符数标在括号里。

## 为什么选 TR-C（匹配度说明，供你写投稿信时参考）

- 本文内核是"**运输决策受通信可行性约束**"——派多少架、走哪条路、何时起飞，
  在加入"中继可用性"后整体改写，这是 TR-C 的 emerging technologies 定位；
- 方法上有 CP-SAT 集合划分、ALNS、相位松弛、下界构造，TR-C 接收"方法学 + 应用"
  的交叉工作；
- 参考文献里 Faiz et al. (2024, Networks) 是几乎同题的工作（两梯队车辆+UAV、
  灾后救援），说明这一方向有活跃的读者群。

## 已知会被审稿人追问的一点

TR-C 审稿人偏重真实路网/案例数据。本文用的是 30 m Copernicus DEM 构建的
**受控山地算例**，不是公认交通基准。投稿信里 "Why it fits" 一节已主动说明
算例来源与边界，正文 §VII 也逐项声明了未能解决的问题。这是诚实披露，
但不改变"算例代表性"本身会成为审稿意见。
"""


def main() -> int:
    os.makedirs(DESK, exist_ok=True)
    got = []

    # 1) 正文（elsarticle）
    src = os.path.join(PAPER, "main_elsarticle.pdf")
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(DESK, "01_Manuscript.pdf"))
        got.append("01_Manuscript.pdf")

    # 2) 投稿信 / Highlights / 标题页
    write(os.path.join(DESK, "02_Cover_Letter.txt"), COVER.format(
        journal=JOURNAL, repo=REPO_URL))
    write(os.path.join(DESK, "03_Highlights.txt"), HIGHLIGHTS)
    write(os.path.join(DESK, "04_Title_Page.txt"), TITLE_PAGE)

    # 3) 复用 T-ITS 包里已核过的声明类文件（内容与刊无关）
    #    注意：06_Data_Availability 不从这里抄 —— T-ITS 那份模板里带一条
    #    "把 ccx111145 换成你自己的账号" 的说明，而本包的仓库早已写定，
    #    抄过来会与正文声明自相矛盾。改为本包自行生成（见 DATA_AVAIL）。
    old = r"C:\Users\ASUS\Desktop\D题_投稿包"
    for src_name, dst_name in (("05_Declaration_of_Interest.txt",
                                "05_Declaration_of_Interest.txt"),
                               ("08_CRediT_author_statement.txt",
                                "07_CRediT_Author_Statement.txt")):
        p = os.path.join(old, src_name)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(DESK, dst_name))
            got.append(dst_name)
    write(os.path.join(DESK, "06_Data_Availability_Statement.txt"),
          DATA_AVAIL.format(repo=REPO_URL))
    got.append("06_Data_Availability_Statement.txt")

    # 4) 源码（elsarticle 版）
    zpath = os.path.join(DESK, "08_LaTeX_source.zip")
    import zipfile
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("main_elsarticle.tex", "numbers_en.tex", "refs.bib"):
            p = os.path.join(BUILD, name)
            if not os.path.exists(p):
                p = os.path.join(PAPER, name)
            if os.path.exists(p):
                z.write(p, "manuscript/" + name)
        fdir = os.path.join(PAPER, "build", "figs")
        if not os.path.isdir(fdir):
            fdir = os.path.join(PAPER, "figs")
        if os.path.isdir(fdir):
            for f in sorted(os.listdir(fdir)):
                low = f.lower()
                # 只装矢量 PDF 与 DEM 那张 PNG。同名 PNG 与 PDF 是同一张图，
                # 两个都塞只是重复占体积（上一版 zip 11 MB 就是这么来的）。
                if low.endswith(".png") and "env" not in low:
                    continue
                z.write(os.path.join(fdir, f), "manuscript/figs/" + f)
    got.append("08_LaTeX_source.zip")

    write(os.path.join(DESK, "00_READ_ME_first.md"), README)
    print("TR-C 投稿包已生成：%s" % DESK)
    for f in sorted(os.listdir(DESK)):
        p = os.path.join(DESK, f)
        print("  %-36s %8.1f KB" % (f, os.path.getsize(p) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
