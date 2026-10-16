"""E3b tables and figure: bring-your-own-LLM agents over the open REST API, against E3's in-process tools.

Inputs (results/aurora_agents/):
  e3_A.jsonl, e3_B.jsonl            E3: local Qwen3.5-9B, tools in-process
  e3_A_rest.jsonl, e3_B_rest.jsonl  E3b: the same agent loop, tools over the REST API
  e3b_claude_marks.jsonl            E3b: Claude (Opus 5.5 in Claude Code on the DGX) driving the REST API by curl;
                                    decision start/end marks
  e3b_rest_log.jsonl                server log of the REST API (one line per request, client tag)
    python -m gym.analyze_byo
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

D = Path(__file__).resolve().parent.parent / "results" / "aurora_agents"


def jl(p):
    p = D / p
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def qwen(file):
    out = []
    for r in jl(file):
        if r.get("task") == "tile" and r["case"] == "A-V":
            continue
        out.append({"task": r["task"], "total": r["t_total"], "model": r["t_model"], "db": r["t_db"],
                    "http": r["t_tool_other"], "turns": r["n_turns"], "tokens": r["completion_tokens"],
                    "ok": r["finished"]})
    return out


def claude():
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
        turns = len(reqs) + 1  # one model turn before each request, one for the answer
        out[case].append({"task": task, "total": total, "db": db, "http": srv - db + 0.0015 * len(reqs),
                          "model": total - srv - 0.0015 * len(reqs), "turns": turns, "ok": True})
    return out


def med(xs):
    return st.median(xs) if xs else float("nan")


def row(name, rs):
    if not rs:
        return f"| {name} | 0 | | | | | | |"
    tot = [r["total"] for r in rs]
    per_turn = [r["model"] / r["turns"] for r in rs]
    share = [100 * (r["db"] + r["http"]) / r["total"] for r in rs]
    return (f"| {name} | {len(rs)} | {med(tot):.1f} | {min(tot):.1f}-{max(tot):.1f} | {med([r['turns'] for r in rs]):.0f} | "
            f"{med(per_turn):.1f} | {1000*med([r['db'] for r in rs]):.0f} / {1000*med([r['http'] for r in rs]):.1f} | "
            f"{med(share):.2f} |")


def main():
    c = claude()
    arms = [
        ("a: Qwen3.5-9B on DGX, tools in-process (E3)", qwen("e3_A.jsonl")),
        ("a: Qwen3.5-9B on DGX, REST API", qwen("e3_A_rest.jsonl")),
        ("a: Claude Opus 5.5 (hosted), REST API", c["A"]),
        ("b: Qwen3.5-9B on DGX, skills + SQL in-process (E3)", qwen("e3_B.jsonl")),
        ("b: Qwen3.5-9B on DGX, API guide + SQL over REST", qwen("e3_B_rest.jsonl")),
        ("b: Claude Opus 5.5 (hosted), API guide + SQL over REST", c["B"]),
    ]
    net = json.loads((D / "e3b_network.json").read_text())
    bench = json.loads((D / "e3b_rest_bench.json").read_text())
    lines = ["| Agent | Decisions | Median (s) | Range (s) | Model turns | Model time per turn (s) | "
             "Database / HTTP, median (ms) | Database + HTTP share (%) |",
             "|---|---|---|---|---|---|---|---|"] + [row(n, rs) for n, rs in arms]
    lines += ["", "| REST overhead (200 calls each) | In-process (ms) | Over HTTP (ms) | HTTP p95 (ms) |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['direct_median_ms']:.2f} | {v['http_median_ms']:.2f} | {v['http_p95_ms']:.2f} |"
              for k, v in bench.items()]
    lines += ["", "| Round trip from the DGX (20 requests, no credentials) | Median (ms) | TLS done (ms) |", "|---|---|---|"]
    lines += [f"| {k} | {1000*med([x['total'] for x in v]):.1f} | {1000*med([x['tls'] for x in v]):.1f} |"
              for k, v in net.items()]
    (D / "e3b_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    fig, ax = plt.subplots(figsize=(6.8, 3.0))
    labels = ["Qwen, in-process", "Qwen, REST", "Claude, REST"] * 2
    for i, (_, rs) in enumerate(arms):
        y = len(arms) - 1 - i
        xs = [r["total"] for r in rs]
        col = "#3b6ea8" if "Claude" in arms[i][0] else "#8a8a8a"
        ax.scatter(xs, [y] * len(xs), s=14, color=col, alpha=0.7, zorder=3)
        if xs:
            ax.plot([med(xs)] * 2, [y - 0.3, y + 0.3], color="black", lw=1.5, zorder=4)
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels(labels[::-1], fontsize=8)
    ax.axhline(2.5, color="#cccccc", lw=0.8)
    ax.text(0.01, 0.97, "a: specialist tools", transform=ax.transAxes, ha="left", va="top", fontsize=8)
    ax.text(0.01, 0.45, "b: generic, discovers the API", transform=ax.transAxes, ha="left", va="top", fontsize=8)
    ax.set_xscale("log")
    ax.set_xlim(1, 120)
    ax.set_xticks([1, 2, 5, 10, 20, 50, 100])
    ax.set_xticklabels(["1", "2", "5", "10", "20", "50", "100"])
    ax.set_xlabel("Decision time, question to answer (s)", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(axis="x", color="#eeeeee", zorder=0)
    fig.tight_layout()
    fig.savefig(D / "fig_e3b_byo.png", dpi=200)


if __name__ == "__main__":
    main()
