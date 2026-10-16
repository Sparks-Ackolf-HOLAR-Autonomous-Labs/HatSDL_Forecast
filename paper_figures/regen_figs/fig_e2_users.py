#!/usr/bin/env python3
"""Fig. 3: user actions over target as AURORA's community grows, 30 seeds.

Data: results/aurora/e2_{production,history,plan}_s{1..30}.json.gz
(one file per tuner and seed; each user action with its time, mode and
latency) and the per-mode latency targets stored in each file's meta. Curve:
share of user actions over their mode's target in a 6 s window centred on
each second; line = median over seeds, band = interquartile range (as in
Fig. 2); grey = the 15 s in which a stage is on the calendar and its users
have not arrived. (a) full scale; (b) the same curves from 0 to 5 %, where the
production indexes and the plan-aware tuner lie. Colours and line styles
follow paper_fig_style. Takeaway: the history-based tuner misses targets when
each new user group arrives; the plan-aware tuner and the hand-set production
set do not.
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
from paper_fig_style import DCE_FULL, ARM_COLOURS, ARM_NAMES, ARM_STYLES, IDLE, apply_style, save  # noqa: E402
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
    fig, axes = plt.subplots(2, 1, figsize=(DCE_FULL, 4.6), height_ratios=[1.25, 1])
    meta = None
    rng = np.random.default_rng(0)
    for ai, arm in enumerate(["production", "history", "plan"]):
        files = sorted(glob.glob(str(DATA / f"e2_{arm}_s*.json.gz")))
        runs = [json.loads(gzip.decompress(Path(f).read_bytes())) for f in files]
        meta = runs[0]["meta"]
        slo = meta["slo_ms"]
        T = (meta["gap_s"] + meta["stage_s"]) * len(meta["stages"])
        grid = np.arange(0, T, 1.0)
        c = np.array([curve(r, grid, slo) for r in runs])
        q1, med, q3 = np.nanpercentile(c, [25, 50, 75], axis=0)
        axes[0].fill_between(grid, q1, q3, color=ARM_COLOURS[arm], alpha=0.2, lw=0)
        axes[0].plot(grid, med, color=ARM_COLOURS[arm], ls=ARM_STYLES[arm], lw=1.4, label=ARM_NAMES[arm])
        # (b) share over target per stage and seed (as in Table A3), one point per seed, bar = median
        for si in range(len(meta["stages"])):
            v = [100 * np.mean([x["ms"] > slo[x["mode"]] for x in r["actions"] if x["stage"] == si])
                 for r in runs]
            x0 = si + (ai - 1) * 0.25
            axes[1].scatter(x0 + rng.uniform(-0.07, 0.07, len(v)), v, s=7, color=ARM_COLOURS[arm],
                            marker="osD"[ai], alpha=0.6, lw=0)
            axes[1].plot([x0 - 0.1, x0 + 0.1], [np.median(v)] * 2, color="#333333", lw=1.3)
    for si in range(len(meta["stages"])):
        s = meta["gap_s"] * (si + 1) + meta["stage_s"] * si
        axes[0].axvspan(s - meta["gap_s"], s, color=IDLE, lw=0, zorder=0)
        axes[0].text(s + meta["stage_s"] / 2, 1.0, SHORT[si], transform=axes[0].get_xaxis_transform(),
                     ha="center", va="bottom", fontsize=7)
    axes[0].set_xlim(0, grid[-1] + 1)
    axes[0].set_ylim(bottom=0)
    axes[0].set_xlabel("time (s)")
    axes[0].set_ylabel("user actions over their\nlatency target in 6 s (%)")
    axes[1].set_xticks(range(len(meta["stages"])), SHORT)
    axes[1].set_yscale("symlog", linthresh=1)
    axes[1].set_ylim(-0.1, 60)
    axes[1].set_yticks([0, 1, 10, 50], ["0", "1", "10", "50"])
    axes[1].set_ylabel("actions over target\nper stage and seed (%)")
    for k, ax in enumerate(axes):
        ax.set_title(f"({'ab'[k]})", loc="left", fontsize=9, fontweight="bold", x=-0.1, y=1.17 if k == 0 else 1.0)
    fig.legend(loc="outside lower center", ncol=3, handlelength=3.0)
    save(fig, OUT)


if __name__ == "__main__":
    main()
