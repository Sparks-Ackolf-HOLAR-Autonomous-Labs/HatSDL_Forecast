"""Experiment E2b on AURORA: maximum capacity of the database under the seven user modes.

E2 stopped at the year-4 stage (123 users) and every latency target still held, so it did not
find the limit. This ramp keeps the year-4 mix of user modes (the same seven modes, the same
read templates and latency targets as `aurora_users`) and multiplies the number of users by
k = 1, 2, 4, ... until the share of actions over target passes 5 %. Each step runs open-loop
(Poisson arrivals) through a fixed pool of connections with writes at the year-4 rate, so the
step where queueing takes over is the read capacity for that index set and pool size.

A second ramp holds the year-4 readers and multiplies the write rate (tiles plus their flakes,
from the copy's own timestamps) to find the write capacity.

Index sets are fixed during a ramp (steady state, no tuner): the production set, and the set
the plan-aware tuner chooses for the year-4 mix.

    python -m gym.aurora_capacity reads --arm production --pool 6
    python -m gym.aurora_capacity writes --arm plan --pool 6
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import threading
import time
from collections import defaultdict

import gym.aurora_gym as G
import gym.aurora_users as U
from gym.aurora_src import dst

OUT = U.OUT
YEAR4 = U.STAGES[-1][1]  # users per mode at the year-4 stage
STEP_S, SETTLE_S = 30.0, 3.0
READ_K = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64]
WRITE_K = [1, 5, 10, 25, 50, 100, 200, 400]
STOP_OVER = 0.05  # stop a ramp once more than 5 % of actions miss their target
OK_OVER = 0.01    # capacity = largest step with at most 1 % over target and the queue drained


def index_set(arm, bm, wp):
    if arm == "production":
        return set(G.PRODUCTION)
    return U.choose(U.template_rates(YEAR4, 2.0, wp), bm)


def run_step(A, lab, pool, users, wscale, wp, r):
    """One open-loop step; returns per-action and per-write records."""
    jobs: queue.Queue = queue.Queue()
    done, writes, lock = [], [], threading.Lock()
    stop = threading.Event()

    def worker():
        wc = dst()
        wc.execute("SET statement_timeout = '30s'")
        while True:
            j = jobs.get()
            if j is None:
                return
            arrive, mode, tpls = j
            start = time.time()
            err = None
            for t in tpls:
                try:
                    rows = wc.execute(U.T[t], A(t)).fetchall()
                    if t == "review" and rows:
                        wc.execute("UPDATE crystallite SET reviewed=true, classification_h=classification_ai, "
                                   "user_action_at=now() WHERE crystallite_id = ANY(%s)", ([x[0] for x in rows[:5]],))
                        with lock:
                            lab.reviewed.extend(x[0] for x in rows[:5])
                except Exception as e:  # a timeout under overload counts as a missed action
                    err = type(e).__name__
            end = time.time()
            with lock:
                done.append(dict(mode=mode, ms=(end - arrive) * 1000, svc_ms=(end - start) * 1000, err=err))

    def writer():
        nxt = time.time()
        rate = wscale * wp["images_per_active_minute"]["p50"] / 60.0
        while not stop.is_set():
            nxt += r.expovariate(rate)
            time.sleep(max(0.0, nxt - time.time()))
            if stop.is_set():
                break
            ts = time.time()
            lab.act("scan")
            lab.act("detect")
            writes.append(dict(t=ts, ms=(time.time() - ts) * 1000))

    ws = [threading.Thread(target=worker, daemon=True) for _ in range(pool)]
    for w in ws:
        w.start()
    wt = threading.Thread(target=writer, daemon=True)
    wt.start()
    t_start = time.time()
    end = t_start + STEP_S
    arrivals = []
    for m, n in users.items():
        lam = n * U.MODES[m][0] / 60.0
        t = t_start
        while lam > 0:
            t += r.expovariate(lam)
            if t >= end:
                break
            tpl = ([r.choices([x for x, _ in U.STAFF_MIX], [w for _, w in U.STAFF_MIX])[0]]
                   if m == "staff" else U.MODES[m][1])
            arrivals.append((t, m, tpl))
    arrivals.sort()
    for t, m, tpl in arrivals:
        while time.time() < t:
            time.sleep(min(0.005, max(0.0, t - time.time())))
        jobs.put((t, m, tpl))
    while time.time() < end:
        time.sleep(0.05)
    stop.set()
    # drain for at most one step length; whatever is left is recorded as missed
    drain_end = time.time() + STEP_S
    while not jobs.empty() and time.time() < drain_end:
        time.sleep(0.1)
    left = jobs.qsize()
    while True:
        try:
            jobs.get_nowait()
        except queue.Empty:
            break
    for _ in ws:
        jobs.put(None)
    for w in ws:
        w.join(timeout=60)
    wt.join(timeout=10)
    return done, writes, left, len(arrivals), time.time() - t_start


def summarise(k, users, wscale, done, writes, left, offered, wall):
    over = sum(1 for d in done if d["err"] or d["ms"] > U.SLO_MS[d["mode"]]) + left
    by = defaultdict(list)
    for d in done:
        by[d["mode"]].append(d["ms"])
    p95 = {m: sorted(v)[int(0.95 * (len(v) - 1))] for m, v in by.items()}
    svc = sorted(d["svc_ms"] for d in done)
    wms = sorted(w["ms"] for w in writes)
    return dict(k=k, users=sum(users.values()), write_scale=wscale, offered=offered,
                offered_per_s=offered / STEP_S, served=len(done), undrained=left,
                over_share=over / max(1, offered), p95_ms=p95,
                svc_mean_ms=sum(svc) / max(1, len(svc)),
                tiles_per_min_offered=wscale * 109, tiles_written=len(writes),
                tiles_per_min=len(writes) / STEP_S * 60,
                write_p95_ms=wms[int(0.95 * (len(wms) - 1))] if wms else None, wall_s=wall)


def ramp(a, kind):
    bm = json.loads((OUT / "behaviour_model_users.json").read_text())
    wp = json.loads((OUT / "write_profile.json").read_text())
    r = random.Random(a.seed)
    c = dst()
    want = index_set(a.arm, bm, wp)
    G.set_indexes(c, want)
    c.execute("ANALYZE crystallite")
    A = U.Args(c, random.Random(a.seed * 7 + 1))
    lab = A.lab
    for _ in range(30):
        lab.act("scan")
    steps = []
    try:
        for k in (a.ks or (READ_K if kind == "reads" else WRITE_K)):
            if kind == "reads":
                users, wscale = {m: n * k for m, n in YEAR4.items()}, 2.0
            else:
                users, wscale = dict(YEAR4), 2.0 * k
            time.sleep(SETTLE_S)
            s = summarise(k, users, wscale, *run_step(A, lab, a.pool, users, wscale, wp, r))
            steps.append(s)
            print(f"{kind} {a.arm} pool={a.pool} k={k:3d} users={s['users']:5d} offered={s['offered_per_s']:6.1f}/s "
                  f"over={100 * s['over_share']:5.1f}% undrained={s['undrained']} svc={s['svc_mean_ms']:.1f} ms "
                  f"tiles/min={s['tiles_per_min']:.0f} write_p95={s['write_p95_ms']}", flush=True)
            if s["over_share"] > STOP_OVER and not a.ks:
                break
    finally:
        lab.cleanup()
        G.set_indexes(c, G.PRODUCTION)
    ok = [s for s in steps if s["over_share"] <= OK_OVER and s["undrained"] == 0]
    out = dict(kind=kind, arm=a.arm, pool=a.pool, seed=a.seed, indexes=sorted(want), step_s=STEP_S,
               year4_users=YEAR4, slo_ms=U.SLO_MS, steps=steps, capacity_step=ok[-1] if ok else None)
    (OUT / f"e2b_{kind}_{a.arm}_p{a.pool}_s{a.seed}{a.tag}.json").write_text(json.dumps(out, indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["reads", "writes"])
    p.add_argument("--arm", choices=["production", "plan"], required=True)
    p.add_argument("--pool", type=int, default=6)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--ks", type=lambda x: [int(v) for v in x.split(",")], help="user multipliers (refinement)")
    p.add_argument("--tag", default="", help="suffix of the output file")
    a = p.parse_args()
    ramp(a, a.kind)


if __name__ == "__main__":
    main()
