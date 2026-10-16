"""Experiment E3 on AURORA: decision time when an LLM/VLM agent, not a person, queries the database.

E1 to E2c timed the database alone (a query takes 0.2-300 ms). AURORA's users will increasingly
reach the archive through agents, and then a decision also contains model calls, tool-call
turns, skill discovery, model start-up and network hops. This module measures those parts on the
DGX with a local vision-language model (Qwen3.5-9B on vLLM) whose tools run real queries on the
DGX copy of AURORA (sddb_aurora), and splits every decision into model time and database time.

Three agent cases (the user's a, b, c):
  A    specialist agent (stand-in for a fine-tuned LLM): AURORA tools exposed directly, short
       system prompt, no reasoning trace.
  A-V  the same agent given a microscope-tile image (VLM input) with the question.
  B    generic agent with skills: it sees only a list of skills, must read the AURORA skill to
       learn the schema, then writes its own SQL through a read-only run_sql tool; reasoning on.
  overhead (c) is measured separately: model start-up from the server log, network round trips
       to hosted model APIs and over the tailnet (see `network`).

    python -m gym.agent_latency run --case A --reps 3
    python -m gym.agent_latency concurrency --n 1,4,16
    python -m gym.agent_latency network
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import json
import random
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from gym.aurora_src import dst

OUT = Path(__file__).resolve().parent.parent / "results" / "aurora_agents"
URL = "http://127.0.0.1:8720/v1/chat/completions"
MODEL = None  # filled from /v1/models
ROWS = 50     # rows returned to the model per tool call
TIMEOUT_S = 15  # same statement limit as AURORA's read-only role
REST = os.environ.get("AURORA_REST", "")  # if set (e.g. http://127.0.0.1:8730), tools go over the REST API (E3b)

# ------------------------------------------------------------------ database side (timed)
_local = threading.local()


def conn():
    if not hasattr(_local, "c"):
        c = dst()
        c.execute(f"SET statement_timeout = '{TIMEOUT_S}s'")
        c.execute("SET default_transaction_read_only = on")
        _local.c = c
    return _local.c


def _js(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def sql(q, a=None):
    """Run one read-only statement; return (rows as dicts, db seconds, error)."""
    t0 = time.perf_counter()
    try:
        cur = conn().execute(q, a)
        cols = [d.name for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, map(_js, r))) for r in cur.fetchmany(ROWS)]
        return rows, time.perf_counter() - t0, None
    except Exception as e:  # noqa: BLE001 - errors go back to the model, as a tool would
        conn().rollback() if not conn().autocommit else None
        return [], time.perf_counter() - t0, f"{type(e).__name__}: {str(e)[:300]}"


AREA = "((physical_dimensions->>'area_um2')::numeric)"
SPECIALIST_SQL = {
    "aurora_archive_search": (f"SELECT c.crystallite_id, c.classification_confidence_ai, {AREA} AS area_um2 "
                              "FROM crystallite c JOIN bulk_crystal b USING (bulk_crystal_id) "
                              "WHERE b.material=%(material)s AND c.classification_ai=%(layer)s AND c.removed_at IS NULL "
                              "ORDER BY c.classification_confidence_ai DESC LIMIT %(limit)s"),
    "aurora_stack_candidates": (f"SELECT crystallite_id, {AREA} AS area_um2, classification_confidence_ai "
                                "FROM crystallite WHERE bulk_crystal_id=%(bulk_crystal_id)s "
                                "AND classification_ai='monolayer' AND removed_at IS NULL "
                                f"ORDER BY {AREA} DESC NULLS LAST LIMIT %(limit)s"),
    "aurora_chip_summary": "SELECT classification_ai, count(*) AS n FROM crystallite WHERE chip_id=%(chip_id)s GROUP BY 1",
    "aurora_get_flake": "SELECT * FROM crystallite WHERE crystallite_id=%(crystallite_id)s",
    "aurora_tile_flakes": ("SELECT crystallite_id, bounding_box_ai, classification_ai FROM crystallite "
                           "WHERE image_path=%(image_path)s"),
    "aurora_removed_since": "SELECT chip_id, count(*) AS n FROM crystallite WHERE removed_at > %(since)s GROUP BY 1",
}


def _fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
I = {"type": "integer"}
SPECIALIST_TOOLS = [
    _fn("aurora_archive_search", "Highest-confidence flakes of one material and layer class.",
        {"material": S, "layer": {"type": "string", "enum": ["monolayer", "bilayer", "trilayer", "thick"]},
         "limit": I}, ["material", "layer"]),
    _fn("aurora_stack_candidates", "Largest monolayer flakes of one bulk crystal, for stacking.",
        {"bulk_crystal_id": S, "limit": I}, ["bulk_crystal_id"]),
    _fn("aurora_chip_summary", "Number of flakes per layer class on one chip.", {"chip_id": S}, ["chip_id"]),
    _fn("aurora_get_flake", "Full record of one flake by its identifier.", {"crystallite_id": S}, ["crystallite_id"]),
    _fn("aurora_tile_flakes", "Flakes detected on one microscope tile (by image path).", {"image_path": S}, ["image_path"]),
    _fn("aurora_removed_since", "Chips with flakes removed after a date (ISO), and how many.", {"since": S}, ["since"]),
]
SPECIALIST_PROMPT = ("You are the AURORA archive agent. Answer questions about AURORA's 2D-material flakes by "
                     "calling the aurora_* tools, then reply in at most three sentences.")

# Generic agent: a skill list in the style of agent skill folders; only one skill is about AURORA.
SKILLS = {
    "pdf": "Read, split and fill PDF files.",
    "docx": "Create and edit Word documents.",
    "plotting": "Make publication-quality plots with matplotlib.",
    "literature": "Search papers and build a reading list.",
    "slurm": "Write and submit SLURM batch jobs on CHPC.",
    "dft-setup": "Prepare Quantum ESPRESSO inputs from a structure.",
    "xrd": "Index and refine powder XRD patterns.",
    "aurora-database": "Query AURORA's archive of exfoliated 2D-material flakes, chips and microscope tiles.",
    "spreadsheet": "Read and write Excel and CSV files.",
    "git": "Commit, branch and review code changes.",
    "email": "Draft and send e-mails.",
    "calendar": "Book instruments and meetings.",
}
AURORA_SKILL = """# aurora-database
AURORA (University of Utah / Arkansas, NSF PCL node) stores every exfoliated 2D flake it images.
Use the run_sql tool (PostgreSQL, read-only, 15 s limit, first 50 rows returned).

Tables (main columns):
- bulk_crystal(bulk_crystal_id text, material text, ...)            e.g. material 'WSe2', 'MoS2', 'hBN'
- chip(chip_id text, tray_id, current_status, current_location, bulk_crystal_id, created_at, updated_at, removed_at)
- image(image_id, chip_id, image_path text, meta_data jsonb, created_at)    one row per microscope tile
- crystallite(crystallite_id text, chip_id, bulk_crystal_id, image_id, image_path,
    classification_ai text   -- 'monolayer' | 'bilayer' | 'trilayer' | 'thick' (detector label)
    classification_h text    -- human review label, NULL until reviewed
    reviewed bool, classification_confidence_ai float, detection_confidence_ai float,
    uncertainty_score_ai float, bounding_box_ai jsonb, physical_dimensions jsonb  -- ->>'area_um2'
    x_position, y_position, user_id, user_action_at, created_at, removed_at timestamptz)
  6.2 million rows; always filter (chip_id, bulk_crystal_id, image_path or crystallite_id are indexed).
Removed flakes have removed_at set; exclude them unless asked.
Example: SELECT count(*) FROM crystallite WHERE chip_id = '<chip>' AND classification_ai = 'monolayer';
"""
GENERIC_TOOLS = [
    _fn("list_skills", "List the skills available to you.", {}, []),
    _fn("read_skill", "Read the instructions of one skill.", {"name": S}, ["name"]),
    _fn("run_sql", "Run one read-only SQL statement on a database named by a skill.", {"query": S}, ["query"]),
]
GENERIC_PROMPT = ("You are a general research assistant for a materials science group. You have skills that "
                  "explain how to use your tools; list and read the relevant skill before using a tool you do "
                  "not know. Reply in at most three sentences.")


def rest_tool(name, args):
    """The same tool over the open REST API (gym.rest_api); db seconds as reported by the server."""
    if name == "run_sql":
        url, body = f"{REST}/v1/sql", json.dumps({"query": args.get("query", "")}).encode()
    else:
        url, body = f"{REST}/v1/tools/{name}?" + urllib.parse.urlencode(args), None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "X-Client": "qwen-rest"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    out = json.loads(raw)
    err = out.get("error")
    return raw.decode()[:6000], (out.get("db_ms") or 0) / 1000, 1, err


def run_tool(name, args):
    """Execute a tool call; return (text for the model, db seconds, n_queries, error)."""
    if REST and (name == "run_sql" or name in SPECIALIST_SQL):
        return rest_tool(name, args)
    if name == "list_skills":
        return json.dumps(SKILLS), 0.0, 0, None
    if name == "read_skill":
        return (AURORA_SKILL if args.get("name") == "aurora-database" else f"No details for {args.get('name')}."), 0.0, 0, None
    if name == "run_sql":
        rows, s, err = sql(args.get("query", ""))
        return json.dumps({"rows": rows, "error": err}, default=str)[:6000], s, 1, err
    if name in SPECIALIST_SQL:
        a = dict(args)
        a.setdefault("limit", 10)
        try:
            a["limit"] = min(int(a["limit"]), ROWS)
        except (TypeError, ValueError):
            a["limit"] = 10
        rows, s, err = sql(SPECIALIST_SQL[name], a)
        return json.dumps({"rows": rows, "error": err}, default=str)[:6000], s, 1, err
    return json.dumps({"error": f"unknown tool {name}"}), 0.0, 0, "unknown tool"


# ------------------------------------------------------------------ model side (timed)
def post(body, timeout=600):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out, time.perf_counter() - t0


def model_name():
    global MODEL
    if MODEL is None:
        with urllib.request.urlopen(URL.replace("chat/completions", "models"), timeout=10) as r:
            MODEL = json.loads(r.read())["data"][0]["id"]
    return MODEL


def tile_image(seed):
    """A synthetic 1280x960 optical-microscope-like tile (timing only; AURORA images are not in the copy)."""
    from PIL import Image, ImageDraw, ImageFilter
    r = random.Random(seed)
    im = Image.new("RGB", (1280, 960), (176, 150, 196))  # SiO2/Si purple background
    d = ImageDraw.Draw(im)
    for _ in range(9):
        x, y, s = r.randint(60, 1180), r.randint(60, 880), r.randint(20, 140)
        shade = r.choice([(160, 140, 190), (120, 100, 170), (70, 60, 120), (210, 200, 120)])
        pts = [(x + r.randint(-s, s), y + r.randint(-s, s)) for _ in range(6)]
        d.polygon(pts, fill=shade)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def agent(case, task, seed, max_turns=12):
    """One decision: question in, answer out. Returns a timing record."""
    generic = case == "B"
    tools = GENERIC_TOOLS if generic else SPECIALIST_TOOLS
    sys_p = GENERIC_PROMPT if generic else SPECIALIST_PROMPT
    user = [{"type": "text", "text": task["q"]}]
    if case == "A-V":
        user = [{"type": "image_url", "image_url": {"url": tile_image(seed)}},
                {"type": "text", "text": task["q_img"]}]
    msgs = [{"role": "system", "content": sys_p}, {"role": "user", "content": user}]
    rec = {"case": case, "task": task["id"], "seed": seed, "turns": [], "t_model": 0.0, "t_db": 0.0,
           "t_tool_other": 0.0, "n_queries": 0, "sql_errors": 0, "prompt_tokens": 0, "completion_tokens": 0}
    t_start = time.perf_counter()
    for turn in range(max_turns):
        body = {"model": model_name(), "messages": msgs, "tools": tools, "temperature": 0.7, "top_p": 0.8,
                "seed": seed * 100 + turn, "max_tokens": 4096,
                "chat_template_kwargs": {"enable_thinking": generic}}
        out, wall = post(body)
        u = out.get("usage", {})
        m = out["choices"][0]["message"]
        rec["t_model"] += wall
        rec["prompt_tokens"] += u.get("prompt_tokens", 0)
        rec["completion_tokens"] += u.get("completion_tokens", 0)
        calls = m.get("tool_calls") or []
        tr = {"model_s": wall, "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
              "tools": []}
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls} if calls
                    else {"role": "assistant", "content": m.get("content") or ""})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            t0 = time.perf_counter()
            text, db_s, nq, err = run_tool(name, args)
            tot = time.perf_counter() - t0
            rec["t_db"] += db_s
            rec["t_tool_other"] += tot - db_s
            rec["n_queries"] += nq
            rec["sql_errors"] += bool(err) and nq > 0
            tr["tools"].append({"name": name, "args": args, "db_s": db_s, "err": err})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": text})
        rec["turns"].append(tr)
        if not calls:
            rec["answer"] = (m.get("content") or "")[:600]
            break
    rec["n_turns"] = len(rec["turns"])
    rec["t_total"] = time.perf_counter() - t_start
    rec["finished"] = "answer" in rec
    return rec


def tasks(seed):
    """Five questions, one per AURORA user mode, with parameters drawn from the copy."""
    c = conn()
    r = random.Random(seed)
    mat = r.choice([x[0] for x in c.execute("SELECT material FROM bulk_crystal b WHERE EXISTS (SELECT 1 FROM crystallite c "
                                            "WHERE c.bulk_crystal_id=b.bulk_crystal_id AND classification_ai='monolayer') "
                                            "LIMIT 20")])
    bc = r.choice([x[0] for x in c.execute("SELECT DISTINCT bulk_crystal_id FROM crystallite TABLESAMPLE SYSTEM (0.1) "
                                           "WHERE classification_ai='monolayer'")])
    chip = r.choice([x[0] for x in c.execute("SELECT chip_id FROM chip TABLESAMPLE SYSTEM (50)")])
    fid, path = r.choice(c.execute("SELECT crystallite_id, image_path FROM crystallite TABLESAMPLE SYSTEM (0.01)").fetchall())
    since = (c.execute("SELECT max(removed_at) FROM crystallite").fetchone()[0] or datetime(2026, 1, 1))
    since = since.date().replace(day=1).isoformat()
    return [
        {"id": "research", "q": f"Find the 10 highest-confidence monolayer flakes of {mat} that are not removed; "
                                "give their IDs and areas."},
        {"id": "planner", "q": f"For bulk crystal {bc}, list the 5 largest monolayer candidates for stacking."},
        {"id": "novice", "q": f"Summarise chip {chip}: how many flakes of each layer class does it hold?"},
        {"id": "pid", "q": f"Give me the record of flake {fid}: its layer class, confidence and chip."},
        {"id": "ehs", "q": f"Which chips had flakes removed since {since}, and how many on each?"},
        {"id": "tile", "q": f"How many flakes were detected on the tile {path}, and what layer classes?",
         "q_img": f"This is microscope tile {path}. Count the flakes you see, then compare with the flakes "
                  "AURORA detected on this tile."},
    ]


def cmd_run(a):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"e3_{a.case}{a.tag}.jsonl"
    for rep in range(1, a.reps + 1):
        for t in tasks(rep):
            if a.case == "A-V" and t["id"] != "tile":
                continue
            if a.case != "A-V" and t["id"] == "tile" and a.skip_tile:
                continue
            rec = agent(a.case, t, rep)
            rec["t_wall_utc"] = datetime.utcnow().isoformat()
            with f.open("a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
            print(f"{a.case} {t['id']} rep{rep}: total {rec['t_total']:.1f}s model {rec['t_model']:.1f}s "
                  f"db {rec['t_db']*1000:.1f}ms turns {rec['n_turns']} q {rec['n_queries']} ok {rec['finished']}",
                  flush=True)


def cmd_concurrency(a):
    """n specialist agents at once on the same model server and database."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "e3_concurrency.jsonl"
    for n in [int(x) for x in a.n.split(",")]:
        recs, threads = [], []
        ts = tasks(1)[:5]

        def go(i):
            recs.append(agent("A", ts[i % 5], 1000 + i))
        t0 = time.perf_counter()
        for i in range(n):
            th = threading.Thread(target=go, args=(i,))
            th.start()
            threads.append(th)
        for th in threads:
            th.join()
        span = time.perf_counter() - t0
        for r in recs:
            r["n_concurrent"] = n
            r["span_s"] = span
            with f.open("a") as fh:
                fh.write(json.dumps(r, default=str) + "\n")
        tot = sorted(r["t_total"] for r in recs)
        print(f"n={n}: span {span:.1f}s median decision {tot[len(tot)//2]:.1f}s max {tot[-1]:.1f}s "
              f"queries/s {sum(r['n_queries'] for r in recs)/span:.2f}", flush=True)


def cmd_microbench(a):
    """Prefill and decode rates of the served model (no tools)."""
    OUT.mkdir(parents=True, exist_ok=True)
    res = []
    filler = "flake " * 50
    for n in (1, 10, 40, 160):  # ~50 tokens per unit
        body = {"model": model_name(), "messages": [{"role": "user", "content": filler * n + "\nSay OK."}],
                "max_tokens": 1, "chat_template_kwargs": {"enable_thinking": False}, "temperature": 0}
        post(body)  # warm (prefix cache would hide prefill on repeat, so vary the text)
        body["messages"][0]["content"] = f"{random.random()} " + filler * n + "\nSay OK."
        out, w = post(body)
        res.append({"kind": "prefill", "prompt_tokens": out["usage"]["prompt_tokens"], "s": w})
    for m in (16, 128, 512):
        body = {"model": model_name(), "messages": [{"role": "user", "content": "Count upward from 1, one number per line."}],
                "max_tokens": m, "chat_template_kwargs": {"enable_thinking": False}, "temperature": 0,
                "ignore_eos": True}
        out, w = post(body)
        res.append({"kind": "decode", "completion_tokens": out["usage"]["completion_tokens"], "s": w})
    for i in range(3):
        body = {"model": model_name(), "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": tile_image(50 + i)}}, {"type": "text", "text": "Say OK."}]}],
            "max_tokens": 1, "chat_template_kwargs": {"enable_thinking": False}}
        out, w = post(body)
        res.append({"kind": "image_prefill", "prompt_tokens": out["usage"]["prompt_tokens"], "s": w})
    (OUT / "e3_microbench.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def curl_times(url, method="POST", n=8):
    fmt = "%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total} %{http_code}"
    out = []
    for _ in range(n):
        body = ["-H", "content-type: application/json", "-d", "{}"] if method == "POST" else []
        p = subprocess.run(["curl", "-s", "-o", "/dev/null", "-X", method, *body, "-w", fmt, "--max-time", "20", url],
                           capture_output=True, text=True)
        try:
            dns, conn_, tls, ttfb, total, code = p.stdout.split()
            out.append({"dns": float(dns), "tcp": float(conn_), "tls": float(tls), "ttfb": float(ttfb),
                        "total": float(total), "http": code})
        except ValueError:
            out.append({"error": p.stdout + p.stderr})
        time.sleep(0.5)
    return out


def cmd_network(_):
    """Round trips with no credentials: an unauthenticated request returns 401 after the full TLS and gateway path."""
    OUT.mkdir(parents=True, exist_ok=True)
    targets = {
        "hosted API, Anthropic": "https://api.anthropic.com/v1/messages",
        "hosted API, OpenAI": "https://api.openai.com/v1/chat/completions",
        "hosted API, Google": "https://generativelanguage.googleapis.com/v1beta/models",
        "Hugging Face hub": "https://huggingface.co/api/models/Qwen/Qwen3.5-9B",
        "local model server (loopback)": "http://127.0.0.1:8720/v1/models",
    }
    res = {k: curl_times(u, "GET" if ("models" in u) else "POST") for k, u in targets.items()}
    (OUT / "e3_network.json").write_text(json.dumps(res, indent=1))
    for k, v in res.items():
        ok = [x for x in v if "ttfb" in x]
        if ok:
            ok.sort(key=lambda x: x["total"])
            print(f"{k}: median total {ok[len(ok)//2]['total']*1000:.0f} ms, tls {ok[len(ok)//2]['tls']*1000:.0f} ms "
                  f"(http {ok[0]['http']})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--case", choices=["A", "A-V", "B"], required=True)
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--skip-tile", action="store_true")
    r.add_argument("--tag", default="", help="suffix for the output file, e.g. _rest")
    c = sp.add_parser("concurrency")
    c.add_argument("--n", default="1,4,16")
    sp.add_parser("microbench")
    sp.add_parser("network")
    a = p.parse_args()
    {"run": cmd_run, "concurrency": cmd_concurrency, "microbench": cmd_microbench, "network": cmd_network}[a.cmd](a)
