#!/usr/bin/env python3
"""Fig. A1 (E4, annex): admission control on 6 shared connections, 30 seeds.

Data: results/aurora/e4_admission_s{1..30}.json (per seed and arm,
summary values before the surge, during the unannounced script surge and
during the announced workshop). Three panels: (a) people's actions over
target, (b) time the database added to an agent decision (95th percentile,
logarithmic), (c) script requests answered within 1 s. Point = mean over
seeds, bar = interquartile range. Takeaway: only the controller that reads the
calendar keeps people on target through both events, without starving agents.
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
DATA = ROOT / "results" / "aurora"
OUT = HERE.parent / "figures" / "fig_e4_admission.png"
ARMS = ["shared", "static", "reactive", "forecast"]
PH = ["before", "surge", "workshop"]
PANELS = [
    ("people's actions\nover target (%)", lambda s, p: 100 * s[p]["people_over"], "linear"),
    ("time added to an agent\ndecision, 95th pct (s)", lambda s, p: s[p]["llm_added_s_p95"], "log"),
    ("script requests answered\nwithin 1 s (per s)",
     lambda s, p: s[p]["script_served_per_s"] * (1 - s[p]["script_over"]), "linear"),
]


def main():
    apply_style()
    runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(DATA / "e4_admission_s*.json")))]
    runs = [r for r in runs if all(a in r["arms"] for a in ARMS)]
    fig, axes = plt.subplots(1, 3, figsize=(DCE_FULL, 2.35))
    for k, (ax, (label, fn, scale)) in enumerate(zip(axes, PANELS)):
        for i, a in enumerate(ARMS):
            x = np.arange(len(PH)) + (i - 1.5) * 0.17
            v = np.array([[fn(r["arms"][a], p) for p in PH] for r in runs], dtype=float)
            mean = v.mean(axis=0)
            q1, q3 = np.percentile(v, [25, 75], axis=0)
            ax.errorbar(x, mean, yerr=[mean - np.minimum(q1, mean), np.maximum(q3, mean) - mean],
                        fmt="o", ms=3.2, capsize=1.8, lw=1.0, color=ARM_COLOURS[a],
                        label=ARM_NAMES[a] if k == 0 else None)
        ax.set_xticks(range(len(PH)), ["before", "surge", "workshop"])
        ax.set_ylabel(label)
        ax.set_yscale(scale)
        ax.set_title(f"({'abc'[k]})", loc="left", fontsize=9, fontweight="bold")
    fig.legend(loc="outside upper center", ncol=4)
    save(fig, OUT)


if __name__ == "__main__":
    main()
