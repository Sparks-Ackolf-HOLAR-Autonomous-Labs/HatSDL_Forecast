"""Compact E1 latency curves for the paper figure (all 30 seeds).

The raw E1 run files of seeds 4-30 (516 MB) are archived with the Zenodo release; seeds 1-3 are in
results/aurora/. This script reduces every run to the curve the figure draws:
95th-percentile decision latency in a 6 s window centred on each whole second
of the scripted day, one curve per tuner and seed, and writes
results/aurora/e1a_curves.json (committed).

    python -m gym.e1_curves [extra raw folder ...]
"""
from __future__ import annotations

import glob
import gzip
import json
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora"


def main():
    dirs = [OUT] + [Path(p) for p in sys.argv[1:]]
    runs = {}
    for d in dirs:
        for f in sorted(glob.glob(str(d / "e1a_*_s*.json.gz"))):
            r = json.loads(gzip.decompress(Path(f).read_bytes()))
            runs[(r["meta"]["arm"], r["meta"]["seed"])] = r
    meta = next(iter(runs.values()))["meta"]
    T = (meta["gap_s"] + meta["phase_s"]) * len(meta["phases"])
    grid = np.arange(0, T, 1.0)
    curves = {}
    for (arm, seed), r in sorted(runs.items()):
        t = np.array([x["t"] for x in r["decisions"]])
        ms = np.array([x["ms"] for x in r["decisions"]])
        c = []
        for g in grid:
            m = (t >= g - 3) & (t < g + 3)
            c.append(round(float(np.percentile(ms[m], 95)), 3) if m.any() else None)
        curves.setdefault(arm, {})[str(seed)] = c
    doc = {"what": "95th-percentile decision latency (ms) in a 6 s window centred on each grid second",
           "grid_s": grid.tolist(),
           "meta": {k: meta[k] for k in ("phases", "phase_s", "gap_s")},
           "seeds": {a: sorted(int(s) for s in v) for a, v in curves.items()},
           "curves": curves}
    (OUT / "e1a_curves.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print({a: len(v) for a, v in curves.items()})


if __name__ == "__main__":
    main()
