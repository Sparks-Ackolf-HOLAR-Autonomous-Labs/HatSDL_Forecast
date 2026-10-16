#!/usr/bin/env python3
"""Fig. 4: where an agent's decision time goes, for the five agent configurations of Table 2.

Data: results/aurora_agents/e3_A.jsonl (specialist, local Qwen3.5-9B, tools in-process),
e3_A-V.jsonl (the same with a tile image), e3_B.jsonl (generic agent, own SQL, local),
and, for the hosted model (Claude Opus 5.5) over the REST interface, the decision start/end marks
e3b_claude_marks.jsonl with the server log e3b_rest_log.jsonl, split as in gym/analyze_byo.py
(database = SQL execution time, interface = REST server time beyond SQL plus 1.5 ms per request,
model = the rest, which for the hosted model includes the network round trip to its gateway).
(a) median decision time split into model, interface and database time in proportion to the
mean shares of each configuration; (b) database and interface time as a share of each decision,
one point per decision, bar = median, logarithmic axis.
Takeaway: with a local model the database is under 0.3 % of a decision; a faster hosted model
raises that share about tenfold, so the database objective changes with the agent.
Style: paper_fig_style, drawn at the DCE text width (144 mm) at print size.
"""
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paper_fig_style import DCE_FULL, INK, apply_style, save  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = HERE.parents[1]
D = ROOT / "results" / "aurora_agents"
OUT = HERE.parent / "figures" / "fig_agents.png"
PART_COL = {"model": "#BBBBBB", "interface": "#56B4E9", "database": "#D55E00"}


def jl(name):
    return [json.loads(x) for x in (D / name).read_text().splitlines() if x.strip()]


def local(name):
    return [{"total": r["t_total"], "db": r["t_db"], "http": r["t_tool_other"],
             "model": r["t_total"] - r["t_db"] - r["t_tool_other"]} for r in jl(name)]


def hosted():
    marks, log = jl("e3b_claude_marks.jsonl"), jl("e3b_rest_log.jsonl")
    dec = {}
    for m in marks:
        dec.setdefault((m["case"], m["task"]), {})[m["event"]] = m["t"]
    out = {"A": [], "B": []}
    for (case, task), ev in dec.items():
        reqs = [x for x in log if x["client"] == f"claude-{case}-{task}" and ev["start"] <= x["t"] <= ev["end"]]
        db = sum((x["db_ms"] or 0) for x in reqs) / 1000
        srv = sum(x["server_ms"] for x in reqs) / 1000
        total = ev["end"] - ev["start"]
        http = srv - db + 0.0015 * len(reqs)
        out[case].append({"total": total, "db": db, "http": http, "model": total - db - http})
    return out


def main():
    apply_style()
    h = hosted()
    rows = [("specialist, local 9B model", local("e3_A.jsonl")),
            ("specialist + tile image, local", local("e3_A-V.jsonl")),
            ("generic, own SQL, local 9B model", local("e3_B.jsonl")),
            ("specialist, hosted model, REST", h["A"]),
            ("generic, hosted model, REST", h["B"])]
    fig, (a, b) = plt.subplots(1, 2, figsize=(DCE_FULL, 2.5), width_ratios=[1.25, 1], sharey=True)
    y = np.arange(len(rows))[::-1]
    rng = np.random.default_rng(0)
    for yi, (name, rs) in zip(y, rows):
        med = st.median(r["total"] for r in rs)
        tot = sum(r["total"] for r in rs)
        left = 0.0
        for part, key in (("model", "model"), ("interface", "http"), ("database", "db")):
            w = med * sum(r[key] for r in rs) / tot
            a.barh(yi, w, left=left, height=0.6, color=PART_COL[part], label=part if yi == y[0] else None,
                   edgecolor="white" if part == "model" else PART_COL[part], lw=0.3)
            left += w
        a.text(med + 0.8, yi, f"{med:.1f} s", va="center", fontsize=7)
        share = [100 * (r["db"] + r["http"]) / r["total"] for r in rs]
        b.scatter(share, yi + rng.uniform(-0.15, 0.15, len(share)), s=9, color=PART_COL["database"],
                  alpha=0.7, lw=0)
        b.plot([st.median(share)] * 2, [yi - 0.3, yi + 0.3], color=INK, lw=1.3)
        print(name, len(rs), f"median {med:.1f} s, share median {st.median(share):.2f} %")
    a.set_yticks(y, [n for n, _ in rows])
    a.set_xlabel("median decision time (s)")
    a.set_xlim(0, 70)
    a.legend(loc="lower right", fontsize=6.5, handlelength=1.2)
    a.grid(axis="y", visible=False)
    b.set_xscale("log")
    b.set_xlim(0.005, 30)
    b.set_xticks([0.01, 0.1, 1, 10], ["0.01", "0.1", "1", "10"])
    b.set_xlabel("database and interface share\nof each decision (%)")
    b.grid(axis="y", visible=False)
    for k, ax in enumerate((a, b)):
        ax.set_title(f"({'ab'[k]})", loc="left", fontsize=9, fontweight="bold")
    save(fig, OUT)


if __name__ == "__main__":
    main()
