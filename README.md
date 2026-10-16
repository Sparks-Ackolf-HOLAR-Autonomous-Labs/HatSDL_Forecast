# Laboratory plans let a self-driving database prepare for the workload of a two-dimensional materials laboratory network

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23413474.svg)](https://doi.org/10.5281/zenodo.23413474)

Code and data for the paper prepared for Data-Centric Engineering (Cambridge University Press). This folder runs on its own: copy it out, run `git init` inside it, and every figure script runs from the folder root with the packages in `requirements.txt` (the figure scripts need only numpy and matplotlib). `REPRODUCE.md` gives the steps that rebuild every figure, table and test from the files here, and the command, seeds and run time of every experiment.

| Folder | Contents |
|---|---|
| `gym/` | tuners, workload generators (laboratory day, user modes, national demand, admission control), agent harness, REST interface, analysis and statistics scripts |
| `results/aurora/` | run files and summary tables of the experiments on the copy of AURORA's database; `e1a_run_stats.json` and `e1a_curves.json` hold the per-run statistics and per-seed latency curves of all 30 E1 seeds; `seeds30/` and `e4b/run_e4b.sh` are the scripts that ran the seeds |
| `stack/postgres_setup.sh` | builds and starts the PostgreSQL 16 server with the settings of the runs |
| `results/aurora_agents/`, `results/aurora_multi/` | every agent decision with its model calls, SQL and answer |
| `paper_figures/regen_figs/` | one script per figure, drawn at print size from committed result files |
| `paper_figures/figures/` | the figures as they appear in the paper |
| `sdldb/layers/config.py` | database connection settings read by `gym/aurora_src.py` (passwords come from the environment, never from this folder) |

The experiments themselves need a PostgreSQL copy of AURORA's production database, which is not redistributed; the run files they produced are included, so every table, test and figure can be rebuilt without it. The raw E1 run files of seeds 4-30 (516 MB) are not included; the per-run statistics and curves derived from them are.

## Figures

| Figure | File | Script | Data |
|---|---|---|---|
| Fig. 1 | `paper_figures/figures/fig_loop.png` | `paper_figures/regen_figs/fig_loop.py` | none (schematic) |
| Fig. 2 | `paper_figures/figures/fig_e1a_latency.png` | `paper_figures/regen_figs/fig_e1_latency.py` | results/aurora/e1a_curves.json (from gym/e1_curves.py over the 90 E1 run files) |
| Fig. 3 | `paper_figures/figures/fig_e2_users.png` | `paper_figures/regen_figs/fig_e2_users.py` | results/aurora/e2_*_s*.json.gz (90 run files) |
| Fig. A1 (Supplementary Fig. S1) | `paper_figures/figures/fig_e4_admission.png` | `paper_figures/regen_figs/fig_e4_admission.py` | results/aurora/e4_admission_s*.json (30 seeds) |
| Fig. 4 | `paper_figures/figures/fig_e4b_surge.png` | `paper_figures/regen_figs/fig_e4b_surge.py` | results/aurora/e4b/e4b_surge_s*.json (30 seeds) |

## Tables

| Table | Source |
|---|---|
| Table 1 | results/aurora/profile.json (AURORA contents and usage counters; gym/aurora_src.py profile), write_profile.json (gym/aurora_users.py write-profile) |
| E1 numbers in the text | results/aurora/e1a_summary.md (gym/analyze_aurora.py from e1a_run_stats.json) |
| Table 2 | results/aurora/e2_summary.md (gym/analyze_users.py) |
| Table 3 | results/aurora_agents/e3_summary.md, e3b_summary.md (gym/analyze_agents.py, gym/analyze_byo.py) |
| Table A3 | results/aurora/e2b_summary.md (gym/analyze_capacity.py) |
| Tables A4-A5 | results/aurora/e2c_summary.md (gym/analyze_national.py) |
| Table A6 | results/aurora_multi/ (gym/analyze_multi.py) |
| Tables A7-A8 | results/aurora/e4_summary.md, stats_tests.md (gym/analyze_admission.py, gym/stats_tests.py) |
| Tables A9-A10 | results/aurora/e4b/summary.md, stats.json (gym/analyze_surge.py) |

## Licence

Code: MIT License (`LICENSE`). Data, result files and figures: CC BY 4.0 (`LICENSE-CC-BY-4.0.txt`).

## Acknowledgement

Taylor D. Sparks acknowledges support from the U.S. National Science Foundation through the Programmable Cloud Laboratory (PCL) Test Bed AURORA, Award No. 2607535.
