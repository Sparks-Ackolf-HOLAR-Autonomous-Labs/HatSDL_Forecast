"""E4b on AURORA: an unannounced surge whose size and make-up are unknown in advance.

E4 used one surge (400 API scripts) every seed. A connection split set by hand for that surge
(people 4, scripts 2) protected people as well as the self-driving controller did, so E4 could
not separate the two for people. E4b draws the surge afresh for every seed, with the same
draw for every arm of that seed, and no controller is told its size:

  people burst   research users (archive search, then a persistent-ID lookup) arriving from a
                 citation, a news item or a dataset catalogue; log-uniform 100 to R_MAX users
  script surge   no-pause API scripts as in E4; log-uniform 25 to S_MAX scripts

Both start at SURGE_T, unannounced. Everything else is E4: national people (N2), 600 replayed
LLM agents, the announced workshop at WORKSHOP_T, 6 connections, the same controllers.

Arms: three fixed splits (people and LLM tool calls : scripts = 5:1, 4:2 as in E4, 3:3), the
reactive controller and the self-driving controller (calendar + short-range forecast). The
controllers are unchanged from E4. The shared pool is left out: it failed every E4 seed.

Run:  python -m gym.aurora_surge run --seed 1
      python -m gym.aurora_surge run --seed 1 --research 2000 --scripts 25 --tag cornerA
Output: results/aurora/e4b_surge_s{seed}{tag}.json
"""
import argparse
import json
import math
import random
import time

from gym import aurora_admission as A
from gym import aurora_national as N
from gym import aurora_users as U

ARMS = ["static51", "static", "static33", "reactive", "forecast"]
R_MIN, R_MAX = 100, 2400
S_MIN, S_MAX = 25, 1200


def draw(seed):
    """Surge sizes of a seed: independent of the arm, unknown to every controller."""
    r = random.Random(10_000 + seed)
    lu = lambda lo, hi: int(round(math.exp(r.uniform(math.log(lo), math.log(hi)))))
    return lu(R_MIN, R_MAX), lu(S_MIN, S_MAX)


def cmd_run(a):
    R, S = draw(a.seed)
    R = a.research if a.research is not None else R
    S = a.scripts if a.scripts is not None else S
    sc = {s["key"]: s for s in N.scenarios()}
    people = dict(sc["N2"]["users"])
    tr = A.traces()
    wp, r, c, Aa = N._setup(a.seed)
    svc0 = {}
    for t in U.T:
        ts = []
        for _ in range(5):
            s = time.time()
            try:
                c.execute(U.T[t], Aa(t)).fetchall()
            except Exception:
                pass
            ts.append((time.time() - s) * 1000)
        svc0[t] = sorted(ts)[2]
    print(f"seed {a.seed}: research burst {R} users, script surge {S}", flush=True)
    res = {}
    try:
        for arm in (a.arms or ARMS):
            time.sleep(3)
            Aa.r = random.Random(a.seed * 7 + 1)
            run = A.Run(arm, a.seed, Aa, wp, tr, svc0, n_scripts=S, extra={"research": R})
            info = run.run(people)
            s = A.summarise(run, info)
            s["controller"] = run.trace[::2]
            res[arm] = s
            print(f"{arm:9s} " + " | ".join(
                f"{ph}: people over {100 * s[ph]['people_over']:.1f}% "
                f"llm +{s[ph]['llm_added_s_p95'] or 0:.2f} s scripts {s[ph]['script_served_per_s']:.0f}/s "
                f"p95 {s[ph]['script_p95_ms'] or 0:.0f} ms"
                for ph in ("surge", "workshop")) +
                f" throttled={info['throttled']} left={sum(info['left'].values())} lag95={info['gen_lag_p95_ms']:.0f}ms",
                flush=True)
    finally:
        Aa.lab.cleanup()
    (A.OUT / f"e4b_surge_s{a.seed}{a.tag}.json").write_text(json.dumps(dict(
        seed=a.seed, research=R, scripts=S, step_s=A.STEP_S, surge_t=A.SURGE_T, workshop_t=A.WORKSHOP_T,
        pool=A.POOL, n_llm=A.N_LLM, workshop=A.WORKSHOP, people=people, svc0=svc0, arms=res),
        indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("run")
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--arms", type=lambda x: x.split(","))
    q.add_argument("--research", type=int)
    q.add_argument("--scripts", type=int)
    q.add_argument("--tag", default="")
    sp.add_parser("draws")
    a = p.parse_args()
    if a.cmd == "draws":
        for s in range(1, 31):
            print(s, *draw(s))
        return
    cmd_run(a)


if __name__ == "__main__":
    main()
