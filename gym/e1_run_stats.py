"""Per-run statistics of E1 (results/aurora/e1a_run_stats.json), the input of the E1 tables and tests.

The raw run files (e1a_<arm>_s<seed>.json.gz) hold every decision; those of seeds 4-30 total 516 MB and
are not kept with the code. This file keeps, per run, every number gym/analyze_aurora.py and
gym/stats_tests.py use, so both rebuild their E1 tables and tests without the raw files.

    python -m gym.e1_run_stats [extra raw folder ...]    # raw files in results/aurora plus extra folders
"""
from __future__ import annotations

import glob
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora"
STATS = OUT / "e1a_run_stats.json"
SLOW_MS = 50.0
EVENT_ACTION = {1: "review", 2: "plan"}  # phase index -> the action that phase introduces


def stats(r: dict) -> dict:
    m = r["meta"]
    dec = r["decisions"]
    ms = np.array([x["ms"] for x in dec])
    out = {"meta": {k: m[k] for k in ("arm", "seed", "phases", "phase_s", "gap_s", "final_indexes")},
           "median": float(np.median(ms)), "p95": float(np.percentile(ms, 95)), "p99": float(np.percentile(ms, 99)),
           "slow_pct": float(100 * np.mean(ms > SLOW_MS)), "n": int(len(ms)),
           "phase_p95": [], "phase_n": [], "action_p95": {}, "event": {},
           "builds": sum(e["action"] == "build" for e in r["events"]),
           "drops": sum(e["action"] == "drop" for e in r["events"])}
    for pi in range(len(m["phases"])):
        v = [x["ms"] for x in dec if x["phase"] == pi]
        out["phase_p95"].append(float(np.percentile(v, 95)))
        out["phase_n"].append(len(v))
    by = defaultdict(list)
    for x in dec:
        by[x["action"]].append(x["ms"])
    out["action_p95"] = {k: float(np.percentile(v, 95)) for k, v in by.items()}
    for pi, act in EVENT_ACTION.items():
        t0 = m["gap_s"] * (pi + 1) + m["phase_s"] * pi
        d = [x for x in dec if x["phase"] == pi and x["action"] == act]
        first = min([x["t"] - t0 for x in d if x["ms"] < 1], default=None)
        out["event"][act] = {"slow15": int(sum(x["ms"] > 5 and x["t"] - t0 < 15 for x in d)), "ready_s": first}
    return out


def load() -> dict:
    """arm -> {seed: stats}: the committed statistics, overridden by any raw file present."""
    runs = defaultdict(dict)
    if STATS.exists():
        for rec in json.loads(STATS.read_text()):
            runs[rec["meta"]["arm"]][rec["meta"]["seed"]] = rec
    for f in sorted(glob.glob(str(OUT / "e1a_*_s*.json.gz"))):
        r = json.loads(gzip.decompress(Path(f).read_bytes()))
        runs[r["meta"]["arm"]][r["meta"]["seed"]] = stats(r)
    return runs


def main():
    recs = {}
    for d in [OUT] + [Path(p) for p in sys.argv[1:]]:
        for f in sorted(glob.glob(str(d / "e1a_*_s*.json.gz"))):
            r = json.loads(gzip.decompress(Path(f).read_bytes()))
            recs.setdefault((r["meta"]["arm"], r["meta"]["seed"]), stats(r))
    STATS.write_text(json.dumps([recs[k] for k in sorted(recs)], indent=0) + "\n")
    print(f"{len(recs)} runs -> {STATS}")


if __name__ == "__main__":
    main()
