#!/usr/bin/env python3
"""Fig. 2: decision latency through a scripted AURORA day, 30 seeds.

Data: results/aurora/e1a_curves.json (built by gym/e1_curves.py from
the 90 run files of the laboratory-day experiment): 95th-percentile decision
latency in 6 s windows, one curve per tuner and seed. One panel, logarithmic
latency axis; line = median over seeds, band = interquartile range; grey =
idle window the scheduler announced before each phase; phase names above the
panel. Colours and line styles follow paper_fig_style (blue dashed = set by
hand, orange dotted = learns from history, green solid = reads the plan).
Takeaway: the plan-aware tuner is fast from the start of each phase, the
history-based tuner only after about 10 s, the production indexes stay slow
for review and stacking.
Style: paper_fig_style, drawn at the DCE text width (144 mm) at print size.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, ARM_COLOURS, ARM_NAMES, ARM_STYLES, IDLE, apply_style, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = HERE.parents[1]
DATA = ROOT / "results" / "aurora" / "e1a_curves.json"
OUT = HERE.parent / "figures" / "fig_e1a_latency.png"
SHORT = ["chip scan and\nflake detection", "review of\nthe new chips", "stacking\nplanner",
         "detection with\nweb viewing"]


def main():
    apply_style()
    d = json.loads(DATA.read_text())
    m, grid = d["meta"], np.array(d["grid_s"])
    fig, ax = plt.subplots(figsize=(DCE_FULL, 2.75))
    for pi in range(len(m["phases"])):
        s = m["gap_s"] * (pi + 1) + m["phase_s"] * pi
        ax.axvspan(s - m["gap_s"], s, color=IDLE, lw=0, zorder=0)
        ax.text(s + m["phase_s"] / 2, 1.0, SHORT[pi], transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=7)
    for arm in ["production", "history", "plan"]:
        c = np.array([[np.nan if v is None else v for v in cur] for cur in d["curves"][arm].values()])
        q1, med, q3 = np.nanpercentile(c, [25, 50, 75], axis=0)
        ax.fill_between(grid, q1, q3, color=ARM_COLOURS[arm], alpha=0.2, lw=0)
        ax.plot(grid, med, color=ARM_COLOURS[arm], ls=ARM_STYLES[arm], lw=1.4,
                label=ARM_NAMES[arm], zorder=3 if arm == "production" else 2)
    ax.set_yscale("log")
    ax.set_xlim(0, grid[-1] + 1)
    ax.set_xlabel("time in the scripted AURORA day (s)")
    ax.set_ylabel("decision latency, 95th\npercentile in 6 s (ms)")
    fig.legend(loc="outside lower center", ncol=3, handlelength=3.0)
    save(fig, OUT)


if __name__ == "__main__":
    main()
