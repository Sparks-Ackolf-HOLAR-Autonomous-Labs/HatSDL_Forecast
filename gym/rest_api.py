"""E3b: AURORA's tools behind an open REST API, so users can bring their own LLM.

A user's agent (a local model, Claude, ChatGPT, or a script) reaches the archive over HTTP instead
of in-process tools. The API is self-describing, so a generic agent can find out how to use it:

    GET  /                 what this service is, and where the guides are
    GET  /llms.txt         agent guide (the AURORA skill, written for HTTP)
    GET  /openapi.json     OpenAPI 3.1 description of every endpoint
    GET  /v1/tools/<name>?arg=value   the six E3 specialist tools
    POST /v1/sql           {"query": "..."}  one read-only statement (15 s limit, 50 rows)

Every response carries the database time (JSON field db_ms and a Server-Timing header), and the
server logs one line per request (client tag from the X-Client header), so a decision can be split
into model time, network/HTTP time and database time on the server side.

    python -m gym.rest_api serve --port 8730 --log rest_log.jsonl
    python -m gym.rest_api bench --url http://127.0.0.1:8730 --n 200
"""
from __future__ import annotations

import argparse
import json
import queue
import statistics
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gym import agent_latency as al

GUIDE = """# AURORA archive API (agent guide)
AURORA (University of Utah / Arkansas, NSF PCL node) stores every exfoliated 2D flake it images.
Read-only. Responses are JSON: {"rows": [...], "error": null, "db_ms": 1.2}; at most 50 rows.

Tools (GET, arguments as query parameters):
- /v1/tools/aurora_archive_search?material=WSe2&layer=monolayer&limit=10   highest-confidence flakes
- /v1/tools/aurora_stack_candidates?bulk_crystal_id=<id>&limit=5           largest monolayers of a crystal
- /v1/tools/aurora_chip_summary?chip_id=<id>                               flakes per layer class on a chip
- /v1/tools/aurora_get_flake?crystallite_id=<id>                           one flake record
- /v1/tools/aurora_tile_flakes?image_path=<path>                           flakes on one microscope tile
- /v1/tools/aurora_removed_since?since=2026-01-01                          chips with removed flakes

Own SQL (POST /v1/sql, body {"query": "..."}; PostgreSQL, 15 s limit):
""" + al.AURORA_SKILL.split("\n", 2)[2].replace("Use the run_sql tool (PostgreSQL, read-only, 15 s limit, first 50 rows returned).\n", "")

ROOT = {
    "name": "AURORA archive API",
    "description": "Read-only access to AURORA's archive of exfoliated 2D-material flakes, chips and microscope "
                   "tiles. Bring your own LLM agent: read /llms.txt (agent guide) or /openapi.json, then call "
                   "the tools or POST read-only SQL to /v1/sql.",
    "agent_guide": "/llms.txt",
    "openapi": "/openapi.json",
}


def openapi():
    paths = {}
    for t in al.SPECIALIST_TOOLS:
        f = t["function"]
        params = [{"name": k, "in": "query", "required": k in f["parameters"]["required"], "schema": v}
                  for k, v in f["parameters"]["properties"].items()]
        paths[f"/v1/tools/{f['name']}"] = {"get": {"operationId": f["name"], "summary": f["description"],
                                                   "parameters": params}}
    paths["/v1/sql"] = {"post": {"operationId": "run_sql", "summary": "One read-only SQL statement (see /llms.txt).",
                                 "requestBody": {"content": {"application/json": {"schema": {
                                     "type": "object", "properties": {"query": {"type": "string"}},
                                     "required": ["query"]}}}}}}
    return {"openapi": "3.1.0", "info": {"title": ROOT["name"], "version": "0.1", "description": ROOT["description"]},
            "paths": paths}


_log_lock = threading.Lock()
_pool: "queue.Queue" = queue.Queue()  # reused database sessions (one per concurrent request)


def _with_conn(fn, *a):
    """Run fn on a pooled read-only session; a new session is opened only when all are busy."""
    try:
        c = _pool.get_nowait()
    except queue.Empty:
        c = None
    if c is None:
        if hasattr(al._local, "c"):
            del al._local.c
        al.conn()
    else:
        al._local.c = c
    try:
        return fn(*a)
    finally:
        _pool.put(al._local.c)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    log_path: Path | None = None

    def log_message(self, *a):  # quiet; we keep our own log
        pass

    def _send(self, code, body, ctype="application/json", db_ms=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, default=str)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if db_ms is not None:
            self.send_header("Server-Timing", f"db;dur={db_ms:.3f}")
        self.end_headers()
        self.wfile.write(data)

    def _log(self, t0, code, db_ms, nq):
        if self.log_path is None:
            return
        rec = {"t": time.time(), "client": self.headers.get("X-Client", ""), "method": self.command,
               "path": self.path.split("?")[0], "code": code, "db_ms": db_ms, "nq": nq,
               "server_ms": (time.perf_counter() - t0) * 1000}
        with _log_lock, open(self.log_path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def _tool(self, name, args):
        if name not in al.SPECIALIST_SQL:
            return 404, {"error": f"unknown tool {name}"}, None, 0
        a = dict(args)
        try:
            a["limit"] = min(int(a.get("limit", 10)), al.ROWS)
        except (TypeError, ValueError):
            a["limit"] = 10
        rows, db_s, err = _with_conn(al.sql, al.SPECIALIST_SQL[name], a)
        return (400 if err else 200), {"rows": rows, "error": err, "db_ms": round(db_s * 1000, 3)}, db_s * 1000, 1

    def do_GET(self):
        t0 = time.perf_counter()
        u = urllib.parse.urlsplit(self.path)
        db_ms, nq = None, 0
        if u.path == "/":
            code, body, ctype = 200, ROOT, "application/json"
        elif u.path == "/llms.txt":
            code, body, ctype = 200, GUIDE, "text/markdown; charset=utf-8"
        elif u.path == "/openapi.json":
            code, body, ctype = 200, openapi(), "application/json"
        elif u.path.startswith("/v1/tools/"):
            args = dict(urllib.parse.parse_qsl(u.query))
            code, body, db_ms, nq = self._tool(u.path.rsplit("/", 1)[1], args)
            ctype = "application/json"
        else:
            code, body, ctype = 404, {"error": "not found; see /"}, "application/json"
        self._send(code, body, ctype, db_ms)
        self._log(t0, code, db_ms, nq)

    def do_POST(self):
        t0 = time.perf_counter()
        n = int(self.headers.get("Content-Length") or 0)
        try:
            q = json.loads(self.rfile.read(n) or b"{}").get("query", "")
        except json.JSONDecodeError:
            q = ""
        if self.path.split("?")[0] != "/v1/sql" or not q:
            self._send(400, {"error": "POST /v1/sql with {\"query\": ...}"})
            self._log(t0, 400, None, 0)
            return
        rows, db_s, err = _with_conn(al.sql, q)
        out = {"rows": rows, "error": err, "db_ms": round(db_s * 1000, 3)}
        self._send(400 if err else 200, out, db_ms=db_s * 1000)
        self._log(t0, 400 if err else 200, db_s * 1000, 1)


def cmd_serve(a):
    Handler.log_path = Path(a.log).expanduser() if a.log else None
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"AURORA REST API on http://{a.host}:{a.port}", flush=True)
    srv.serve_forever()


def call(url, client="bench", body=None):
    """One HTTP call; returns (json, wall s, server db ms)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Client": client})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    wall = time.perf_counter() - t0
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {"text": raw.decode()[:200]}
    return out, wall, (out.get("db_ms") if isinstance(out, dict) else None)


def cmd_bench(a):
    """Same tool calls in-process and over HTTP (new connection per call, as a simple client does)."""
    t = al.tasks(1)
    params = {"aurora_get_flake": {"crystallite_id": t[3]["q"].split("flake ")[1].split(":")[0]},
              "aurora_chip_summary": {"chip_id": t[2]["q"].split("chip ")[1].split(":")[0]},
              "aurora_stack_candidates": {"bulk_crystal_id": t[1]["q"].split("crystal ")[1].split(",")[0], "limit": 5}}
    res = {}
    for name, args in params.items():
        direct, http, srv_db = [], [], []
        for _ in range(a.n):
            t0 = time.perf_counter()
            al.run_tool(name, dict(args))
            direct.append((time.perf_counter() - t0) * 1000)
            _, w, db = call(f"{a.url}/v1/tools/{name}?{urllib.parse.urlencode(args)}")
            http.append(w * 1000)
            srv_db.append(db or 0)
        res[name] = {"n": a.n, "direct_median_ms": statistics.median(direct), "http_median_ms": statistics.median(http),
                     "http_p95_ms": sorted(http)[int(0.95 * a.n)], "db_median_ms": statistics.median(srv_db)}
        print(name, json.dumps({k: round(v, 3) for k, v in res[name].items()}), flush=True)
    al.OUT.mkdir(parents=True, exist_ok=True)
    (al.OUT / "e3b_rest_bench.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8730)
    s.add_argument("--log", default="")
    b = sp.add_parser("bench")
    b.add_argument("--url", default="http://127.0.0.1:8730")
    b.add_argument("--n", type=int, default=200)
    a = p.parse_args()
    {"serve": cmd_serve, "bench": cmd_bench}[a.cmd](a)
