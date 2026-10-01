# UAV transport–relay co-design in mountainous terrain — replication package

Code, result files and figure generators for the manuscript

> **Joint Transport–Relay Co-Design for UAV Emergency Logistics in Mountainous
> Terrain: Handover-Aware Feasibility, Channel-Model Sensitivity, and the Price of
> Partitioning**

submitted to *Transportation Research Part C: Emerging Technologies*.

Every number, table and figure in the manuscript is regenerated from the result
files in this repository by a scripted pipeline. No value is typed by hand except
the declarations listed in Section VII of the paper.

---

## What is where

| Directory | Contents |
|---|---|
| `code/` | All Python used to produce the results, figures and tables, plus the verification scripts |
| `results/` | Result files (JSON/XLSX) that the manuscript's numbers are generated from |
| `figs/` | Raster figures (Chinese competition paper) |
| `figs_els/` | Vector figures at Elsevier column width (used by the submission) |
| `figs_ieee/` | Vector figures at IEEE two-column width |
| `paper/` | LaTeX source of the Chinese competition paper |
| `paper_en/` | LaTeX source of the English manuscript (`main.tex` is the single source of truth) |
| `数据/` | Input geospatial data (Copernicus GLO-30 DEM subset) and the benchmark instance |

## How to regenerate

```bash
# Python 3.11+; the pipeline pins its own dependencies in code/
python code/run_all_en.py          # full pipeline: results -> figures -> numbers
python code/make_figs_en.py        # figures only (IEEE column width)
DTS_FIGW=5.4 DTS_FIGDIR=figs_els python code/make_figs_en.py   # Elsevier width
python code/make_numbers_en.py     # LaTeX macros from the result files
python code/check_consistency.py   # 47-cell consistency gate; non-zero exit on failure
```

Figures are generated at a canvas width equal to the width they are *displayed*
at, so that in-figure type is not scaled down. `DTS_FIGW` sets that width and
`DTS_FIGDIR` the output directory; the two sets (`figs_els/`, `figs_ieee/`) are
generated separately because the two layouts display figures at different widths.

## Manuscript build

```bash
cd paper_en
xelatex main && bibtex main && xelatex main && xelatex main
```

## Verification

| Script | What it checks |
|---|---|
| `code/check_consistency.py` | 47 consistency checks (numbers vs. text, banned overclaims, no non-ASCII in the English source); aborts packaging on failure |
| `code/_verify_refs.py` | Every bibliography entry against its publisher record by DOI |
| `code/_crosscheck_pack.py` | Submission-pack numbers against the generated LaTeX macros |
| `code/_check_overlap.py` | In-figure text collisions (unreliable for rotated labels — see the docstring) |
| `code/_refcheck.py` | 20 referee-item assertions |

## Scope and limits

The manuscript states its limits explicitly rather than implying they are solved.
In particular:

- Every **negative** fleet-size verdict is a statement about a **declared finite
  search space** with a stated pruning policy. None is a statement of
  impossibility. One run that would have removed that caveat did not terminate
  within the compute budget and is shipped as a result file so the
  non-termination can be reproduced.
- The transport layer is solved heuristically; no optimality gap is claimed.
- The terrain family is derived from a single elevation model by controlled
  transformations, and outage statistics are verified on a fixed sampling grid.
- This is a controlled mountainous instance, **not** a public transportation
  benchmark.

## Data sources

- Benchmark instance: supplied with the problem statement.
- Elevation: **Copernicus GLO-30** (ESA), 30 m, EPSG:4326. Openly available.
- Propagation: ITU-R P.526 single-knife-edge diffraction.

## Authors

Changxuan Cao, Qiong Li, Zhifeng Liu (corresponding), Yulong Peng, Zexu Ouyang —
East China University of Technology (ECUT), Nanchang, Jiangxi, China.

## License

Code under the MIT License (see `LICENSE`). Manuscript text and figures remain
© the authors.
