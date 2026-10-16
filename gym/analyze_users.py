"""Summarise experiment E2 on AURORA (results/aurora/e2_*.json.gz): tables and figure.

    python -m gym.analyze_users
"""
from __future__ import annotations

import glob
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora"
ARMS = ["production", "history", "plan"]
LABEL = {"production": "production index set (fixed)", "history": "history-based tuner",
         "plan": "plan-aware tuner (allocation calendar)"}
MODE_LABEL = {"staff": "development staff", "novice": "first-time users", "research": "research users",
              "power": "power users", "prototype": "innovation / prototyping", "industry": "industry users",
              "education": "education users", "ehs": "safety-critical / EHS"}


def load():
    runs = defaultdict(list)
    for f in sorted(glob.glob(str(OUT / "e2_*_s*.json.gz"))):
        d = json.loads(gzip.decompress(Path(f).read_bytes()))
        runs[d["meta"]["arm"]].append(d)
    return runs


def stage_start(m, si):
    return m["gap_s"] * (si + 1) + m["stage_s"] * si


def p95(v):
    return float(np.percentile(v, 95)) if len(v) else np.nan


def main():
    runs = load()
    arms = [a for a in ARMS if runs[a]]
    bm = json.loads((OUT / "behaviour_model_users.json").read_text())
    size = {k: v["size_mb"] for k, v in bm["indexes"].items()}
    meta = runs[arms[0]][0]["meta"]
    stages, slo = meta["stages"], meta["slo_ms"]
    modes = [m for m in MODE_LABEL if any(m in s[1] for s in stages)]
    L = ["# E2 on AURORA: from development staff to a community service", "",
         f"Seeds per arm: {', '.join(f'{a} {len(runs[a])}' for a in arms)}. Stages of {meta['stage_s']:.0f} s, "
         f"each announced {meta['gap_s']:.0f} s ahead; {meta['pool']} pooled connections serve all users.", ""]
    # 1. share of user actions over their mode's latency target, per stage
    L += ["## Share of user actions over their latency target, per stage (%; mean over seeds)", "",
          "| Stage | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for si, (sname, users, ws) in enumerate(stages):
        cells = []
        for a in arms:
            v = [100 * np.mean([x["ms"] > slo[x["mode"]] for x in r["actions"] if x["stage"] == si])
                 for r in runs[a]]
            cells.append(f"{np.mean(v):.1f}" + (f" ± {np.std(v):.1f}" if len(v) > 1 else ""))
        L.append(f"| {sname} ({sum(users.values())} users, writes x{ws:g}) | " + " | ".join(cells) + " |")
    # 2. first 15 s after each stage starts
    L += ["", "## First 15 s of each stage: actions over target (count; mean over seeds)", "",
          "| Stage | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for si, (sname, _, _) in enumerate(stages):
        cells = []
        for a in arms:
            v = []
            for r in runs[a]:
                t0 = stage_start(r["meta"], si)
                v.append(sum(x["ms"] > slo[x["mode"]] for x in r["actions"] if x["stage"] == si and x["t"] - t0 < 15))
            cells.append(f"{np.mean(v):.0f}")
        L.append(f"| {sname} | " + " | ".join(cells) + " |")
    # 3. p95 per mode in the last stage (year 4) and across all stages
    last = len(stages) - 1
    L += ["", f"## 95th-percentile latency per user mode, stage '{stages[last][0]}' (ms; target in brackets)", "",
          "| User mode | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for m in modes:
        cells = [f"{np.mean([p95([x['ms'] for x in r['actions'] if x['stage'] == last and x['mode'] == m]) for r in runs[a]]):.1f}"
                 for a in arms]
        L.append(f"| {MODE_LABEL[m]} ({slo[m]}) | " + " | ".join(cells) + " |")
    L += ["", "## 95th-percentile latency per user mode over the whole run (ms)", "",
          "| User mode | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for m in modes:
        cells = [f"{np.mean([p95([x['ms'] for x in r['actions'] if x['mode'] == m]) for r in runs[a]]):.1f}"
                 for a in arms]
        L.append(f"| {MODE_LABEL[m]} | " + " | ".join(cells) + " |")
    # 4. writes and index space
    L += ["", "## Writes (one tile plus its flakes) and index space", "",
          "| | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    L.append("| write p95 (ms) | " + " | ".join(
        f"{np.mean([p95([w['ms'] for w in r['writes']]) for r in runs[a]]):.1f}" for a in arms) + " |")
    L.append("| tiles written per run | " + " | ".join(
        f"{np.mean([len(r['writes']) for r in runs[a]]):.0f}" for a in arms) + " |")
    L.append("| crystallite secondary indexes at end (MB) | " + " | ".join(
        f"{np.mean([sum(size.get(i, 0) for i in r['meta']['final_indexes']) for r in runs[a]]):.0f}" for a in arms) + " |")
    L.append("| user actions served | " + " | ".join(
        f"{np.mean([len(r['actions']) for r in runs[a]]):.0f}" for a in arms) + " |")
    L += ["", "## Index actions (first seed)", ""]
    for a in arms:
        ev = runs[a][0]["events"]
        L.append(f"- {LABEL[a]}: {sum(e['action'] == 'build' for e in ev)} builds, "
                 f"{sum(e['action'] == 'drop' for e in ev)} drops; final set: "
                 f"{', '.join(runs[a][0]['meta']['final_indexes'])}")
        for e in ev:
            L.append(f"  - t={e['t']:.0f} s {e['action']} {e['index']} ({e['why']})")
    (OUT / "e2_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    fig(runs, arms, meta)


def fig(runs, arms, meta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8})
    col = {"production": "#7f7f7f", "history": "#d95f02", "plan": "#1b9e77"}
    stages, slo = meta["stages"], meta["slo_ms"]
    T = (meta["gap_s"] + meta["stage_s"]) * len(stages)
    grid = np.arange(0, T, 1.0)
    short = ["today\n(staff)", "beta\n(pilot users)", "user service\n(workshop)", "year 4\n(20 % of US groups)"]
    f, ax = plt.subplots(figsize=(6.8, 2.9))
    for si in range(len(stages)):
        s = stage_start(meta, si)
        ax.axvspan(s - meta["gap_s"], s, color="0.92", lw=0)
        ax.text(s + meta["stage_s"] / 2, 1.02, short[si] if si < len(short) else stages[si][0],
                transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=7)
    for a in arms:
        curves = []
        for r in runs[a]:
            t = np.array([x["t"] for x in r["actions"]])
            ratio = np.array([x["ms"] / slo[x["mode"]] for x in r["actions"]])
            curves.append([100 * np.mean(ratio[(t >= g - 3) & (t < g + 3)] > 1) if np.any((t >= g - 3) & (t < g + 3))
                           else np.nan for g in grid])
        c = np.array(curves)
        ax.plot(grid, np.nanmean(c, axis=0), color=col[a], lw=1.2, label=LABEL[a])
        if len(c) > 1:
            ax.fill_between(grid, np.nanpercentile(c, 25, axis=0), np.nanpercentile(c, 75, axis=0), color=col[a], alpha=0.2, lw=0)
    ax.set_xlabel("time (s); grey = stage announced, users not yet arrived")
    ax.set_ylabel("user actions over their\nlatency target, 6 s window (%)\n(mean; band = quartiles)")
    ax.set_xlim(0, T)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    f.tight_layout()
    f.savefig(OUT / "fig_e2_users.png", dpi=200)


if __name__ == "__main__":
    main()
