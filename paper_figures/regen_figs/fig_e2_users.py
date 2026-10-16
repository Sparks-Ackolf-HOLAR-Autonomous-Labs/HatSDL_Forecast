#!/usr/bin/env python3
"""Fig. 3 (E2): user actions over target as AURORA's community grows, 30 seeds.

Data: results/aurora/e2_{production,history,plan}_s{1..30}.json.gz
(one file per tuner and seed; each user action with its time, mode and
latency) and the per-mode latency targets stored in each file's meta. Curve:
share of user actions over their mode's target in a 6 s window centred on
each second; line = mean over seeds, band = interquartile range; grey = the
15 s in which a stage is on the calendar and its users have not arrived.
Takeaway: the history-based tuner misses targets when each new user group
arrives; the plan-aware tuner and the hand-set production set do not.
Style: paper_fig_style, drawn at the DCE text width (144 mm) at print size.
"""
import glob
import gzip
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, ARM_COLOURS, ARM_NAMES, IDLE, apply_style, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = HERE.parents[1]
DATA = ROOT / "results" / "aurora"
OUT = HERE.parent / "figures" / "fig_e2_users.png"
SHORT = ["today\n(development staff)", "beta\n(pilot users)", "user service\n(workshop)",
         "year 4\n(20 % of US groups)"]


def curve(run, grid, slo):
    t = np.array([x["t"] for x in run["actions"]])
    over = np.array([x["ms"] > slo[x["mode"]] for x in run["actions"]])
    out = []
    for g in grid:
        k = (t >= g - 3) & (t < g + 3)
        out.append(100 * over[k].mean() if k.any() else np.nan)
    return out


def main():
    apply_style()
    fig, ax = plt.subplots(figsize=(DCE_FULL, 2.55))
    meta = None
    for arm in ["production", "history", "plan"]:
        files = sorted(glob.glob(str(DATA / f"e2_{arm}_s*.json.gz")))
        runs = [json.loads(gzip.decompress(Path(f).read_bytes())) for f in files]
        meta = runs[0]["meta"]
        T = (meta["gap_s"] + meta["stage_s"]) * len(meta["stages"])
        grid = np.arange(0, T, 1.0)
        c = np.array([curve(r, grid, meta["slo_ms"]) for r in runs])
        q1, q3 = np.nanpercentile(c, [25, 75], axis=0)
        ax.fill_between(grid, q1, q3, color=ARM_COLOURS[arm], alpha=0.25, lw=0)
        ax.plot(grid, np.nanmean(c, axis=0), color=ARM_COLOURS[arm], lw=1.2,
                label=ARM_NAMES[arm])
    for si in range(len(meta["stages"])):
        s = meta["gap_s"] * (si + 1) + meta["stage_s"] * si
        ax.axvspan(s - meta["gap_s"], s, color=IDLE, lw=0, zorder=0)
        ax.text(s + meta["stage_s"] / 2, 1.0, SHORT[si], transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=7)
    ax.set_xlim(0, grid[-1] + 1)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("user actions over their\nlatency target in 6 s (%)")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.92))
    save(fig, OUT)


if __name__ == "__main__":
    main()
