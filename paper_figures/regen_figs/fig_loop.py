#!/usr/bin/env python3
"""Fig. 1: schematic of the self-driving database loop on a laboratory network node.

No data; the boxes follow the Problem setting and System sections of the
paper (plan and captured workload -> forecast -> behaviour model and planner ->
actions in idle windows -> engines and clients -> measured latency back to the
planner, which keeps or reverts each action).
Style: paper_fig_style fonts (7-8 pt), DCE text width (144 mm) at print size.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

OUT = HERE.parent / "figures" / "fig_loop.png"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 7})
W, H = DCE_FULL, 7.4 / 2.54
fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, 178); ax.set_ylim(-9, 60); ax.axis("off")
LINE = "0.25"


def box(x, y, w, h, title, body, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=2",
                                fc=fc, ec="0.35", lw=0.6))
    ax.text(x + w / 2, y + h - 2.2, title, ha="center", va="top", fontsize=7.5, weight="bold")
    ax.text(x + w / 2, y + h - 7.4, body, ha="center", va="top", fontsize=7, linespacing=1.25)


def arrow(x0, y0, x1, y1):
    ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", lw=0.8, color=LINE,
                                                        shrinkA=0, shrinkB=0))


plan, ctrl, eng = "#e8f1fa", "#eef7ee", "#f4f4f4"
box(3, 33, 40, 24, "Lab network plan",
    "scheduler queue, e.g.\nflake scan of chip 12\nallocation calendar, e.g.\n320-student workshop", plan)
box(3, 3, 40, 24, "Workload capture",
    "query statistics tagged\nwith the task, user class\nand agent version\nthat issued them", plan)
box(49, 18, 27, 24, "Forecast",
    "announced work\n× footprints\n+ short-horizon\nforecast of open\ntraffic", ctrl)
box(82, 18, 32, 24, "Behaviour model\nand planner",
    "\ncost of each query\nunder each action;\ncost of the action;\nbudget", ctrl)
box(120, 33, 56, 24, "Actions in idle windows",
    "indexes, summary tables;\nconnection reservations\nper user class; rate limits\nfor machine clients", ctrl)
box(120, 3, 56, 24, "Engines and clients",
    "PostgreSQL (system of record),\nobject store, graph, vectors;\nserving instruments, planners,\npeople, open readers, agents", eng)

arrow(43.6, 38, 48.4, 38)            # plan -> forecast
arrow(43.6, 22, 48.4, 22)            # workload capture -> forecast
arrow(76.6, 30, 81.4, 30)            # forecast -> planner
arrow(114.6, 38, 119.4, 42)          # planner -> actions
arrow(148, 32.4, 148, 27.6)          # actions -> engines
# feedback: measured latency runs along the bottom, from the engines back to the planner
ax.plot([148, 148, 98], [2.4, -5, -5], color=LINE, lw=0.8, solid_capstyle="butt")
arrow(98, -5, 98, 17.4)
ax.text(123, -5.8, "measured latency per user class: keep or revert each action", ha="center", va="top",
        fontsize=7, color="0.2")
fig.subplots_adjust(0, 0, 1, 1)
save(fig, OUT, pdf=True)
