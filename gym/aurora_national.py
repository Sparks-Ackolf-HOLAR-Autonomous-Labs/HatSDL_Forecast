"""Experiment E2c on AURORA: national open-access demand, not only proposal and workshop users.

E2 and E2b sized the user base from the facility plan's milestones (pilot users, workshops of up
to 125 participants a year, proposals from 20 % of US materials groups by year 4). AURORA is
an open, discoverable national service: anyone can register through the website, the archive
is reachable through the PCL federation and the National Data Platform, and the group's
YouTube channel and podcast give it a national audience. Demand is therefore set by
discovery, courses and machine clients as much as by proposals, and most of it is not on any
allocation calendar.

`demand` turns national scenarios into concurrent users per mode (Little's law: concurrent
users = sessions per hour x session length) with every assumption written out. `run` serves
each scenario on the DGX copy through the same pooled connections as E2b. `burst` sends an
unannounced surge of open traffic on top of the registered users and compares one shared
pool with a per-class connection limit (an admission-control action the database can take).

    python -m gym.aurora_national demand
    python -m gym.aurora_national run --pool 6
    python -m gym.aurora_national burst --seed 1
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

# ---------------------------------------------------------------- modes added for open access
# Public visitor: arrives from a search engine, a video, the NDP catalog or a citation; opens
# flake pages (record by persistent identifier, then the flakes of its tile). No registration.
# API / AI agent: a script or LLM agent of a registered user or another PCL node, querying the
# archive programmatically with no think time between calls.
# Crawler: a search-engine or dataset indexer walking the persistent-identifier pages.
U.MODES.update({
    "visitor": (3, ["pid_lookup", "viewer"]),
    "agent": (30, ["archive_search", "pid_lookup"]),
    "crawler": (600, ["pid_lookup"]),
})
U.SLO_MS.update({"visitor": 300, "agent": 1000, "crawler": 2000})
REGISTERED = {"staff", "novice", "research", "power", "prototype", "industry", "education", "ehs"}
OPEN = {"visitor", "agent", "crawler"}
MACHINE = {"agent", "crawler"}

YEAR4 = U.STAGES[-1][1]

# ---------------------------------------------------------------- national demand scenarios
# Shared assumptions (stated, not measured; change here and rerun `demand`).
A = dict(
    dau_per_mau=0.20,         # share of monthly users active on a given day
    peak_hour_share=0.15,     # share of a day's sessions in the busiest hour (writes: 10:00-17:00)
    session_min=dict(novice=20, research=20, power=30, prototype=20, industry=20, education=30,
                     ehs=10, visitor=4),
    registered_mix=dict(novice=30, research=30, power=8, prototype=4, industry=4, education=40, ehs=3),
)
ANCHORS = {
    "cloudlab_mau": (1400, "CloudLab active users per month (facility plan)"),
    "flux_users": (20000, "researchers and students who have used Flux facilities (facility plan)"),
    "youtube_views": (5.5e6, "views on the Sparks YouTube channel, 760+ videos (facility plan)"),
    "podcast_downloads": (8e5, "Materialism Podcast downloads (facility plan)"),
}


def _registered(mau):
    """Concurrent registered users at the peak hour for a monthly active population `mau`."""
    tot = sum(A["registered_mix"].values())
    out = {}
    for m, w in A["registered_mix"].items():
        sessions_peak_h = mau * w / tot * A["dau_per_mau"] * A["peak_hour_share"]
        out[m] = sessions_peak_h * A["session_min"][m] / 60
    return out


def _visitors(per_day, peak_share=None):
    s = per_day * (peak_share or A["peak_hour_share"])
    return {"visitor": s * A["session_min"]["visitor"] / 60}


def _add(*ds):
    out = defaultdict(float)
    for d in ds:
        for k, v in d.items():
            out[k] += v
    return dict(out)


def scenarios():
    staff = {"staff": 4}
    s = []
    s.append(("P4", "proposal year 4 (E2): workshops and proposals from 20 % of US groups",
              dict(YEAR4), "E2 stage, unchanged"))
    s.append(("N1", "open national service, CloudLab parity",
              _add(staff, _registered(1400), _visitors(5000 / 30)),
              "1,400 registered users a month (CloudLab); 5,000 anonymous visitors a month"))
    s.append(("N2", "open national service, 10x CloudLab",
              _add(staff, _registered(14000), _visitors(50000 / 30)),
              "14,000 registered users a month (Flux lifetime 20,000 users as the ceiling); "
              "50,000 visitors a month"))
    s.append(("N3", "N2 + synchronous classes",
              _add(staff, _registered(14000), _visitors(50000 / 30), {"education": 8 * 40 + 2 * 30}),
              "8 university classes of 40 and 2 K-12 classrooms of 30 on the Workbench in the same hour"))
    s.append(("N4", "N2 + machine clients",
              _add(staff, _registered(14000), _visitors(50000 / 30), {"agent": 50, "crawler": 2}),
              "50 API scripts or AI agents (30 queries/min each) and 2 crawlers (10 pages/s each)"))
    s.append(("B1", "N2 + media burst, 30,000 visits in a day",
              _add(staff, _registered(14000), _visitors(30000, 0.25)),
              "a video or news item linking to the archive; 25 % of the day's visits in its first hour"))
    s.append(("B2", "N2 + media burst, 100,000 visits in a day",
              _add(staff, _registered(14000), _visitors(100000, 0.25)),
              "a widely shared post (national news, social media); 25 % in the first hour"))
    s.append(("W", "worst plausible hour: N3 + N4 + B2",
              _add(staff, _registered(14000), _visitors(100000, 0.25),
                   {"education": 8 * 40 + 2 * 30, "agent": 50, "crawler": 2}),
              "all of the above at once"))
    out = []
    for key, name, users, note in s:
        users = {m: round(v, 1) for m, v in users.items() if v > 0}
        per_s = sum(n * U.MODES[m][0] / 60 for m, n in users.items())
        out.append(dict(key=key, name=name, note=note, users=users, users_total=round(sum(users.values())),
                        actions_per_s=round(per_s, 1),
                        open_share=round(sum(n * U.MODES[m][0] / 60 for m, n in users.items() if m in OPEN)
                                         / max(per_s, 1e-9), 3)))
    return out


def cmd_demand(_):
    sc = scenarios()
    (OUT / "e2c_demand.json").write_text(json.dumps(dict(assumptions=A, anchors=ANCHORS, scenarios=sc), indent=1))
    for s in sc:
        print(f"{s['key']:3s} users={s['users_total']:5d} actions/s={s['actions_per_s']:6.1f} "
              f"open={100 * s['open_share']:4.0f}%  {s['name']}")


# ---------------------------------------------------------------- serving one scenario
def run_step(Aa, lab, users, wp, r, step_s, pools, burst=None):
    """Open-loop step. `pools` maps a class name ('all', or 'registered'/'open') to its number of
    connections; each mode goes to its class queue. `burst` = (t0_s, extra_users) is added to the
    offered load from t0_s without any announcement. Returns per-action records."""
    split = "all" not in pools
    qs = {k: queue.Queue() for k in pools}
    done, lock = [], threading.Lock()
    stop = threading.Event()

    def cls(m):
        if not split:
            return "all"
        if "machine" in pools:
            return "machine" if m in MACHINE else "human"
        return "open" if m in OPEN else "registered"

    def worker(q):
        wc = dst()
        wc.execute("SET statement_timeout = '30s'")
        while True:
            j = q.get()
            if j is None:
                return
            arrive, mode, tpls, phase = j
            start, err = time.time(), None
            for t in tpls:
                try:
                    wc.execute(U.T[t], Aa(t)).fetchall()
                except Exception as e:  # a timeout under overload counts as a missed action
                    err = type(e).__name__
            end = time.time()
            with lock:
                done.append(dict(mode=mode, phase=phase, t=arrive, ms=(end - arrive) * 1000,
                                 svc_ms=(end - start) * 1000, err=err))

    def writer():
        nxt = time.time()
        rate = 2.0 * wp["images_per_active_minute"]["p50"] / 60.0
        while not stop.is_set():
            nxt += r.expovariate(rate)
            time.sleep(max(0.0, nxt - time.time()))
            if stop.is_set():
                break
            lab.act("scan")
            lab.act("detect")

    ws = []
    for k, n in pools.items():
        for _ in range(n):
            w = threading.Thread(target=worker, args=(qs[k],), daemon=True)
            w.start()
            ws.append((k, w))
    wt = threading.Thread(target=writer, daemon=True)
    wt.start()
    t0 = time.time()
    end = t0 + step_s
    arrivals = []

    def gen(us, start, phase):
        for m, n in us.items():
            lam = n * U.MODES[m][0] / 60.0
            t = start
            while lam > 0:
                t += r.expovariate(lam)
                if t >= end:
                    break
                tpl = ([r.choices([x for x, _ in U.STAFF_MIX], [w for _, w in U.STAFF_MIX])[0]]
                       if m == "staff" else U.MODES[m][1])
                arrivals.append((t, m, tpl, phase))

    gen(users, t0, "base")
    if burst:
        gen(burst[1], t0 + burst[0], "burst")
    arrivals.sort()
    lag = []
    for t, m, tpl, ph in arrivals:
        while time.time() < t:
            time.sleep(min(0.005, max(0.0, t - time.time())))
        lag.append(time.time() - t)
        qs[cls(m)].put((t, m, tpl, ph))
    gen_lag_p95_ms = sorted(lag)[int(0.95 * (len(lag) - 1))] * 1000 if lag else 0.0
    while time.time() < end:
        time.sleep(0.05)
    stop.set()
    drain_end = time.time() + step_s
    while any(not q.empty() for q in qs.values()) and time.time() < drain_end:
        time.sleep(0.1)
    left = defaultdict(int)
    for k, q in qs.items():
        while True:
            try:
                j = q.get_nowait()
                left[j[1]] += 1
            except queue.Empty:
                break
    for k, w in ws:
        qs[k].put(None)
    for _, w in ws:
        w.join(timeout=60)
    wt.join(timeout=10)
    return done, dict(left), len(arrivals), gen_lag_p95_ms


def summarise(done, left, offered, step_s, t0=None):
    by = defaultdict(list)
    for d in done:
        by[d["mode"]].append(d)
    modes = {}
    for m in set(by) | set(left):
        v = by.get(m, [])
        ms = sorted(x["ms"] for x in v)
        over = sum(1 for x in v if x["err"] or x["ms"] > U.SLO_MS[m]) + left.get(m, 0)
        n = len(v) + left.get(m, 0)
        modes[m] = dict(n=n, over_share=over / max(1, n), p95_ms=ms[int(0.95 * (len(ms) - 1))] if ms else None,
                        p50_ms=ms[len(ms) // 2] if ms else None)

    def share(sel):
        n = sum(modes[m]["n"] for m in modes if sel(m))
        o = sum(modes[m]["over_share"] * modes[m]["n"] for m in modes if sel(m))
        return o / max(1, n)

    svc = [d["svc_ms"] for d in done]
    return dict(offered=offered, offered_per_s=offered / step_s, served=len(done), undrained=sum(left.values()),
                over_share=share(lambda m: True), registered_over=share(lambda m: m in REGISTERED),
                open_over=share(lambda m: m in OPEN), svc_mean_ms=sum(svc) / max(1, len(svc)), modes=modes)


def _setup(seed):
    wp = json.loads((OUT / "write_profile.json").read_text())
    r = random.Random(seed)
    c = dst()
    G.set_indexes(c, set(G.PRODUCTION))
    c.execute("ANALYZE crystallite")
    Aa = U.Args(c, random.Random(seed * 7 + 1))
    for _ in range(30):
        Aa.lab.act("scan")
    return wp, r, c, Aa


def cmd_run(a):
    wp, r, c, Aa = _setup(a.seed)
    steps = []
    try:
        for s in scenarios():
            if a.only and s["key"] not in a.only:
                continue
            time.sleep(3)
            done, left, offered, lag = run_step(Aa, Aa.lab, s["users"], wp, r, a.step_s, {"all": a.pool})
            x = summarise(done, left, offered, a.step_s)
            x.update(key=s["key"], name=s["name"], users_total=s["users_total"], gen_lag_p95_ms=lag)
            steps.append(x)
            print(f"{s['key']:3s} users={s['users_total']:5d} offered={x['offered_per_s']:6.1f}/s "
                  f"over={100 * x['over_share']:5.1f}% registered={100 * x['registered_over']:5.1f}% "
                  f"open={100 * x['open_over']:5.1f}% undrained={x['undrained']} svc={x['svc_mean_ms']:.0f} ms",
                  flush=True)
    finally:
        Aa.lab.cleanup()
    (OUT / f"e2c_run_p{a.pool}_s{a.seed}{a.tag}.json").write_text(
        json.dumps(dict(pool=a.pool, seed=a.seed, step_s=a.step_s, steps=steps), indent=1, default=str))


def cmd_ramp(a):
    """Multiply one scenario (or only its machine clients) by k until targets fail."""
    sc = {s["key"]: s for s in scenarios()}
    base = sc[a.base]["users"]
    wp, r, c, Aa = _setup(a.seed)
    steps = []
    try:
        for k in a.ks:
            users = ({m: (n * k if m == "agent" else n) for m, n in base.items()} if a.agents_only
                     else {m: n * k for m, n in base.items()})
            time.sleep(3)
            done, left, offered, lag = run_step(Aa, Aa.lab, users, wp, r, a.step_s, {"all": a.pool})
            x = summarise(done, left, offered, a.step_s)
            x.update(k=k, users=users, users_total=round(sum(users.values())), gen_lag_p95_ms=lag)
            steps.append(x)
            print(f"{a.base} k={k:g} users={x['users_total']:6d} offered={x['offered_per_s']:7.1f}/s "
                  f"over={100 * x['over_share']:5.1f}% registered={100 * x['registered_over']:5.1f}% "
                  f"open={100 * x['open_over']:5.1f}% undrained={x['undrained']} svc={x['svc_mean_ms']:.0f} ms "
                  f"gen_lag_p95={lag:.0f} ms", flush=True)
            if x["over_share"] > 0.05:
                break
    finally:
        Aa.lab.cleanup()
    tag = "agents" if a.agents_only else "all"
    (OUT / f"e2c_ramp_{a.base}_{tag}_p{a.pool}_s{a.seed}.json").write_text(
        json.dumps(dict(base=a.base, agents_only=a.agents_only, pool=a.pool, seed=a.seed, step_s=a.step_s,
                        steps=steps), indent=1, default=str))


def cmd_burst(a):
    """Registered users at N2 plus an unannounced surge of `--agents` API/AI agents 20 s into a 60 s step."""
    sc = {s["key"]: s for s in scenarios()}
    base = sc["N2"]["users"]
    extra = {"agent": a.agents}
    wp, r, c, Aa = _setup(a.seed)
    arms = {"shared": {"all": 6}, "class_limit": {"registered": 2, "open": 4},
            "machine_limit": {"human": 4, "machine": 2}}
    arms = {k: v for k, v in arms.items() if not a.arms or k in a.arms}
    out = {}
    try:
        for arm, pools in arms.items():
            time.sleep(3)
            done, left, offered, lag = run_step(Aa, Aa.lab, base, wp, r, 60.0, pools, burst=(20.0, extra))
            t0 = min(d["t"] for d in done) if done else 0
            pre = [d for d in done if d["t"] - t0 < 20]
            post = [d for d in done if d["t"] - t0 >= 20]
            x = dict(all=summarise(done, left, offered, 60.0),
                     before=summarise(pre, {}, len(pre), 20.0),
                     during=summarise(post, left, len(post) + sum(left.values()), 40.0))
            out[arm] = dict(pools=pools, **x)
            d = x["during"]
            hv = x["during"]["modes"].get("visitor", {}).get("over_share", 0)
            print(f"visitors over {100 * hv:.1f}%  ", end="")
            print(f"{arm:12s} before: registered over {100 * x['before']['registered_over']:.1f}%  "
                  f"during burst: registered over {100 * d['registered_over']:.1f}% "
                  f"open over {100 * d['open_over']:.1f}% undrained={d['undrained']}", flush=True)
    finally:
        Aa.lab.cleanup()
    (OUT / f"e2c_burst_a{a.agents}_s{a.seed}{'_' + '_'.join(a.arms) if a.arms else ''}.json").write_text(
        json.dumps(dict(seed=a.seed, base="N2", burst_extra=extra, arms=out), indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("demand")
    q = sp.add_parser("run")
    q.add_argument("--pool", type=int, default=6)
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--step-s", type=float, default=30.0)
    q.add_argument("--only", type=lambda x: x.split(","))
    q.add_argument("--tag", default="")
    b = sp.add_parser("burst")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--agents", type=int, default=400)
    b.add_argument("--arms", type=lambda x: x.split(","))
    m = sp.add_parser("ramp")
    m.add_argument("--base", default="W")
    m.add_argument("--agents-only", action="store_true")
    m.add_argument("--ks", type=lambda x: [float(v) for v in x.split(",")], default=[1, 2, 4, 8, 16])
    m.add_argument("--pool", type=int, default=6)
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--step-s", type=float, default=30.0)
    a = p.parse_args()
    {"demand": cmd_demand, "run": cmd_run, "burst": cmd_burst, "ramp": cmd_ramp}[a.cmd](a)


if __name__ == "__main__":
    main()
