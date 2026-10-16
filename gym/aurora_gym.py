"""Experiment E1 on AURORA: a self-driving DBMS tuning the copy of AURORA's current database.

Data: the copy made by `gym.aurora_src load` (database sddb_aurora on the DGX
PostgreSQL; 6.24 M crystallites, 0.81 M images). Workload: the actions of the
AURORA loop (chip scan, flake detection, review, stacking planner) plus the
web viewer, whose use is measured in production (results/aurora/profile.json).

Starting point for every arm: the index set AURORA runs in production. The
tuner may drop and build crystallite indexes; indexes on the small tables and
on image / image_process_info stay fixed.

    python -m gym.aurora_gym setup            # fixed indexes + production crystallite set
    python -m gym.aurora_gym calibrate        # behaviour model (template x index latency, write cost per index)
    python -m gym.aurora_gym run --arm plan --seed 1
"""
from __future__ import annotations

import argparse
import json
import random
import threading
import time
import uuid
from collections import Counter, deque
from pathlib import Path

from gym.aurora_src import dst

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results" / "aurora"

FIXED = [  # production indexes outside the tuner's scope (all used in production)
    "CREATE INDEX IF NOT EXISTS image_chip_id_idx ON image (chip_id)",
    "CREATE INDEX IF NOT EXISTS image_image_path_idx ON image (image_path)",
    "CREATE INDEX IF NOT EXISTS image_process_info_image_id_idx ON image_process_info (image_id)",
    "CREATE INDEX IF NOT EXISTS image_process_info_processed_image_idx ON image_process_info (is_processed, image_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS export_queue_crystallite_id_key ON export_queue (crystallite_id)",
]
AREA = "((physical_dimensions->>'area_um2')::numeric)"
# Candidate crystallite indexes: the 13 production secondaries plus two that serve the AURORA loop.
PRODUCTION = {
    "crystallite_image_path_idx": "crystallite (image_path)",
    "crystallite_chip_id_idx": "crystallite (chip_id)",
    "crystallite_classification_ai_idx": "crystallite (classification_ai)",
    "crystallite_reviewed_checked": "crystallite (reviewed, h_label_checked)",
    "crystallite_reviewed_idx": "crystallite (reviewed)",
    "crystallite_reviewed_true_created_idx": "crystallite (created_at DESC, crystallite_id DESC) WHERE reviewed = true",
    "crystallite_user_id_idx": "crystallite (user_id)",
    "idx_crystallite_removed_at": "crystallite (removed_at)",
    "crystallite_image_id_idx": "crystallite (image_id)",
    "crystallite_area_num_idx": f"crystallite ({AREA})",
    "idx_crystallite_bulk_crystal_id": "crystallite (bulk_crystal_id)",
    "crystallite_unreviewed_created_idx": "crystallite (created_at, crystallite_id) WHERE reviewed = false OR reviewed IS NULL",
    "crystallite_image_process_info_id_idx": "crystallite (image_process_info_id)",
}
NEW = {
    "ix_review_queue": "crystallite (chip_id, created_at) WHERE reviewed IS NOT TRUE "
                       "AND classification_ai IN ('monolayer', 'bilayer')",
    "ix_monolayer_area": f"crystallite (bulk_crystal_id, {AREA} DESC) WHERE classification_ai = 'monolayer' "
                         "AND removed_at IS NULL",
}
CANDIDATES = {**PRODUCTION, **NEW}

# ---------------------------------------------------------------- templates
# Read templates on crystallite (what the tuner can change) and on the fixed tables.
TEMPLATES = {
    "review": "SELECT crystallite_id FROM crystallite WHERE chip_id=%s AND reviewed IS NOT TRUE "
              "AND classification_ai IN ('monolayer','bilayer') ORDER BY created_at LIMIT 50",
    "planner": f"SELECT crystallite_id, {AREA} AS a FROM crystallite WHERE bulk_crystal_id=%s "
               f"AND classification_ai='monolayer' AND removed_at IS NULL ORDER BY a DESC LIMIT 20",
    "viewer": "SELECT crystallite_id, bounding_box_ai, classification_ai FROM crystallite WHERE image_path=%s",
    "scan_check": "SELECT count(*) FROM image WHERE chip_id=%s",
    "detect_claim": "SELECT image_process_info_id FROM image_process_info WHERE image_id=%s AND is_processed IS NOT TRUE",
}
TUNED = {"review", "planner", "viewer"}

# One lab action = the database calls it makes before the next instrument or agent step.
ANNOUNCED = {"scan", "detect", "review", "plan"}
PHASES = [  # each preceded by an idle window the scheduler announces
    ("chip scan and flake detection", {"scan": 0.25, "detect": 0.65, "view": 0.10}),
    ("review of the new chips",       {"review": 0.70, "detect": 0.20, "view": 0.10}),
    ("stacking planner",              {"plan": 0.60, "review": 0.30, "view": 0.10}),
    ("detection with web viewing",    {"detect": 0.55, "view": 0.45}),
]
PHASE_S, GAP_S, TICK_S, HALF_LIFE_S = 45.0, 15.0, 8.0, 60.0
# Prior for the unannounced part before anything is observed: in production the web viewer's
# image_path lookup is 12,247 of the 12,416 crystallite index scans (profile.json), so both tuners
# start out knowing that the viewer reads crystallites.
PRIOR = [("view", 10)]
FLAKES_PER_IMAGE = 8  # production: 6.24 M crystallites / 0.81 M images


class Lab:
    """Draws parameters from the copy and runs one lab action; tracks rows it wrote for clean-up."""

    def __init__(self, c, r):
        self.c, self.r = c, r
        self.chips = [x[0] for x in c.execute(
            "SELECT DISTINCT chip_id FROM crystallite WHERE reviewed IS NOT TRUE "
            "AND classification_ai IN ('monolayer','bilayer')")]
        self.chip_crystal = dict(c.execute("SELECT chip_id, bulk_crystal_id FROM chip WHERE bulk_crystal_id IS NOT NULL"))
        self.chips = [x for x in self.chips if x in self.chip_crystal]
        self.crystals = [x[0] for x in c.execute("SELECT DISTINCT bulk_crystal_id FROM crystallite "
                                                 "WHERE classification_ai='monolayer' AND bulk_crystal_id IS NOT NULL")]
        self.paths = [x[0] for x in c.execute("SELECT image_path FROM image TABLESAMPLE SYSTEM (2) LIMIT 5000")]
        self.pending = deque()  # images scanned but not yet run through the detector
        self.reviewed, self.exported = [], []

    def q(self, name, arg, lat):
        t0 = time.perf_counter()
        rows = self.c.execute(TEMPLATES[name], (arg,)).fetchall()
        lat[name] = lat.get(name, 0) + (time.perf_counter() - t0) * 1000
        return rows

    def w(self, name, lat, sql, args):
        t0 = time.perf_counter()
        cur = self.c.execute(sql, args)
        lat[name] = lat.get(name, 0) + (time.perf_counter() - t0) * 1000
        return cur

    def act(self, kind):
        r, lat = self.r, {}
        if kind == "scan":  # microscope stores one tile of a chip
            chip = r.choice(self.chips)
            img = uuid.uuid4()
            with self.c.transaction():
                self.w("w_image", lat, "INSERT INTO image (image_id, chip_id, image_path, created_at, updated_at) "
                       "VALUES (%s,%s,%s,now(),now())", (img, chip, f"gym/{chip}/{img}.jpg"))
                self.w("w_image", lat, "INSERT INTO image_process_info (image_process_info_id, image_id, is_processed, "
                       "created_at, updated_at) VALUES (%s,%s,false,now(),now())", (uuid.uuid4(), img))
            self.q("scan_check", chip, lat)
            self.pending.append((img, chip))
        elif kind == "detect":  # detector (or VLM agent) processes one tile and writes its flakes
            if not self.pending:
                return self.act("scan")
            img, chip = self.pending.popleft()
            ipi = self.q("detect_claim", img, lat)[0][0]
            rows = []
            for _ in range(FLAKES_PER_IMAGE):
                cls = r.choices(["thick", "bilayer", "monolayer", "trilayer"], [0.985, 0.007, 0.006, 0.002])[0]
                area = round(r.lognormvariate(4.5, 1.0), 2)
                rows.append((uuid.uuid4(), r.uniform(-50, 50), r.uniform(-50, 50), cls, chip, self.chip_crystal[chip],
                             img, ipi, f"gym/{chip}/{img}.jpg",
                             json.dumps({"area_um2": area}), r.random(), r.random()))
            with self.c.transaction():
                cur = self.c.cursor()
                t0 = time.perf_counter()
                cur.executemany("INSERT INTO crystallite (crystallite_id, x_position, y_position, classification_ai, "
                                "chip_id, bulk_crystal_id, image_id, image_process_info_id, image_path, "
                                "physical_dimensions, classification_confidence_ai, detection_confidence_ai, "
                                "reviewed, h_label_checked, created_at, updated_at) "
                                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,false,now(),now())", rows)
                cur.execute("UPDATE image_process_info SET is_processed=true, updated_at=now() "
                            "WHERE image_process_info_id=%s", (ipi,))
                lat["w_flakes"] = (time.perf_counter() - t0) * 1000
        elif kind == "review":  # a person (or a review agent) confirms the next 5 candidates on a chip
            chip = r.choice(self.chips)
            ids = [x[0] for x in self.q("review", chip, lat)[:5]]
            if ids:
                self.w("w_review", lat, "UPDATE crystallite SET reviewed=true, classification_h=classification_ai, "
                       "user_action_at=now() WHERE crystallite_id = ANY(%s)", (ids,))
                self.reviewed += ids
        elif kind == "plan":  # stacking planner picks the largest monolayers of one crystal and queues one
            rows = self.q("planner", r.choice(self.crystals), lat)
            if rows:
                pick = r.choice(rows)[0]
                cur = self.w("w_export", lat, "INSERT INTO export_queue (id, crystallite_id, added_at) VALUES (%s,%s,now()) "
                             "ON CONFLICT (crystallite_id) DO NOTHING RETURNING id", (uuid.uuid4(), pick))
                if cur.fetchone():
                    self.exported.append(pick)
        elif kind == "view":  # web viewer opens one image and its flakes (not in the lab schedule)
            self.q("viewer", r.choice(self.paths), lat)
        return lat

    def cleanup(self):
        c = self.c
        c.execute("DELETE FROM export_queue WHERE crystallite_id = ANY(%s)", (self.exported,))
        c.execute("UPDATE crystallite SET reviewed=false, classification_h=NULL, user_action_at=NULL "
                  "WHERE crystallite_id = ANY(%s)", (self.reviewed,))
        c.execute("DELETE FROM crystallite WHERE image_path LIKE 'gym/%%'")
        c.execute("DELETE FROM image_process_info WHERE image_id IN (SELECT image_id FROM image WHERE image_path LIKE 'gym/%%')")
        c.execute("DELETE FROM image WHERE image_path LIKE 'gym/%%'")
        c.execute("VACUUM ANALYZE crystallite")


def crystallite_indexes(c):
    return {x[0] for x in c.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' "
                                     "AND tablename='crystallite' AND indexname <> 'crystallite_pkey'")}


def set_indexes(c, want, concurrently=False):
    cc = " CONCURRENTLY" if concurrently else ""
    have = crystallite_indexes(c)
    for ix in sorted(have - set(want)):
        c.execute(f"DROP INDEX{cc} IF EXISTS {ix}")
    for ix in sorted(set(want) - have):
        c.execute(f"CREATE INDEX{cc} IF NOT EXISTS {ix} ON {CANDIDATES[ix]}")


def cmd_setup(_):
    with dst() as c:
        for s in FIXED:
            c.execute(s)
        t0 = time.time()
        set_indexes(c, PRODUCTION)
        c.execute("ANALYZE")
        print("production set built in", round(time.time() - t0, 1), "s")


# ---------------------------------------------------------------- behaviour model
def cmd_calibrate(a):
    """Latency of each tuned template with no candidate index and with each candidate alone; build
    time and size of each candidate; added cost of one flake-batch insert per extra index."""
    r = random.Random(0)
    out = dict(templates={}, indexes={})
    with dst() as c:
        lab = Lab(c, r)
        args = {"review": lambda: r.choice(lab.chips), "planner": lambda: r.choice(lab.crystals),
                "viewer": lambda: r.choice(lab.paths)}

        def measure(n):
            res = {}
            for t in TUNED:
                lat = []
                for _ in range(n):
                    d = {}
                    lab.q(t, args[t](), d)
                    lat.append(d[t])
                res[t] = sorted(lat)[len(lat) // 2]
            return res

        def flake_cost(n=40):
            lab.pending.clear()
            for _ in range(n):
                lab.act("scan")
            ms = [lab.act("detect")["w_flakes"] for _ in range(n)]
            lab.cleanup()
            return sorted(ms)[len(ms) // 2]

        set_indexes(c, [])
        c.execute("ANALYZE crystallite")
        out["templates"]["none"] = measure(3)
        base_write = flake_cost()
        print("none", out["templates"]["none"], "write", round(base_write, 2), flush=True)
        for ix, body in CANDIDATES.items():
            t0 = time.time()
            c.execute(f"CREATE INDEX {ix} ON {body}")
            build = time.time() - t0
            c.execute("ANALYZE crystallite")
            lat = measure(7)
            size = c.execute("SELECT pg_relation_size(%s)", (ix,)).fetchone()[0]
            c.execute(f"DROP INDEX {ix}")
            out["indexes"][ix] = dict(build_s=round(build, 2), size_mb=round(size / 2**20, 1), latency_ms=lat)
            print(ix, out["indexes"][ix], flush=True)
        set_indexes(c, CANDIDATES)
        c.execute("ANALYZE crystallite")
        all_write = flake_cost()
        out["write_ms_per_flake_batch"] = dict(no_secondary=base_write, all_15=all_write,
                                               per_index=(all_write - base_write) / len(CANDIDATES))
        print("write", out["write_ms_per_flake_batch"], flush=True)
        set_indexes(c, PRODUCTION)
        c.execute("ANALYZE")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "behaviour_model.json").write_text(json.dumps(out, indent=1))


# ---------------------------------------------------------------- tuners
def footprint_rates(mix):
    """Expected tuned-template reads and flake-batch writes per lab action."""
    rate = Counter()
    for act, w in mix.items():
        if act == "review":
            rate["review"] += w
        elif act == "plan":
            rate["planner"] += w
        elif act == "view":
            rate["viewer"] += w
        elif act == "detect":
            rate["w_flakes"] += w
    return rate


def choose(rate, bm):
    """Greedy index set: add the candidate with the largest forecast saving per action (read time saved
    minus the extra write time it puts on every flake batch) until none saves time."""
    none, ix_lat = bm["templates"]["none"], {k: v["latency_ms"] for k, v in bm["indexes"].items()}
    per_ix_write = bm["write_ms_per_flake_batch"]["per_index"]

    def cost(s):
        read = sum(rate.get(t, 0) * min([none[t]] + [ix_lat[i][t] for i in s]) for t in TUNED)
        return read + rate.get("w_flakes", 0) * per_ix_write * len(s)

    chosen = set()
    while True:
        best = min((ix for ix in CANDIDATES if ix not in chosen), key=lambda ix: cost(chosen | {ix}), default=None)
        if best is None or cost(chosen | {best}) >= cost(chosen) - 0.05:
            return chosen
        chosen.add(best)


class Tuner(threading.Thread):
    def __init__(self, log, t0):
        super().__init__(daemon=True)
        self.c, self.log, self.t0 = dst(), log, t0
        self.want, self.cv, self.stop = None, threading.Condition(), False

    def request(self, target, why):
        with self.cv:
            self.want = (set(target), why)
            self.cv.notify()

    def run(self):
        while True:
            with self.cv:
                while self.want is None and not self.stop:
                    self.cv.wait(0.2)
                if self.stop and self.want is None:
                    return
                target, why = self.want
                self.want = None
            have = crystallite_indexes(self.c)
            for ix in sorted(have - target):
                self.c.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {ix}")
                self.log.append(dict(t=time.time() - self.t0, action="drop", index=ix, why=why))
            for ix in sorted(target - have):
                ts = time.time()
                self.c.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {ix} ON {CANDIDATES[ix]}")
                self.log.append(dict(t=ts - self.t0, action="build", index=ix, why=why, build_s=time.time() - ts))


def cmd_run(a):
    bm = json.loads((OUT / "behaviour_model.json").read_text())
    r = random.Random(a.seed)
    c = dst()
    set_indexes(c, PRODUCTION)  # every arm starts from what AURORA runs today
    c.execute("ANALYZE crystallite")
    lab = Lab(c, r)
    for _ in range(30):  # a few tiles waiting for the detector at the start
        lab.act("scan")
    events, decisions = [], []
    t0 = time.time()
    tuner = Tuner(events, t0) if a.arm in ("history", "plan") else None
    if tuner:
        tuner.start()
    hist = [(t0, act) for act, n in PRIOR for _ in range(n)]  # (t, action), decayed with HALF_LIFE_S

    def history_rate(only_unannounced=False):
        now = time.time()
        w = Counter()
        for ts, act in hist:
            if not only_unannounced or act not in ANNOUNCED:
                w[act] += 0.5 ** ((now - ts) / HALF_LIFE_S)
        tot = sum(w.values()) or 1.0
        return {k: v / tot for k, v in w.items()}

    def plan_rate(mix):
        announced = {k: v for k, v in mix.items() if k in ANNOUNCED}
        unann = history_rate(only_unannounced=True)
        recent = hist[-200:]
        share = sum(act not in ANNOUNCED for _, act in recent) / max(1, len(recent))
        rate = footprint_rates({k: v * (1 - share) / max(1e-9, sum(announced.values())) for k, v in announced.items()})
        for k, v in footprint_rates({k: v * share for k, v in unann.items()}).items():
            rate[k] += v
        return rate

    for pi, (pname, mix) in enumerate(PHASES):
        gap_end = time.time() + GAP_S
        if a.arm == "plan":
            tuner.request(choose(plan_rate(mix), bm), f"plan: before '{pname}'")
        while time.time() < gap_end:
            time.sleep(0.05)
        ph_end, next_tick = time.time() + PHASE_S, time.time() + TICK_S
        acts, wts = zip(*mix.items())
        while time.time() < ph_end:
            act = r.choices(acts, wts)[0]
            ts = time.time()
            lat = lab.act(act) or {}
            decisions.append(dict(t=ts - t0, phase=pi, action=act, ms=sum(lat.values()), parts=lat))
            hist.append((ts, act))
            if tuner and time.time() >= next_tick:
                next_tick += TICK_S
                if a.arm == "history":
                    tuner.request(choose(footprint_rates(history_rate()), bm), "history: decayed observed mix")
                else:
                    tuner.request(choose(plan_rate(mix), bm), "plan: in-phase, unannounced from history")
    if tuner:
        tuner.stop = True
        tuner.join(timeout=300)
    final = sorted(crystallite_indexes(c))
    lab.cleanup()
    set_indexes(c, PRODUCTION)
    meta = dict(arm=a.arm, seed=a.seed, phases=[p for p, _ in PHASES], phase_s=PHASE_S, gap_s=GAP_S, tick_s=TICK_S,
                half_life_s=HALF_LIFE_S, final_indexes=final)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"e1a_{a.arm}_s{a.seed}.json").write_text(json.dumps(dict(meta=meta, events=events, decisions=decisions)))
    ms = sorted(d["ms"] for d in decisions)
    print(a.arm, a.seed, "decisions", len(ms), "median", round(ms[len(ms) // 2], 2),
          "p95", round(ms[int(0.95 * len(ms))], 2), flush=True)


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("setup")
    s.add_parser("calibrate")
    rn = s.add_parser("run")
    rn.add_argument("--arm", choices=["production", "history", "plan"], required=True)
    rn.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    {"setup": cmd_setup, "calibrate": cmd_calibrate, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
