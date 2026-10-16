"""Experiment E3c on AURORA: a complex research question that one agent cannot answer alone.

E3 and E3b timed single questions that one tool call answers. Real community questions span the
whole AURORA loop, the literature and planning, for example:

  "Across all prior AURORA experiments on twisted bilayer graphene, which combinations of source
   material, exfoliation conditions, stacking angle, fabrication parameters and device geometry
   produced the most reproducible signatures of correlated or superconducting phases in cryogenic
   transport; how do those samples relate to similar materials and experiments in the literature;
   and, based on both successful and failed experiments, what five experiments should AURORA run
   next to maximise the probability of a reproducible phase while minimising fabrication time and
   cost?"

Agents (one local model, Qwen3.5-9B on vLLM, with different prompts and tools):
  coordinator  splits the question, asks the specialists (several at once if it wants), writes the answer
  archive      AURORA flake archive: crystals, chips, exfoliation settings, flakes (real copy)
  devices      stacking, device and transport records (schema aurora_next; absent today, simulated projection)
  literature   paper and snippet search through the Asta MCP service (live network calls)
  theory       continuum-model calculator: magic angle, moire period, carrier density at full filling
  planner      ranks candidate next experiments by success probability per hour from the records

Arms:
  single_archive  the E3 specialist alone (only archive tools)
  single_all      one agent holding every tool (no sub-agents)
  team            coordinator + five specialists
Conditions:
  today      AURORA as it is: the stacking/device/transport tables do not exist
  projected  plus the simulated aurora_next schema (gym.aurora_next)
Database modes:
  summary    the self-driving database has built a chip x layer-class aggregate in advance
  raw        flake-yield questions run against the 6.2 M-row flake table under the 15 s limit

    python -m gym.multi_agent run --arm team --cond projected --seeds 1-10 --par 10
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from gym import agent_latency as al

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("E3C_OUT", ROOT / "results" / "aurora_multi"))
# asta_mcp.py (literature tool): next to this file in the public folder, in ../shared in the working tree
sys.path[:0] = [str(Path(__file__).resolve().parent), str(ROOT.parent / "shared")]

QUESTION = (
    "Across all prior AURORA experiments on twisted bilayer graphene, which combinations of source material, "
    "exfoliation conditions, stacking angle, fabrication parameters, and device geometry produced the most "
    "reproducible signatures of correlated or superconducting phases in cryogenic transport measurements; how do "
    "those samples relate to similar materials and experiments in the literature; and, based on both successful "
    "and failed experiments, what five experiments should AURORA run next to maximize the probability of "
    "discovering a reproducible phase while minimizing fabrication time and experimental cost?")
SUB_CHARS = 1800  # a specialist's answer is cut to this many characters before the coordinator sees it


class Ctx:
    """Per-decision settings and timing ledger (thread-safe)."""

    def __init__(self, cond, dbmode, seed):
        self.cond, self.dbmode, self.seed = cond, dbmode, seed
        self.lock = threading.Lock()
        self.t0 = time.perf_counter()
        self.calls = []   # one row per model call
        self.tools = []   # one row per tool call
        self.sql = []     # every statement the database received

    def now(self):
        return time.perf_counter() - self.t0

    def log(self, kind, row):
        with self.lock:
            getattr(self, kind).append(row)


# ------------------------------------------------------------------ tool implementations
NEXT = lambda ctx: "aurora_next" if ctx.cond == "projected" else "aurora_next_not_built"  # noqa: E731


def db(ctx, agent, q, a=None):
    rows, s, err = al.sql(q, a)
    ctx.log("sql", {"agent": agent, "t": ctx.now(), "sql": " ".join(q.split())[:500], "db_s": s, "err": err,
                    "rows": len(rows)})
    return rows, s, err


YIELD_SUMMARY = (
    "SELECT b.material AS source, b.grower, ch.exfoliation_parameters->>'sample_pressure_kpa' AS sample_pressure_kpa, "
    "ch.exfoliation_parameters->>'heat_to_temperature_c' AS heat_to_c, count(DISTINCT ch.chip_id) AS chips, "
    "sum(s.n) AS flakes, sum(s.n) FILTER (WHERE s.classification_ai='monolayer') AS monolayers, "
    "sum(s.n) FILTER (WHERE s.classification_ai='bilayer') AS bilayers "
    "FROM sddb_chip_class_counts s JOIN chip ch USING (chip_id) JOIN bulk_crystal b ON b.bulk_crystal_id=s.bulk_crystal_id "
    "WHERE b.material ILIKE %(m)s GROUP BY 1,2,3,4 ORDER BY monolayers DESC NULLS LAST")
YIELD_RAW = (
    "SELECT b.material AS source, b.grower, ch.exfoliation_parameters->>'sample_pressure_kpa' AS sample_pressure_kpa, "
    "ch.exfoliation_parameters->>'heat_to_temperature_c' AS heat_to_c, count(DISTINCT ch.chip_id) AS chips, "
    "count(*) AS flakes, count(*) FILTER (WHERE cr.classification_ai='monolayer') AS monolayers, "
    "count(*) FILTER (WHERE cr.classification_ai='bilayer') AS bilayers "
    "FROM crystallite cr JOIN chip ch USING (chip_id) JOIN bulk_crystal b ON b.bulk_crystal_id=cr.bulk_crystal_id "
    "WHERE b.material ILIKE %(m)s AND cr.removed_at IS NULL GROUP BY 1,2,3,4 ORDER BY monolayers DESC NULLS LAST")


def t_exfoliation_yield(ctx, agent, material="%graph%"):
    q = YIELD_SUMMARY if ctx.dbmode == "summary" else YIELD_RAW
    rows, s, err = db(ctx, agent, q, {"m": material})
    for r in rows:
        if r.get("chips"):
            r["monolayers_per_chip"] = round((r["monolayers"] or 0) / r["chips"], 1)
    return {"rows": rows[:20], "error": err}, "db", s


GROUPS = {"twist_bin": "round(s.measured_twist_deg::numeric * 20) / 20", "source": "b.material",
          "sample_pressure_kpa": "ch.exfoliation_parameters->>'sample_pressure_kpa'", "method": "s.method",
          "pickup_temp_c": "s.pickup_temp_c", "geometry": "d.geometry", "graphite_gate": "s.graphite_gate"}


def t_reproducibility(ctx, agent, group_by="twist_bin,geometry"):
    keys = [g.strip() for g in str(group_by).split(",") if g.strip() in GROUPS][:3] or ["twist_bin"]
    sel = ", ".join(f"{GROUPS[k]} AS {k}" for k in keys)
    n = NEXT(ctx)
    q = (f"WITH dev AS (SELECT d.device_id, count(*) AS cooldowns, count(*) FILTER (WHERE t.correlated_insulator) AS ci, "
         f"count(*) FILTER (WHERE t.superconducting) AS sc, sum(t.cryostat_hours) AS cryo_h, sum(t.cost_usd) AS cost "
         f"FROM {n}.device d JOIN {n}.transport_run t USING (device_id) GROUP BY 1) "
         f"SELECT {sel}, count(*) AS devices, round(avg((dev.ci >= 2)::int), 2) AS reproducible_ci, "
         f"round(avg((dev.sc >= 2)::int), 2) AS reproducible_sc, round(avg((dev.ci >= 1)::int), 2) AS any_ci, "
         f"round(avg(s.fab_hours + d.fab_hours)::numeric, 1) AS fab_hours, round(avg(dev.cost)::numeric) AS cryo_cost_usd "
         f"FROM dev JOIN {n}.device d USING (device_id) JOIN {n}.stack s USING (stack_id) "
         f"JOIN crystallite cr ON cr.crystallite_id = s.graphene_flake_id JOIN chip ch ON ch.chip_id = cr.chip_id "
         f"JOIN bulk_crystal b ON b.bulk_crystal_id = cr.bulk_crystal_id "
         f"GROUP BY {', '.join(str(i + 1) for i in range(len(keys)))} HAVING count(*) >= 3 "
         f"ORDER BY reproducible_ci DESC, devices DESC LIMIT 25")
    rows, s, err = db(ctx, agent, q)
    return {"rows": rows, "error": err}, "db", s


def t_run_sql(ctx, agent, query=""):
    rows, s, err = db(ctx, agent, query)
    return {"rows": rows[:30], "error": err}, "db", s


def t_lit(ctx, agent, query="", kind="papers"):
    from asta_mcp import call_tool
    t = time.perf_counter()
    try:
        if kind == "snippets":
            r = call_tool("snippet_search", {"query": query, "limit": 5})
            items = [{"title": d["paper"]["title"], "snippet": d["snippet"]["text"][:300]} for d in r.get("data", [])]
        else:
            r = call_tool("search_papers_by_relevance", {"keyword": query, "limit": 8,
                                                         "fields": "title,year,venue,externalIds"})
            r = r if isinstance(r, list) else r.get("data", [])
            items = [{"title": d.get("title"), "year": d.get("year"), "venue": d.get("venue"),
                      "doi": (d.get("externalIds") or {}).get("DOI")} for d in r]
        err = None
    except Exception as e:  # noqa: BLE001
        items, err = [], f"{type(e).__name__}: {str(e)[:200]}"
    return {"results": items, "error": err}, "literature", time.perf_counter() - t


def t_theory(ctx, agent, quantity="magic_angle", twist_deg=1.08, w_meV=110.0, v_ms=1.0e6):
    """Bistritzer-MacDonald continuum estimates (chiral-limit first magic alpha = 0.586)."""
    t = time.perf_counter()
    a = 0.246  # nm, graphene lattice constant
    hv = 6.582e-16 * float(v_ms) * 1e9  # eV nm
    K = 4 * math.pi / (3 * a)
    out = {}
    th_m = 2 * math.asin(float(w_meV) / 1000 / (0.586 * hv) / (2 * K))
    out["first_magic_angle_deg"] = round(math.degrees(th_m), 3)
    th = math.radians(float(twist_deg))
    lam = a / (2 * math.sin(th / 2))
    out["twist_deg"] = float(twist_deg)
    out["moire_period_nm"] = round(lam, 2)
    out["full_filling_density_1e12_cm2"] = round(4 / (math.sqrt(3) / 2 * lam ** 2) * 1e14 / 1e12, 2)
    out["alpha"] = round(float(w_meV) / 1000 / (hv * 2 * K * math.sin(th / 2)), 3)
    out["note"] = "flat bands need alpha within about 10% of 0.586; that is roughly +/-0.1 deg around the magic angle"
    return out, "compute", time.perf_counter() - t


def t_rank(ctx, agent, budget_hours=200):
    """Rank candidate next experiments by (posterior success + 1 sd) per expected hour."""
    t = time.perf_counter()
    n = NEXT(ctx)
    yld, _, s1 = t_exfoliation_yield(ctx, agent)
    exf = [r for r in yld.get("rows", []) if r.get("monolayers")]
    rows, s2, err = db(ctx, agent,
                       f"WITH dev AS (SELECT device_id, count(*) FILTER (WHERE correlated_insulator) AS ci, "
                       f"sum(cryostat_hours) AS cryo_h FROM {n}.transport_run GROUP BY 1) "
                       f"SELECT round(s.target_twist_deg::numeric, 2) AS target_twist, s.method, d.geometry, s.graphite_gate, "
                       f"count(*) AS n, sum((dev.ci >= 2)::int) AS ok, avg(s.fab_hours + d.fab_hours + dev.cryo_h) AS hours "
                       f"FROM dev JOIN {n}.device d USING (device_id) JOIN {n}.stack s USING (stack_id) GROUP BY 1,2,3,4")
    cands = []
    for r in rows:
        a_, b_ = 1 + (r["ok"] or 0), 1 + r["n"] - (r["ok"] or 0)
        mean = a_ / (a_ + b_)
        sd = math.sqrt(a_ * b_ / ((a_ + b_) ** 2 * (a_ + b_ + 1)))
        cands.append({**r, "p_success": round(mean, 3), "p_sd": round(sd, 3), "hours": round(float(r["hours"]), 1),
                      "score_per_100h": round(100 * (mean + sd) / float(r["hours"]), 3)})
    cands.sort(key=lambda x: -x["score_per_100h"])
    best_exf = sorted(exf, key=lambda r: -(r.get("monolayers_per_chip") or 0))[:3]
    out = {"candidates": cands[:10], "best_exfoliation_settings": best_exf, "budget_hours": budget_hours,
           "error": err if not cands else None}
    if not cands:
        out["note"] = ("no stacking, device or transport outcomes in the database; only exfoliation yields can be "
                       "ranked, so device-level choices must come from literature priors")
    return out, "db", s1 + s2


TOOLS = {
    "exfoliation_yield": (t_exfoliation_yield, "Flake counts per source crystal and exfoliation setting (pressure, "
                          "temperature), with monolayers per chip.", {"material": al.S}, []),
    "reproducibility_table": (t_reproducibility, "For stacked twisted-graphene devices: share of devices with a "
                              "correlated-insulator or superconducting signature in at least two cooldowns, grouped "
                              "by up to three of twist_bin, source, sample_pressure_kpa, method, pickup_temp_c, "
                              "geometry, graphite_gate (comma separated).", {"group_by": al.S}, []),
    "archive_sql": (t_run_sql, "One read-only SQL statement on AURORA's flake archive (tables bulk_crystal, chip, "
                    "image, crystallite; 15 s limit).", {"query": al.S}, ["query"]),
    "device_sql": (t_run_sql, "One read-only SQL statement on AURORA's stacking, device and transport records "
                   "(write aurora_next.stack, aurora_next.device, aurora_next.transport_run; stack.graphene_flake_id joins "
                   "crystallite.crystallite_id; 15 s limit).", {"query": al.S}, ["query"]),
    "search_papers": (t_lit, "Search the literature; kind 'papers' (titles, years, DOIs) or 'snippets' (text).",
                      {"query": al.S, "kind": {"type": "string", "enum": ["papers", "snippets"]}}, ["query"]),
    "continuum_model": (t_theory, "Continuum-model numbers for twisted bilayer graphene: first magic angle, moire "
                        "period and full-filling density at a twist angle.",
                        {"twist_deg": {"type": "number"}, "w_meV": {"type": "number"}}, []),
    "rank_next_experiments": (t_rank, "Rank candidate next experiments by success probability (with uncertainty, "
                              "from successes and failures) per expected hour, plus the best exfoliation settings.",
                              {"budget_hours": al.I}, []),
}

SPECIALISTS = {
    "archive": (["exfoliation_yield", "archive_sql"],
                "You are AURORA's flake-archive agent. Answer from AURORA's crystal, chip, exfoliation and flake "
                "records only. Give numbers. If the records cannot answer something, say so plainly."),
    "devices": (["reproducibility_table", "device_sql"],
                "You are AURORA's stacking-and-transport agent. Answer from AURORA's stack, device and cryogenic "
                "transport records only. Give numbers. If the records do not exist, say so plainly."),
    "literature": (["search_papers"],
                   "You are a literature agent. Search, then answer with paper titles, years and DOIs. Do not invent "
                   "papers."),
    "theory": (["continuum_model"],
               "You are a theory agent for moire materials. Use the continuum_model tool for numbers."),
    "planner": (["rank_next_experiments"],
                "You are AURORA's experiment planner. Use the ranking tool, then propose concrete next experiments "
                "with expected hours and why. Learn from failures as well as successes."),
}
for _n, (_t, _p) in SPECIALISTS.items():
    SPECIALISTS[_n] = (_t, _p + " Reply in at most eight sentences or a short list.")

COORD_PROMPT = (
    "You coordinate a team of agents for AURORA, an autonomous 2D-materials laboratory. Specialists: archive (flake "
    "archive: crystals, chips, exfoliation settings, flake yields), devices (stacks, twist angles, devices, cryogenic "
    "transport outcomes), literature (papers), theory (continuum-model numbers), planner (ranks next experiments by "
    "success per hour). Use ask_agent to send each specialist a focused sub-question; you may ask several at once. "
    "Then write the final answer: (1) the most reproducible combinations, with numbers, (2) relation to the "
    "literature, with citations, (3) five next experiments with expected hours. State clearly which parts the data "
    "could not answer.")
SINGLE_PROMPT = (
    "You are AURORA's research agent for an autonomous 2D-materials laboratory. Use your tools, then answer: (1) the "
    "most reproducible combinations, with numbers, (2) relation to the literature, with citations, (3) five next "
    "experiments with expected hours. State clearly which parts your tools could not answer.")
ARCHIVE_ONLY_PROMPT = al.SPECIALIST_PROMPT.replace("reply in at most three sentences", "reply")


def fn_spec(name):
    _, desc, props, req = TOOLS[name]
    return al._fn(name, desc, props, req)


ASK = al._fn("ask_agent", "Ask one specialist agent a sub-question and get its answer.",
             {"agent": {"type": "string", "enum": list(SPECIALISTS)}, "question": al.S}, ["agent", "question"])


def loop(ctx, role, sys_p, tools, user, think, max_turns=10, depth=0):
    """Run one agent to its final answer; tool calls in one turn run concurrently."""
    msgs = [{"role": "system", "content": sys_p}, {"role": "user", "content": user}]
    for turn in range(max_turns):
        body = {"model": al.model_name(), "messages": msgs, "tools": tools, "temperature": 0.7, "top_p": 0.8,
                "seed": ctx.seed * 1000 + turn + 37 * depth, "max_tokens": 6144,
                "chat_template_kwargs": {"enable_thinking": think}}
        if depth > 0 and turn == 0:
            body["tool_choice"] = "required"  # a specialist must consult its records before answering
        ts = ctx.now()
        try:
            out, wall = al.post(body)
        except Exception as e:  # noqa: BLE001 - context overflow or server error ends this agent
            ctx.log("calls", {"role": role, "t": ts, "model_s": ctx.now() - ts, "error": str(e)[:200]})
            return f"[{role} failed: {str(e)[:120]}]"
        u = out.get("usage", {})
        m = out["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        ctx.log("calls", {"role": role, "t": ts, "model_s": wall, "prompt_tokens": u.get("prompt_tokens", 0),
                          "completion_tokens": u.get("completion_tokens", 0), "n_tool_calls": len(calls)})
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls} if calls
                    else {"role": "assistant", "content": m.get("content") or ""})
        if not calls:
            return m.get("content") or ""

        def run(c):
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            t1 = ctx.now()
            if name == "ask_agent" and args.get("agent") in SPECIALISTS:
                tl, sp = SPECIALISTS[args["agent"]]
                think_sub = args["agent"] == "planner"
                ans = loop(ctx, args["agent"], sp, [fn_spec(x) for x in tl], args.get("question", ""), think_sub,
                           max_turns=6, depth=depth + 1)
                ctx.log("tools", {"role": role, "tool": "ask_agent", "target": args["agent"], "t": t1,
                                  "wall_s": ctx.now() - t1, "kind": "agent", "busy_s": 0.0})
                return json.dumps({"agent": args["agent"], "answer": ans[:SUB_CHARS]})
            if name in TOOLS:
                fn = TOOLS[name][0]
                kw = {k: v for k, v in args.items() if k in TOOLS[name][2]}
                try:
                    res, kind, busy = fn(ctx, role, **kw)
                except Exception as e:  # noqa: BLE001
                    res, kind, busy = {"error": f"{type(e).__name__}: {str(e)[:200]}"}, "error", 0.0
                ctx.log("tools", {"role": role, "tool": name, "t": t1, "wall_s": ctx.now() - t1, "kind": kind,
                                  "busy_s": busy, "error": res.get("error") if isinstance(res, dict) else None})
                return json.dumps(res, default=str)[:6000]
            return json.dumps({"error": f"unknown tool {name}"})

        with ThreadPoolExecutor(max_workers=max(1, len(calls))) as ex:
            results = list(ex.map(run, calls))
        for c, text in zip(calls, results):
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": text})
    return "[no final answer within the turn limit]"


def decision(arm, cond, dbmode, seed):
    ctx = Ctx(cond, dbmode, seed)
    if arm == "team":
        ans = loop(ctx, "coordinator", COORD_PROMPT, [ASK], QUESTION, think=True, max_turns=8)
    elif arm == "single_all":
        ans = loop(ctx, "single", SINGLE_PROMPT, [fn_spec(x) for x in TOOLS], QUESTION, think=True, max_turns=12)
    else:
        ans = loop(ctx, "single", ARCHIVE_ONLY_PROMPT, [fn_spec("exfoliation_yield"), fn_spec("archive_sql")],
                   QUESTION, think=False, max_turns=10)
    return {"arm": arm, "cond": cond, "dbmode": dbmode, "seed": seed, "t_total": ctx.now(), "answer": ans,
            "calls": ctx.calls, "tools": ctx.tools, "sql": ctx.sql, "model": al.model_name(),
            "t_wall_utc": datetime.utcnow().isoformat()}


def cmd_run(a):
    OUT.mkdir(parents=True, exist_ok=True)
    lo, hi = (int(x) for x in a.seeds.split("-"))
    f = OUT / f"e3c_{a.arm}_{a.cond}_{a.db}.jsonl"
    lock = threading.Lock()

    def one(seed):
        rec = decision(a.arm, a.cond, a.db, seed)
        with lock, f.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        print(f"{a.arm} {a.cond} {a.db} seed {seed}: {rec['t_total']:.1f} s", flush=True)

    with ThreadPoolExecutor(max_workers=a.par) as ex:
        list(ex.map(one, range(lo, hi + 1)))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arm", choices=["single_archive", "single_all", "team"], required=True)
    r.add_argument("--cond", choices=["today", "projected"], required=True)
    r.add_argument("--db", choices=["summary", "raw"], default="summary")
    r.add_argument("--seeds", default="1-1")
    r.add_argument("--par", type=int, default=1)
    a = p.parse_args()
    cmd_run(a)


if __name__ == "__main__":
    main()
