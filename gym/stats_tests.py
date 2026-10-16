"""Paired hypothesis tests over seeds for the paper (E1, E2, E4).

Each seed fixes the random arrivals of one run, and every arm of an experiment ran with the same seeds, so the
arms are compared seed by seed: two-sided Wilcoxon signed-rank test on the paired values, Holm correction over all
tests in this file, and a 95 % percentile-bootstrap interval (10,000 resamples of seeds) on the median paired
difference. E1 is read from its per-run statistics (results/aurora/e1a_run_stats.json, gym/e1_run_stats.py),
because the raw E1 files of seeds 4-30 (516 MB) are not kept with the code. A Mann-Whitney U
test checks that seeds 1-3 (run alone) and seeds 4-30 (run in parallel lanes) can be pooled.

    python -m gym.stats_tests            # writes results/aurora/stats_tests.md and .json
"""
from __future__ import annotations

import glob
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from gym import e1_run_stats

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora"
RNG = np.random.default_rng(0)


def load_gz(pattern):
    runs = defaultdict(dict)
    for f in sorted(glob.glob(str(OUT / pattern))):
        r = json.loads(gzip.decompress(Path(f).read_bytes()))
        runs[r["meta"]["arm"]].setdefault(r["meta"]["seed"], r)
    return runs


def e1_metrics(s):
    """s: per-run statistics from gym.e1_run_stats (raw E1 files of seeds 4-30 are not kept with the code)."""
    out = {"p95": s["p95"]}
    for act in ("review", "plan"):
        ready = s["event"][act]["ready_s"]
        out[f"ready_{act}"] = np.nan if ready is None else ready
        out[f"slow15_{act}"] = float(s["event"][act]["slow15"])
    return out


def e2_metrics(r):
    slo = r["meta"]["slo_ms"]
    return {f"over_stage{si}": 100 * float(np.mean([x["ms"] > slo[x["mode"]] for x in r["actions"] if x["stage"] == si]))
            for si in range(len(r["meta"]["stages"]))}


def e4_metrics(arm):
    out = {}
    for p in ("surge", "workshop"):
        s = arm[p]
        out[f"people_over_{p}"] = 100 * s["people_over"]
        out[f"agent_added_{p}"] = s["llm_added_s_p95"]
        out[f"script_1s_{p}"] = s["script_served_per_s"] * (1 - s["script_over"])
    return out


def paired(name, a_label, b_label, a, b):
    """a, b: dict seed -> value. Returns a test record (difference = a - b)."""
    seeds = sorted(s for s in set(a) & set(b) if np.isfinite(a[s]) and np.isfinite(b[s]))
    x, y = np.array([a[s] for s in seeds]), np.array([b[s] for s in seeds])
    d = x - y
    rec = {"test": name, "a": a_label, "b": b_label, "n": len(seeds),
           "median_a": float(np.median(x)), "median_b": float(np.median(y)),
           "median_diff": float(np.median(d)), "a_lower_in": int(np.sum(d < 0)), "ties": int(np.sum(d == 0))}
    boot = [np.median(d[RNG.integers(0, len(d), len(d))]) for _ in range(10000)]
    rec["ci95"] = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    rec["p"] = float(stats.wilcoxon(x, y).pvalue) if np.any(d != 0) else 1.0
    return rec


def holm(recs):
    order = np.argsort([r["p"] for r in recs])
    m, running = len(recs), 0.0
    for k, i in enumerate(order):
        running = max(running, min(1.0, (m - k) * recs[i]["p"]))
        recs[i]["p_holm"] = running
    return recs


def main():
    recs, pool = [], []
    e1 = e1_run_stats.load()
    v1 = {a: {s: e1_metrics(r) for s, r in e1[a].items()} for a in e1}
    for key, lab in [("p95", "E1 95th pct over the day (ms)"), ("ready_review", "E1 time to ready, review (s)"),
                     ("ready_plan", "E1 time to ready, stacking (s)"), ("slow15_review", "E1 slow calls first 15 s, review"),
                     ("slow15_plan", "E1 slow calls first 15 s, stacking")]:
        recs.append(paired(lab, "plan-aware", "history", {s: v[key] for s, v in v1["plan"].items()},
                           {s: v[key] for s, v in v1["history"].items()}))
    recs.append(paired("E1 95th pct over the day (ms)", "plan-aware", "production",
                       {s: v["p95"] for s, v in v1["plan"].items()}, {s: v["p95"] for s, v in v1["production"].items()}))
    for a in v1:
        early = [v["p95"] for s, v in v1[a].items() if s <= 3]
        late = [v["p95"] for s, v in v1[a].items() if s > 3]
        pool.append({"exp": "E1", "arm": a, "n_alone": len(early), "n_lanes": len(late),
                     "median_alone": float(np.median(early)), "median_lanes": float(np.median(late)),
                     "p": float(stats.mannwhitneyu(early, late).pvalue)})
    e2 = load_gz("e2_*_s*.json.gz")
    v2 = {a: {s: e2_metrics(r) for s, r in e2[a].items()} for a in e2}
    stages = [st[0] for st in next(iter(e2["plan"].values()))["meta"]["stages"]]
    for si, sname in enumerate(stages):
        k = f"over_stage{si}"
        for b in ("history", "production"):
            recs.append(paired(f"E2 actions over target, {sname} (%)", "plan-aware", b,
                               {s: v[k] for s, v in v2["plan"].items()}, {s: v[k] for s, v in v2[b].items()}))
    for a in v2:
        early = [v["over_stage0"] for s, v in v2[a].items() if s <= 3]
        late = [v["over_stage0"] for s, v in v2[a].items() if s > 3]
        pool.append({"exp": "E2 (stage 1)", "arm": a, "n_alone": len(early), "n_lanes": len(late),
                     "median_alone": float(np.median(early)), "median_lanes": float(np.median(late)),
                     "p": float(stats.mannwhitneyu(early, late).pvalue)})
    e4 = {}
    for f in sorted(glob.glob(str(OUT / "e4_admission_s*.json"))):
        r = json.loads(Path(f).read_text())
        if all(a in r["arms"] for a in ("shared", "static", "reactive", "forecast")):
            e4[r.get("seed", int(Path(f).stem.split("_s")[-1]))] = {a: e4_metrics(r["arms"][a]) for a in r["arms"]}
    for key, lab in [("people_over_surge", "E4 people over target, surge (%)"),
                     ("people_over_workshop", "E4 people over target, workshop (%)"),
                     ("agent_added_surge", "E4 time added to agent decision, surge (s)"),
                     ("agent_added_workshop", "E4 time added to agent decision, workshop (s)"),
                     ("script_1s_surge", "E4 script requests within 1 s, surge (per s)")]:
        for b in ("reactive", "static"):
            recs.append(paired(lab, "self-driving", b, {s: v["forecast"][key] for s, v in e4.items()},
                               {s: v[b][key] for s, v in e4.items()}))
    holm(recs)
    (OUT / "stats_tests.json").write_text(json.dumps({"tests": recs, "pooling": pool}, indent=1))
    L = ["# Paired tests over seeds", "",
         "Two-sided Wilcoxon signed-rank test on values paired by seed; Holm correction over all rows; 95 % "
         "percentile-bootstrap interval of the median paired difference (a - b), 10,000 resamples.", "",
         "| Quantity | a | b | n | median a | median b | median diff [95 % CI] | seeds a < b | p (Holm) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        L.append(f"| {r['test']} | {r['a']} | {r['b']} | {r['n']} | {r['median_a']:.3g} | {r['median_b']:.3g} | "
                 f"{r['median_diff']:.3g} [{r['ci95'][0]:.3g}, {r['ci95'][1]:.3g}] | {r['a_lower_in']} | "
                 f"{r['p_holm']:.2g} |")
    L += ["", "## Pooling check: seeds 1-3 (run alone) against seeds 4-30 (parallel lanes), Mann-Whitney U", "",
          "| Experiment | Arm | n alone | n lanes | median alone | median lanes | p |", "|---|---|---|---|---|---|---|"]
    for p in pool:
        L.append(f"| {p['exp']} | {p['arm']} | {p['n_alone']} | {p['n_lanes']} | {p['median_alone']:.3g} | "
                 f"{p['median_lanes']:.3g} | {p['p']:.2g} |")
    (OUT / "stats_tests.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
