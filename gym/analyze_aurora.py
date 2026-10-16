"""Summarise experiment E1 on AURORA: tables in results/aurora/e1a_summary.md.

Reads the per-run statistics (results/aurora/e1a_run_stats.json, from gym/e1_run_stats.py), so the
tables rebuild without the raw run files; a raw file present in results/aurora is used directly.
The figure of the paper is drawn by paper_figures/regen_figs/fig_e1_latency.py from e1a_curves.json.

    python -m gym.analyze_aurora
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from gym.e1_run_stats import load

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora"
ARMS = ["production", "history", "plan"]
LABEL = {"production": "production index set (fixed)", "history": "history-based tuner",
         "plan": "plan-aware tuner"}


def ms_sd(v):
    return f"{np.mean(v):.1f} ± {np.std(v):.1f}" if len(v) > 1 else f"{np.mean(v):.1f}"


def main():
    by_seed = load()
    runs = {a: [by_seed[a][s] for s in sorted(by_seed[a])] for a in ARMS if by_seed.get(a)}
    arms = [a for a in ARMS if a in runs]
    bm = json.loads((OUT / "behaviour_model.json").read_text())
    size = {k: v["size_mb"] for k, v in bm["indexes"].items()}
    meta = runs[arms[0]][0]["meta"]
    phases = meta["phases"]
    lines = ["# E1 on AURORA: summary", "",
             f"Seeds per arm: {', '.join(f'{a} {len(runs[a])}' for a in arms)}. "
             f"Phases of {meta['phase_s']:.0f} s, each after an announced idle window of {meta['gap_s']:.0f} s.", "",
             "| Tuner | Median (ms) | 95th pct (ms) | 99th pct (ms) | Decisions > 50 ms (%) | Decisions | "
             "Crystallite secondary indexes at end (MB) |", "|---|---|---|---|---|---|---|"]
    per_phase, per_action = defaultdict(dict), defaultdict(dict)
    for a in arms:
        st = defaultdict(list)
        for r in runs[a]:
            st["med"].append(r["median"]); st["p95"].append(r["p95"]); st["p99"].append(r["p99"])
            st["slow"].append(r["slow_pct"]); st["n"].append(r["n"])
            st["mb"].append(sum(size.get(ix, 0) for ix in r["meta"]["final_indexes"]))
            for pi in range(len(phases)):
                per_phase[a].setdefault(pi, []).append((r["phase_p95"][pi], r["phase_n"][pi]))
            for k, v in r["action_p95"].items():
                per_action[a].setdefault(k, []).append(v)
        lines.append(f"| {LABEL[a]} | {ms_sd(st['med'])} | {ms_sd(st['p95'])} | {ms_sd(st['p99'])} | "
                     f"{ms_sd(st['slow'])} | {np.mean(st['n']):.0f} | {np.mean(st['mb']):.0f} |")
    lines += ["", "## 95th-percentile decision latency per phase (ms; decisions completed in brackets)", "",
              "| Phase | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for pi, p in enumerate(phases):
        lines.append(f"| {p} | " + " | ".join(
            f"{np.mean([x[0] for x in per_phase[a][pi]]):.1f} ({np.mean([x[1] for x in per_phase[a][pi]]):.0f})"
            for a in arms) + " |")
    # Cost of a lab event: decisions of the phase's new action slower than 5 ms in the first 15 s, and the
    # time from phase start until that action is first answered in under 1 ms (its index in place).
    main_act = {1: "review", 2: "plan"}
    lines += ["", "## After a lab event: slow decisions of the new action in the first 15 s; time until it is "
              "first served in under 1 ms (mean over seeds)", "",
              "| Phase | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for pi, act in main_act.items():
        cells = []
        for a in arms:
            nslow = [r["event"][act]["slow15"] for r in runs[a]]
            first = [np.nan if r["event"][act]["ready_s"] is None else r["event"][act]["ready_s"] for r in runs[a]]
            f = np.nanmean(first) if np.any(np.isfinite(first)) else np.nan
            cells.append(f"{np.mean(nslow):.0f} slow; " + ("never" if np.isnan(f) else f"{f:.1f} s"))
        lines.append(f"| {phases[pi]} | " + " | ".join(cells) + " |")
    lines += ["", "## 95th-percentile latency per lab action (ms)", "",
              "| Action | " + " | ".join(LABEL[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for k in ["scan", "detect", "review", "plan", "view"]:
        lines.append(f"| {k} | " + " | ".join(f"{np.mean(per_action[a].get(k, [np.nan])):.1f}" for a in arms) + " |")
    lines += ["", "## Index actions per run (first seed)", ""]
    for a in arms:
        r = runs[a][0]
        lines.append(f"- {LABEL[a]}: {r['builds']} builds, {r['drops']} drops; final set: "
                     f"{', '.join(r['meta']['final_indexes'])}")
    (OUT / "e1a_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
