#!/usr/bin/env python3
"""Fig. 5: admission control under an unannounced surge of unknown size, 30 seeds.

Data: results/aurora/e4b/e4b_surge_s{1..30}.json (per seed: the drawn
research-user burst and script surge, and per arm the summary of the surge and
workshop phases). Three panels: (a) people's actions over target (surge and
workshop phases together) against the size of the research-user burst, one
point per seed and arm, arms offset slightly along x; seeds with no action
over target are drawn in the shaded band at 0.01 %; (b) script requests still
queued at the end of the run against the size of the script surge; (c) seeds
in which each arm failed (more than 1 % of people's actions over target in a
phase, or script requests still queued at the end; gym/analyze_surge.py), of 30.
Colours: blue = fixed splits set by hand, orange = reactive controller,
green = self-driving controller (paper_fig_style). Takeaway: every fixed split
fails for some surge size, in people (a) or in an unbounded script backlog (b);
the self-driving controller fails in one seed (c).
Style: paper_fig_style, drawn at the DCE text width (144 mm) at print size.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, ARM_COLOURS, ARM_NAMES, ARM_MARKERS, apply_style, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = HERE.parents[1]
DATA = ROOT / "results" / "aurora" / "e4b"
OUT = HERE.parent / "figures" / "fig_e4b_surge.png"
ARMS = ["static51", "static", "static33", "reactive", "forecast"]
SHORT = {"static51": "fixed\n5:1", "static": "fixed\n4:2", "static33": "fixed\n3:3", "reactive": "reactive",
         "forecast": "self-\ndriving"}
FLOOR = 0.01  # % shown for seeds with no action over target (logarithmic axis)
PEOPLE_FAIL = 1.0


def phases(s):
    return [s["surge"], s["workshop"]]


def people_over(s):
    ph = phases(s)
    n = sum(p["people_n"] for p in ph)
    return 100 * sum(p["people_over"] * p["people_n"] for p in ph) / max(1, n)


def failed(s):
    worst = max(100 * p["people_over"] for p in phases(s))
    left = sum(s["undrained"].values())
    return worst > PEOPLE_FAIL, left > 0


def main():
    apply_style()
    runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(DATA / "e4b_surge_s*.json")))]
    runs = [r for r in runs if all(a in r["arms"] for a in ARMS)]
    fig, ax = plt.subplots(1, 3, figsize=(DCE_FULL, 2.75), width_ratios=[1, 1, 0.8])
    ax[0].axhspan(0.006, 0.014, color="#EBEBEB", lw=0, zorder=0)
    for i, a in enumerate(ARMS):
        off = 1 + 0.035 * (i - 2)
        kw = dict(s=17, marker=ARM_MARKERS[a], color=ARM_COLOURS[a], edgecolor="white", linewidth=0.4,
                  alpha=0.85, zorder=4 if a == "forecast" else 3)
        ax[0].scatter([r["research"] * off for r in runs],
                      [max(people_over(r["arms"][a]), FLOOR) for r in runs], label=ARM_NAMES[a], **kw)
        ax[1].scatter([r["scripts"] * off for r in runs],
                      [sum(r["arms"][a]["undrained"].values()) for r in runs], **kw)
        f = [failed(r["arms"][a]) for r in runs]
        both = sum(p or q for p, q in f)
        people = sum(p for p, _ in f)
        y = len(ARMS) - 1 - i
        ax[2].barh(y, people, color=ARM_COLOURS[a], height=0.65, edgecolor=ARM_COLOURS[a])
        ax[2].barh(y, both - people, left=people, color="white", height=0.65, edgecolor=ARM_COLOURS[a],
                   hatch="////", lw=0.8)
        ax[2].text(both + 0.6, y, str(both), ha="left", va="center", fontsize=7)
        print(a, "failed", both, "people", people)
    ax[0].axhline(1.0, color="#555555", lw=0.8, ls="--", zorder=1)
    ax[0].set(xscale="log", yscale="log", ylim=(0.006, 200),
              xlabel="research-user burst, e.g. after\na news item (users)",
              ylabel="people's actions over target (%)")
    ax[1].set(xscale="log", yscale="symlog", ylim=(-0.5, 6e4),
              xlabel="script surge from machine\nclients (scripts)",
              ylabel="script requests still\nqueued at the end")
    ax[1].set_yticks([0, 10, 100, 1000, 10000])
    ax[0].set_xticks([100, 200, 500, 1000])
    ax[1].set_xticks([30, 100, 300, 1000])
    for k in range(2):
        ax[k].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax[k].xaxis.set_minor_formatter(plt.NullFormatter())
    ax[0].set_yticks([0.01, 0.1, 1, 10, 100], ["none", "0.1", "1", "10", "100"])
    ax[2].set_yticks(range(len(ARMS))[::-1], [SHORT[a].replace("\n", " ").replace("- ", "-") for a in ARMS])
    ax[2].set_xlim(0, 30)
    ax[2].set_xticks([0, 10, 20, 30])
    ax[2].set_xlabel("seeds failed (of 30)")
    from matplotlib.patches import Patch
    ax[2].legend(handles=[Patch(facecolor="#777777", label="people over target"),
                          Patch(facecolor="white", edgecolor="#777777", hatch="////", label="script backlog only")],
                 loc="upper left", fontsize=6.5, handlelength=1.2, borderaxespad=0.1)
    ax[2].set_ylim(-0.6, 6.4)
    ax[2].grid(axis="y", visible=False)
    for k in range(3):
        ax[k].set_title(f"({'abc'[k]})", loc="left", fontsize=9, fontweight="bold")
    h, lab = ax[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="outside upper center", ncol=3, handletextpad=0.2, columnspacing=1.0)
    save(fig, OUT)
    print("seeds", len(runs), "->", OUT)


if __name__ == "__main__":
    main()
