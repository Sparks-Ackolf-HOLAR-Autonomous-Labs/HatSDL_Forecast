"""Experiment E2 on AURORA: growth from development staff to a community service, seven user modes.

AURORA's facility plan (NSF PCL Test Bed, Award No. 2607535) names seven user modes. Each mode reads the
database in its own way; this module turns each into read templates on the AURORA schema and
drives them as open-loop arrivals (users x actions per minute) through a fixed pool of
connections, the way a web front end serves its users. Latency therefore includes waiting
for a free connection, so an overloaded index set shows up as queueing.

Writes are not invented: their rate comes from the timestamps already in the copy
(`write-profile`; tiles and flakes per active minute), scaled by the growth stage.

Stages (users per mode) follow the facility plan's milestones: today (staff), beta (18 mo),
robust user service (24 mo, workshops of up to 125 participants a year) and year 4
(proposals from 20 % of US materials groups; 100 % more devices). Access is
proposal-based and workshops are scheduled, so the allocation calendar announces each
stage before its users arrive: that is what the plan-aware tuner reads.

    python -m gym.aurora_users write-profile
    python -m gym.aurora_users calibrate
    python -m gym.aurora_users run --arm plan --seed 1
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import threading
import time
from collections import Counter, defaultdict

import gym.aurora_gym as G
from gym.aurora_src import dst

OUT = G.OUT
AREA = G.AREA

# Two more candidates that serve the new modes (the 13 production indexes and the two E1 ones stay).
G.CANDIDATES.update({
    "ix_archive": "crystallite (bulk_crystal_id, classification_ai, classification_confidence_ai DESC) "
                  "WHERE removed_at IS NULL",
    "ix_user_recent": "crystallite (user_id, user_action_at DESC)",
})
CANDIDATES = G.CANDIDATES

# ---------------------------------------------------------------- read templates per mode
T = {
    # AURORA staff today (the loop of E1): review queue, stacking planner, web viewer
    "review": G.TEMPLATES["review"],
    "planner": G.TEMPLATES["planner"],
    "viewer": G.TEMPLATES["viewer"],
    # First-time users: guided GUI over one chip
    "chip_gallery": "SELECT image_id, image_path FROM image WHERE chip_id=%s ORDER BY created_at LIMIT 24",
    "chip_summary": "SELECT classification_ai, count(*) FROM crystallite WHERE chip_id=%s GROUP BY 1",
    # Research users: archive search (Case Study 3) and citation by persistent identifier
    "archive_search": f"SELECT c.crystallite_id, {AREA} FROM crystallite c JOIN bulk_crystal b USING (bulk_crystal_id) "
                      "WHERE b.material=%s AND c.classification_ai=%s AND c.removed_at IS NULL "
                      "ORDER BY c.classification_confidence_ai DESC LIMIT 50",
    "pid_lookup": "SELECT * FROM crystallite WHERE crystallite_id=%s",
    # Power users: raw export of a crystal's thin flakes for a parameter sweep, raw tile metadata
    "sweep_export": "SELECT crystallite_id, x_position, y_position, physical_dimensions, classification_confidence_ai, "
                    "uncertainty_score_ai FROM crystallite WHERE bulk_crystal_id=%s "
                    "AND classification_ai IN ('monolayer','bilayer','trilayer') AND removed_at IS NULL",
    "telemetry": "SELECT image_id, meta_data FROM image WHERE chip_id=%s",
    # Innovation / prototyping (development lane): compare a detector run with the production run
    "detector_compare": "SELECT classification_ai, count(*), avg(detection_confidence_ai) FROM crystallite "
                        "WHERE image_process_info_id = ANY(%s) GROUP BY 1",
    # Industry: only their own partition
    "own_flakes": "SELECT crystallite_id, classification_h, physical_dimensions FROM crystallite "
                  "WHERE user_id=%s ORDER BY user_action_at DESC LIMIT 100",
    # Education: AURORA Workbench, paging through the reviewed (labelled) dataset, read-only
    "workbench_page": "SELECT crystallite_id, classification_h, bounding_box_ai, image_path FROM crystallite "
                      "WHERE reviewed = true AND (created_at, crystallite_id) < (%s, %s) "
                      "ORDER BY created_at DESC, crystallite_id DESC LIMIT 50",
    # Safety-critical / EHS: audit of removed samples and chip locations
    "removed_audit": "SELECT chip_id, count(*) FROM crystallite WHERE removed_at > %s GROUP BY 1",
    "chip_status": "SELECT chip_id, current_location, current_status FROM chip WHERE updated_at > %s",
}
CRYST = {k for k, v in T.items() if "FROM crystallite" in v}

# mode -> (actions per user per minute, [templates called by one action])
MODES = {
    "staff":     (6, None),  # one of review / planner / viewer, as in E1 production counters
    "novice":    (6, ["chip_gallery", "chip_summary", "viewer"]),
    "research":  (4, ["archive_search", "pid_lookup"]),
    "power":     (12, ["sweep_export", "telemetry"]),
    "prototype": (10, ["detector_compare"]),
    "industry":  (6, ["own_flakes"]),
    "education": (4, ["workbench_page", "viewer"]),
    "ehs":       (1, ["removed_audit", "chip_status"]),
}
STAFF_MIX = [("review", 0.45), ("planner", 0.15), ("viewer", 0.40)]
# Users per mode at each stage; write scale relative to today's median active minute.
STAGES = [
    ("today: development staff",          dict(staff=3, research=1, power=1, prototype=1), 1.0),
    ("beta (18 mo): pilot users",         dict(staff=3, novice=5, research=5, power=2, prototype=2, ehs=1), 1.5),
    ("user service (24 mo): workshop",    dict(staff=4, novice=15, research=15, power=4, prototype=3,
                                               industry=2, education=25, ehs=2), 2.0),
    ("year 4: 20 % of US groups",         dict(staff=4, novice=30, research=30, power=8, prototype=4,
                                               industry=4, education=40, ehs=3), 2.0),
]
STAGE_S, GAP_S, TICK_S, HALF_LIFE_S = 60.0, 15.0, 8.0, 45.0
POOL = 6  # connections serving users (the DGX is shared; kept small on purpose)
SLO_MS = {"staff": 100, "novice": 300, "research": 500, "power": 3000, "prototype": 500,
          "industry": 300, "education": 300, "ehs": 1000}


class Args:
    """Parameter samples drawn once from the copy."""

    def __init__(self, c, r):
        self.r = r
        lab = G.Lab(c, random.Random(0))
        self.lab = lab
        self.all_chips = [x[0] for x in c.execute("SELECT chip_id FROM chip")]
        self.materials = [x[0] for x in c.execute("SELECT DISTINCT b.material FROM bulk_crystal b "
                                                  "JOIN crystallite c USING (bulk_crystal_id) LIMIT 20")] or ["WSe2"]
        self.ids = [x[0] for x in c.execute("SELECT crystallite_id FROM crystallite TABLESAMPLE SYSTEM (0.05)")]
        self.ipis = [x[0] for x in c.execute("SELECT DISTINCT image_process_info_id FROM crystallite "
                                             "TABLESAMPLE SYSTEM (0.2) WHERE image_process_info_id IS NOT NULL")]
        self.users = [x[0] for x in c.execute("SELECT DISTINCT user_id FROM crystallite TABLESAMPLE SYSTEM (5) "
                                              "WHERE user_id IS NOT NULL")]
        self.keys = c.execute("SELECT created_at, crystallite_id FROM crystallite TABLESAMPLE SYSTEM (1) "
                              "WHERE reviewed = true").fetchall()
        self.t_max = c.execute("SELECT max(created_at) FROM crystallite").fetchone()[0]

    def __call__(self, t):
        r = self.r
        if t in ("review", "chip_summary"):
            return (r.choice(self.lab.chips),)
        if t in ("chip_gallery", "telemetry"):
            return (r.choice(self.all_chips),)
        if t == "planner":
            return (r.choice(self.lab.crystals),)
        if t == "viewer":
            return (r.choice(self.lab.paths),)
        if t == "archive_search":
            return (r.choice(self.materials), r.choice(["monolayer", "bilayer"]))
        if t == "pid_lookup":
            return (r.choice(self.ids),)
        if t == "sweep_export":
            return (r.choice(self.lab.crystals),)
        if t == "detector_compare":
            return (r.sample(self.ipis, min(20, len(self.ipis))),)
        if t == "own_flakes":
            return (r.choice(self.users),)
        if t == "workbench_page":
            return r.choice(self.keys)
        if t in ("removed_audit", "chip_status"):
            from datetime import timedelta
            return (self.t_max - timedelta(days=30),)
        raise KeyError(t)


# ---------------------------------------------------------------- write profile from timestamps
def cmd_write_profile(_):
    with dst() as c:
        q = lambda s: c.execute(s).fetchall()  # noqa: E731
        per_min = lambda t: q(  # noqa: E731
            "SELECT percentile_cont(array[0.5,0.9,0.99]) WITHIN GROUP (ORDER BY n), max(n), count(*) "
            f"FROM (SELECT date_trunc('minute', created_at) m, count(*) n FROM {t} GROUP BY 1) s")[0]
        img, fl = per_min("image"), per_min("crystallite")
        span_min = q("SELECT extract(epoch FROM max(created_at)-min(created_at))/60 FROM image")[0][0]
        hours = q("SELECT count(DISTINCT date_trunc('hour', created_at)) FROM image")[0][0]
        span_h = float(span_min) / 60
        months = [(m.strftime("%Y-%m"), n) for m, n in q(
            "SELECT date_trunc('month', created_at), count(*) FROM image GROUP BY 1 ORDER BY 1")]
        rev = [(m.strftime("%Y-%m"), n) for m, n in q(
            "SELECT date_trunc('month', user_action_at), count(*) FROM crystallite "
            "WHERE user_action_at IS NOT NULL GROUP BY 1 ORDER BY 1")]
        hour = [(int(h), n) for h, n in q(
            "SELECT extract(hour FROM created_at AT TIME ZONE 'America/Denver'), count(*) FROM image GROUP BY 1 ORDER BY 1")]
    out = dict(
        images_per_active_minute=dict(p50=img[0][0], p90=img[0][1], p99=img[0][2], max=img[1], active_minutes=img[2]),
        flakes_per_active_minute=dict(p50=fl[0][0], p90=fl[0][1], p99=fl[0][2], max=fl[1], active_minutes=fl[2]),
        span_hours=round(span_h, 1), hours_with_writes=hours, hourly_duty=round(hours / span_h, 4),
        minute_duty=round(img[2] / float(span_min), 4),
        images_per_month=months, reviews_per_month=rev, images_by_hour_mdt=hour)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "write_profile.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, default=float)[:800])


# ---------------------------------------------------------------- behaviour model
def cmd_calibrate(_):
    """Latency of each crystallite template with no secondary index and with each candidate alone.
    A candidate is executed against a template only if the planner uses it (EXPLAIN); otherwise the
    no-index latency is kept, which keeps the model cheap on a shared machine."""
    r = random.Random(0)
    with dst() as c:
        c.execute("SET statement_timeout = '20s'")
        A = Args(c, r)
        samples = {t: [A(t) for _ in range(5)] for t in CRYST}

        def lat(t, n=3):
            ms = []
            for a in samples[t][:n]:
                t0 = time.perf_counter()
                c.execute(T[t], a).fetchall()
                ms.append((time.perf_counter() - t0) * 1000)
            return sorted(ms)[len(ms) // 2]

        G.set_indexes(c, [])
        c.execute("ANALYZE crystallite")
        none = {t: lat(t) for t in CRYST}
        print("none", {k: round(v, 1) for k, v in none.items()}, flush=True)
        out = dict(templates={"none": none}, indexes={})
        for ix, body in CANDIDATES.items():
            t0 = time.time()
            c.execute(f"CREATE INDEX {ix} ON {body}")
            build = time.time() - t0
            c.execute("ANALYZE crystallite")
            res = {}
            for t in CRYST:
                plan = json.dumps(c.execute("EXPLAIN (FORMAT JSON) " + T[t], samples[t][0]).fetchone()[0])
                res[t] = lat(t) if ix in plan else none[t]
            size = c.execute("SELECT pg_relation_size(%s)", (ix,)).fetchone()[0]
            c.execute(f"DROP INDEX {ix}")
            out["indexes"][ix] = dict(build_s=round(build, 2), size_mb=round(size / 2**20, 1), latency_ms=res)
            print(ix, round(build, 1), {k: round(v, 1) for k, v in res.items() if v < none[k] * 0.9}, flush=True)
        prev = json.loads((OUT / "behaviour_model.json").read_text())
        out["write_ms_per_flake_batch"] = prev["write_ms_per_flake_batch"]  # measured in E1 on the same copy
        G.set_indexes(c, G.PRODUCTION)
        c.execute("ANALYZE")
    (OUT / "behaviour_model_users.json").write_text(json.dumps(out, indent=1))


def template_rates(users, wscale, wp):
    """Expected calls per second of each crystallite template and flake batches per second."""
    rate = Counter()
    for m, n in users.items():
        per_min, tpl = MODES[m]
        a = n * per_min / 60.0
        if m == "staff":
            for t, w in STAFF_MIX:
                rate[t] += a * w
        else:
            for t in tpl:
                rate[t] += a
    rate["w_flakes"] = wscale * wp["images_per_active_minute"]["p50"] / 60.0
    return rate


def choose(rate, bm):
    none, ix_lat = bm["templates"]["none"], {k: v["latency_ms"] for k, v in bm["indexes"].items()}
    per_ix_write = bm["write_ms_per_flake_batch"]["per_index"]
    tpl = [t for t in CRYST if rate.get(t, 0) > 0]

    def cost(s):
        read = sum(rate[t] * min([none[t]] + [ix_lat[i][t] for i in s]) for t in tpl)
        return read + rate.get("w_flakes", 0) * per_ix_write * len(s)

    chosen = set()
    while True:
        best = min((ix for ix in CANDIDATES if ix not in chosen), key=lambda ix: cost(chosen | {ix}), default=None)
        if best is None or cost(chosen | {best}) >= cost(chosen) - 0.05:
            return chosen
        chosen.add(best)


# ---------------------------------------------------------------- run
def cmd_run(a):
    bm = json.loads((OUT / "behaviour_model_users.json").read_text())
    wp = json.loads((OUT / "write_profile.json").read_text())
    r = random.Random(a.seed)
    c = dst()
    G.set_indexes(c, G.PRODUCTION)
    c.execute("ANALYZE crystallite")
    A = Args(c, random.Random(a.seed * 7 + 1))
    lab = A.lab
    for _ in range(30):
        lab.act("scan")
    t0 = time.time()
    events, done, writes, lock = [], [], [], threading.Lock()
    reviewed = []
    tuner = G.Tuner(events, t0) if a.arm in ("history", "plan") else None
    if tuner:
        tuner.start()
    stop = threading.Event()
    jobs: queue.Queue = queue.Queue()
    hist: list = []  # (t, template) observed calls, for the history tuner

    def worker():
        wc = dst()
        wc.execute("SET statement_timeout = '30s'")
        while True:
            j = jobs.get()
            if j is None:
                return
            arrive, stage, mode, tpls = j
            start = time.time()
            parts, err = {}, None
            for t in tpls:
                ts = time.perf_counter()
                try:
                    rows = wc.execute(T[t], A(t)).fetchall()
                    if t == "review" and rows:
                        ids = [x[0] for x in rows[:5]]
                        wc.execute("UPDATE crystallite SET reviewed=true, classification_h=classification_ai, "
                                   "user_action_at=now() WHERE crystallite_id = ANY(%s)", (ids,))
                        with lock:
                            reviewed.extend(ids)
                except Exception as e:  # timeout under overload counts as a failed action
                    err = type(e).__name__
                parts[t] = (time.perf_counter() - ts) * 1000
            end = time.time()
            with lock:
                done.append(dict(t=arrive - t0, stage=stage, mode=mode, wait_ms=(start - arrive) * 1000,
                                 ms=(end - arrive) * 1000, parts=parts, err=err))
                for t in tpls:
                    hist.append((end, t))

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(POOL)]
    for w in workers:
        w.start()

    wscale = [1.0]

    def writer():  # tile + flake writes at the rate seen in the copy's timestamps
        nxt = time.time()
        while not stop.is_set():
            rate = wscale[0] * wp["images_per_active_minute"]["p50"] / 60.0
            nxt += r.expovariate(rate)
            time.sleep(max(0.0, nxt - time.time()))
            ts = time.time()
            lab.act("scan")
            lat = lab.act("detect") or {}
            writes.append(dict(t=ts - t0, ms=(time.time() - ts) * 1000, flakes_ms=lat.get("w_flakes")))

    wt = threading.Thread(target=writer, daemon=True)
    wt.start()

    def history_rate():
        now = time.time()
        rate = Counter()
        with lock:
            recent = [(ts, t) for ts, t in hist if now - ts < 6 * HALF_LIFE_S]
        for ts, t in recent:  # decayed calls per second
            rate[t] += 0.5 ** ((now - ts) / HALF_LIFE_S) / (HALF_LIFE_S / 0.6931)
        rate["w_flakes"] = wscale[0] * wp["images_per_active_minute"]["p50"] / 60.0
        return rate

    for si, (sname, users, ws) in enumerate(STAGES):
        if a.arm == "plan":  # the allocation calendar announces the next stage's users
            tuner.request(choose(template_rates(users, ws, wp), bm), f"plan: before '{sname}'")
        gap_end = time.time() + GAP_S
        while time.time() < gap_end:
            time.sleep(0.05)
        wscale[0] = ws
        end, next_tick = time.time() + STAGE_S, time.time() + TICK_S
        arrivals = []
        for m, n in users.items():
            lam = n * MODES[m][0] / 60.0
            t = time.time()
            while True:
                t += r.expovariate(lam)
                if t >= end:
                    break
                tpl = [r.choices([x for x, _ in STAFF_MIX], [w for _, w in STAFF_MIX])[0]] if m == "staff" else MODES[m][1]
                arrivals.append((t, m, tpl))
        arrivals.sort()
        for t, m, tpl in arrivals:
            while time.time() < t:
                time.sleep(min(0.01, max(0.0, t - time.time())))
                if tuner and time.time() >= next_tick:
                    next_tick += TICK_S
                    if a.arm == "history":
                        tuner.request(choose(history_rate(), bm), "history: decayed observed calls")
            jobs.put((t, si, m, tpl))
        while time.time() < end:
            time.sleep(0.05)
    # drain: let queued work finish (bounded) so overload is recorded, not dropped
    drain_end = time.time() + 120
    while not jobs.empty() and time.time() < drain_end:
        time.sleep(0.2)
    left = jobs.qsize()
    for _ in workers:
        jobs.put(None)
    for w in workers:
        w.join(timeout=60)
    stop.set()
    wt.join(timeout=10)
    if tuner:
        tuner.stop = True
        tuner.join(timeout=300)
    final = sorted(G.crystallite_indexes(c))
    lab.reviewed += reviewed
    lab.cleanup()
    G.set_indexes(c, G.PRODUCTION)
    meta = dict(arm=a.arm, seed=a.seed, stages=[(s, u, w) for s, u, w in STAGES], stage_s=STAGE_S, gap_s=GAP_S,
                pool=POOL, slo_ms=SLO_MS, final_indexes=final, undrained=left)
    (OUT / f"e2_{a.arm}_s{a.seed}.json").write_text(json.dumps(dict(meta=meta, events=events, actions=done,
                                                                    writes=writes), default=str))
    by = defaultdict(list)
    for d in done:
        by[(d["stage"], d["mode"])].append(d["ms"])
    print(a.arm, a.seed, "actions", len(done), "undrained", left, flush=True)
    for (s, m), v in sorted(by.items()):
        v.sort()
        print(f"  stage {s} {m:10s} n={len(v):4d} p95={v[int(0.95 * (len(v) - 1))]:9.1f} ms", flush=True)


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("write-profile")
    s.add_parser("calibrate")
    rn = s.add_parser("run")
    rn.add_argument("--arm", choices=["production", "history", "plan"], required=True)
    rn.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    {"write-profile": cmd_write_profile, "calibrate": cmd_calibrate, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
