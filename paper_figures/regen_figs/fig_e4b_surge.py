#!/usr/bin/env python3
"""Fig. 4 (E4b): admission control under an unannounced surge of unknown size, 30 seeds.

Data: results/aurora/e4b/e4b_surge_s{1..30}.json (per seed: the drawn
research-user burst and script surge, and per arm the summary of the surge and
workshop phases). Two panels, one point per seed and arm: (a) people's actions
over target (surge and workshop phases together) against the size of the
research-user burst; (b) script requests still queued at the end of the run
against the size of the script surge. Takeaway: every fixed split fails for
some surge size, in people (a) or in an unbounded script backlog (b); the
self-driving controller does neither.
Style: paper_fig_style, drawn at the DCE text width (144 mm) at print size.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, ARM_COLOURS, ARM_NAMES, apply_style, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = HERE.parents[1]
DATA = ROOT / "results" / "aurora" / "e4b"
OUT = HERE.parent / "figures" / "fig_e4b_surge.png"
ARMS = ["static51", "static", "static33", "reactive", "forecast"]
COL = {**ARM_COLOURS, "static51": "#4A90C8", "static33": "#CC79A7"}
NAME = {**ARM_NAMES, "static51": "fixed split 5:1", "static": "fixed split 4:2",
        "static33": "fixed split 3:3"}
MARK = {"static51": "v", "static": "s", "static33": "^", "reactive": "D", "forecast": "o"}
FLOOR = 0.01  # % shown for seeds with no action over target (logarithmic axis)


def people_over(s):
    ph = [s["surge"], s["workshop"]]
    n = sum(p["people_n"] for p in ph)
    return 100 * sum(p["people_over"] * p["people_n"] for p in ph) / max(1, n)


def main():
    apply_style()
    runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(DATA / "e4b_surge_s*.json")))]
    runs = [r for r in runs if all(a in r["arms"] for a in ARMS)]
    fig, ax = plt.subplots(1, 2, figsize=(DCE_FULL, 2.45))
    for a in ARMS:
        kw = dict(s=13, marker=MARK[a], color=COL[a], edgecolor="white", linewidth=0.4,
                  zorder=4 if a == "forecast" else 3)
        ax[0].scatter([r["research"] for r in runs],
                      [max(people_over(r["arms"][a]), FLOOR) for r in runs], label=NAME[a], **kw)
        ax[1].scatter([r["scripts"] for r in runs],
                      [sum(r["arms"][a]["undrained"].values()) for r in runs], **kw)
    ax[0].axhline(1.0, color="#8C8C8C", lw=0.8, ls="--", zorder=1)
    ax[0].set(xscale="log", yscale="log", ylim=(0.006, 200),
              xlabel="unannounced research-user burst (users)",
              ylabel="people's actions over target (%)")
    ax[1].set(xscale="log", yscale="symlog", ylim=(-0.5, 6e4),
              xlabel="unannounced script surge (scripts)",
              ylabel="script requests still\nqueued at the end")
    ax[1].set_yticks([0, 10, 100, 1000, 10000])
    ax[0].set_xticks([100, 200, 500, 1000, 2000])
    ax[1].set_xticks([30, 100, 300, 1000])
    for k in range(2):
        ax[k].set_title(f"({'ab'[k]})", loc="left", fontsize=9, fontweight="bold")
        ax[k].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax[k].xaxis.set_minor_formatter(plt.NullFormatter())
    fig.legend(loc="outside upper center", ncol=3, handletextpad=0.2, columnspacing=1.0)
    save(fig, OUT)
    print("seeds", len(runs), "->", OUT)


if __name__ == "__main__":
    main()
