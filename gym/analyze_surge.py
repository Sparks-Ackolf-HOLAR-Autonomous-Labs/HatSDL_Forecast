"""Tables, paired tests and figure for E4b (surge of unknown size) from results/aurora/e4b/e4b_surge_s*.json."""
import glob
import json
from pathlib import Path

import numpy as np

from gym.stats_tests import holm, paired

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results" / "aurora" / "e4b"
ARMS = ["static51", "static", "static33", "reactive", "forecast"]
FIXED = ["static51", "static", "static33"]
LABEL = {"static51": "fixed split 5:1", "static": "fixed split 4:2 (E4)", "static33": "fixed split 3:3",
         "reactive": "reactive (history)", "forecast": "self-driving (plan + forecast)"}
COL = {"static51": "#1f3f66", "static": "#4c78a8", "static33": "#9ecae9", "reactive": "#f58518",
       "forecast": "#54a24b"}
MK = {"static51": "v", "static": "s", "static33": "^", "reactive": "D", "forecast": "o"}
SPAN = {"surge": 40.0, "workshop": 50.0}
PEOPLE_FAIL = 1.0   # % of people's actions over target in a phase (the E2b pass rule)


def load():
    runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(OUT / "e4b_surge_s*.json")))]
    return [r for r in runs if all(a in r["arms"] for a in ARMS)]


def metrics(s):
    """One arm of one seed, over the surge and workshop phases together."""
    ph = [s["surge"], s["workshop"]]
    n = sum(p["people_n"] for p in ph)
    over = 100 * sum(p["people_over"] * p["people_n"] for p in ph) / max(1, n)
    worst = max(100 * p["people_over"] for p in ph)
    rs = [p["modes"].get("research", {}) for p in ph]
    rn = sum(x.get("n", 0) for x in rs)
    research = 100 * sum(x.get("over", 0) * x.get("n", 0) for x in rs) / max(1, rn)
    llm = [p["llm_added_s_p95"] for p in ph if p["llm_added_s_p95"] is not None]
    s1 = sum(p["script_served_per_s"] * (1 - p["script_over"]) * SPAN[k]
             for k, p in zip(("surge", "workshop"), ph)) / sum(SPAN.values())
    return dict(people_over=over, people_worst=worst, research_over=research,
                llm_added=max(llm) if llm else float("nan"), script_1s=s1,
                left=sum(s["undrained"].values()), dropped=s.get("dropped", 0))


def main():
    runs = load()
    n = len(runs)
    M = {a: {r["seed"]: metrics(r["arms"][a]) for r in runs} for a in ARMS}
    size = {r["seed"]: (r["research"], r["scripts"]) for r in runs}
    L = [f"# E4b: surge of unknown size, {n} seeds", "",
         "Each seed draws an unannounced burst of research users (log-uniform 100-2,400) and a script surge "
         "(log-uniform 25-1,200), the same for every arm of the seed. Values cover the surge and workshop "
         "phases together. Mean [min-max] over seeds.", ""]

    def f(v, d=1):
        v = [x for x in v if np.isfinite(x)]
        return f"{np.mean(v):.{d}f} [{min(v):.{d}f}-{max(v):.{d}f}]" if v else "n/a"

    L += ["| Arm | people over target (%) | research users over target (%) | seeds with people over 1 % in a phase "
          "| added to agent decision, p95 (s) | scripts answered within 1 s (per s) | scripts still queued at end |",
          "|---|---|---|---|---|---|---|"]
    for a in ARMS:
        v = M[a].values()
        fail = sum(x["people_worst"] > PEOPLE_FAIL for x in v)
        L.append(f"| {LABEL[a]} | {f([x['people_over'] for x in v])} | {f([x['research_over'] for x in v])} | "
                 f"{fail}/{n} | {f([x['llm_added'] for x in v], 2)} | {f([x['script_1s'] for x in v])} | "
                 f"{f([x['left'] for x in v], 0)} |")
    # best fixed split in hindsight per seed: fewest people over target, then most scripts within 1 s
    best = {s: min(FIXED, key=lambda a: (round(M[a][s]["people_over"], 1), -M[a][s]["script_1s"])) for s in size}
    L += ["", "## Best fixed split chosen with hindsight, per seed", "",
          "Fewest people's actions over target, ties broken by scripts answered within 1 s.", "",
          "| Fixed split | seeds where it was best |", "|---|---|"]
    for a in FIXED:
        L.append(f"| {LABEL[a]} | {sum(b == a for b in best.values())} |")
    sd = {"people_over": {}, "script_1s": {}}
    for s in size:
        for k in sd:
            sd[k][s] = M[best[s]][s][k]
    L += ["", f"Self-driving vs the hindsight-best fixed split: people over target {np.mean([M['forecast'][s]['people_over'] for s in size]):.2f} % "
          f"vs {np.mean(list(sd['people_over'].values())):.2f} %; scripts within 1 s {np.mean([M['forecast'][s]['script_1s'] for s in size]):.1f} "
          f"vs {np.mean(list(sd['script_1s'].values())):.1f} per s.", ""]
    # paired tests, self-driving against every other arm
    recs = []
    for b in ARMS[:-1]:
        for k, name in (("people_over", "people over target (%)"), ("llm_added", "added to agent decision (s)"),
                        ("script_1s", "scripts within 1 s (per s)")):
            recs.append(paired(f"E4b {name}", "forecast", b, {s: M["forecast"][s][k] for s in size},
                               {s: M[b][s][k] for s in size}))
    for k, name in (("people_over", "people over target (%)"), ("script_1s", "scripts within 1 s (per s)")):
        recs.append(paired(f"E4b {name}", "forecast", "hindsight-best fixed",
                           {s: M["forecast"][s][k] for s in size}, sd[k]))
    holm(recs)
    L += ["## Paired tests (Wilcoxon signed-rank by seed, Holm-corrected over these comparisons)", "",
          "| Measure | Self-driving vs | median diff [95 % CI] | seeds where self-driving is lower | p (Holm) |",
          "|---|---|---|---|---|"]
    for r in recs:
        b = LABEL.get(r["b"], r["b"])
        L.append(f"| {r['test'][4:]} | {b} | {r['median_diff']:.3g} [{r['ci95'][0]:.3g}, {r['ci95'][1]:.3g}] | "
                 f"{r['a_lower_in']}/{r['n']} (ties {r['ties']}) | {r['p_holm']:.2g} |")
    L += ["", "## Per seed", "", "| seed | research burst | script surge | " +
          " | ".join(f"{LABEL[a]}: people % / scripts 1 s" for a in ARMS) + " |", "|---|---|---|" + "---|" * len(ARMS)]
    for s in sorted(size):
        L.append(f"| {s} | {size[s][0]} | {size[s][1]} | " +
                 " | ".join(f"{M[a][s]['people_over']:.1f} / {M[a][s]['script_1s']:.0f}" for a in ARMS) + " |")
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    (OUT / "stats.json").write_text(json.dumps(recs, indent=1))
    print("\n".join(L[:40]))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.7))
    seeds = sorted(size)
    for a in ARMS:
        ax[0].scatter([size[s][0] for s in seeds], [max(M[a][s]["people_over"], 0.01) for s in seeds], s=14,
                      marker=MK[a], color=COL[a], edgecolor="white", linewidth=0.5, label=LABEL[a], zorder=3)
        ax[1].scatter([size[s][1] for s in seeds], [M[a][s]["script_1s"] for s in seeds], s=14,
                      marker=MK[a], color=COL[a], edgecolor="white", linewidth=0.5, zorder=3)
    ax[0].axhline(PEOPLE_FAIL, color="#888888", lw=0.8, ls="--", zorder=1)
    ax[0].set_xscale("log")
    ax[0].set_yscale("log")
    ax[0].set_xlabel("unannounced research-user burst (users)", fontsize=7)
    ax[0].set_ylabel("people's actions over target (%)", fontsize=7)
    ax[1].set_xscale("log")
    ax[1].set_xlabel("unannounced script surge (scripts)", fontsize=7)
    ax[1].set_ylabel("script requests answered\nwithin 1 s (requests/s)", fontsize=7)
    for k in range(2):
        ax[k].tick_params(labelsize=7)
        ax[k].grid(alpha=0.25, lw=0.5)
        ax[k].text(-0.22, 1.04, "(" + "ab"[k] + ")", transform=ax[k].transAxes, fontsize=8, fontweight="bold")
    h, lab = ax[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=3, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(OUT / "fig_e4b_surge.png", dpi=200)


if __name__ == "__main__":
    main()
