"""Tables and figure for E4 (admission control) from results/aurora/e4_admission_s*.json."""
import glob
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results" / "aurora"
ARMS = ["shared", "static", "reactive", "forecast"]
LABEL = {"shared": "shared pool", "static": "hand-set split", "reactive": "reactive (history)",
         "forecast": "self-driving (plan + forecast)"}
PH = ["before", "surge", "workshop"]


def load():
    runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(OUT / "e4_admission_s*.json")))]
    return [r for r in runs if all(a in r["arms"] for a in ARMS)]


def agg(runs, arm, fn):
    v = [fn(r["arms"][arm]) for r in runs]
    v = [x for x in v if x is not None]
    if not v:
        return None, None, None
    return st.mean(v), min(v), max(v)


def fmt(m, lo, hi, d=1):
    if m is None:
        return "n/a"
    return f"{m:.{d}f} [{lo:.{d}f}-{hi:.{d}f}]"


def main():
    runs = load()
    n = len(runs)
    L = [f"# E4 admission control: {n} seeds (mean [min-max] over seeds)", ""]
    rows = [
        ("People: actions over target (%)", lambda s, p: 100 * s[p]["people_over"], 1),
        ("Workshop students over target (%)", lambda s, p: 100 * s[p]["modes"].get("education", {}).get("over", 0)
         if p == "workshop" else None, 1),
        ("LLM tool call, 95th percentile (ms)", lambda s, p: s[p]["llm_call_p95_ms"], 0),
        ("LLM decision time added by the database, 95th percentile (s)", lambda s, p: s[p]["llm_added_s_p95"], 2),
        ("LLM decision, median (s)", lambda s, p: s[p]["llm_decision_p50_s"], 1),
        ("Database share of LLM decisions (%)", lambda s, p: 100 * s[p]["llm_db_share"], 2),
        ("Scripts served per s", lambda s, p: s[p]["script_served_per_s"], 0),
        ("Script request, 95th percentile (ms)", lambda s, p: s[p]["script_p95_ms"], 0),
        ("Script requests answered within 1 s, per s", lambda s, p: s[p]["script_served_per_s"] * (1 - s[p]["script_over"]), 0),
    ]
    for title, fn, d in rows:
        L += [f"## {title}", "", "| Arm | " + " | ".join(PH) + " |", "|---|" + "---|" * len(PH)]
        for a in ARMS:
            L.append(f"| {LABEL[a]} | " + " | ".join(fmt(*agg(runs, a, lambda s, p=p: fn(s, p)), d) for p in PH) + " |")
        L.append("")
    L += ["## Script requests turned away and left unserved (per run)", "",
          "| Arm | 429 responses | dropped after 4 retries | still queued at the end |", "|---|---|---|---|"]
    for a in ARMS:
        L.append(f"| {LABEL[a]} | {fmt(*agg(runs, a, lambda s: s['throttled']), 0)} | "
                 f"{fmt(*agg(runs, a, lambda s: s.get('dropped', 0)), 0)} | "
                 f"{fmt(*agg(runs, a, lambda s: sum(s['undrained'].values())), 0)} |")
    (OUT / "e4_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.5))
    cols = {"shared": "#9e9e9e", "static": "#4c78a8", "reactive": "#f58518", "forecast": "#54a24b"}
    x = range(len(PH))
    panels = [("people's actions over target (%)", lambda s, p: 100 * s[p]["people_over"]),
              ("time added to an agent\ndecision, 95th percentile (s)", lambda s, p: s[p]["llm_added_s_p95"]),
              ("script requests answered\nwithin 1 s (requests/s)",
               lambda s, p: s[p]["script_served_per_s"] * (1 - s[p]["script_over"]))]
    for k, (t, fn) in enumerate(panels):
        for i, a in enumerate(ARMS):
            m = [agg(runs, a, lambda s, p=p: fn(s, p)) for p in PH]
            ax[k].errorbar([j + (i - 1.5) * 0.15 for j in x], [v[0] for v in m],
                           yerr=[[v[0] - v[1] for v in m], [v[2] - v[0] for v in m]],
                           fmt="o", ms=3, capsize=2, color=cols[a], label=LABEL[a])
        ax[k].set_xticks(list(x), ["before", "script\nsurge", "workshop"], fontsize=7)
        ax[k].set_ylabel(t, fontsize=7)
        ax[k].tick_params(labelsize=7)
        ax[k].text(-0.3, 1.04, "(" + "abc"[k] + ")", transform=ax[k].transAxes, fontsize=8, fontweight="bold")
        if k == 1:
            ax[k].set_yscale("log")
    h, lab = ax[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=4, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / "fig_e4_admission.png", dpi=200)


if __name__ == "__main__":
    main()
