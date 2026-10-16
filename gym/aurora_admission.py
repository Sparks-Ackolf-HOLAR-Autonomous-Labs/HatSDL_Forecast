"""E4 on AURORA: the database sets its own admission control (connection split and machine-client
rate limit) from the plan and a short-horizon forecast, judged on end-to-end time per user class.

E2c showed that unannounced no-pause API scripts push people over their targets on a shared pool,
and that a hand-set split (people 4, machines 2) protects people. E3 measured LLM agents: a tool
call waits 5-40 s of model time on each side, so an agent decision lasts 8-90 s and the database
is under 0.3 % of it. E4 puts the three kinds of client on the same 6 connections:

  people     the seven planned user modes at the N2 national level (E2c) plus public visitors;
             a workshop of 8 classes (education) arrives at an announced time
  LLM agents decisions replayed from the E3 traces (specialist and generic agent): model time is
             waited out, every database tool call goes through the database for real
  scripts    no-pause API clients (30 actions/min each, as the E2c "agent" mode); an unannounced
             surge starts part-way through

Arms (same arrivals for every arm within a seed):
  shared     one queue, 6 connections, no limits (what a default server does)
  static     interactive (people + LLM tool calls) 4, scripts 2, no rate limit (E2c hand-set)
  reactive   history only: every 2 s, moves one connection to the class whose recent actions
             missed their target and caps scripts at what their connections served
  forecast   self-driving: every 1 s, forecasts each class's database work for the next 10 s
             from the calendar (workshop) plus an exponentially weighted arrival rate, splits the
             connections by forecast work and sets the script rate to what the script
             connections can serve; scripts above it are told to retry 1 s later (HTTP 429)

Run:  python -m gym.aurora_admission run --seed 1
Output: results/aurora/e4_admission_s{seed}.json
"""
import argparse
import heapq
import itertools
import json
import math
import queue
import random
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from gym import aurora_gym as G
from gym import aurora_national as N
from gym import aurora_users as U
from gym.aurora_src import dst

OUT = U.OUT
HERE = Path(__file__).resolve().parent
AGENTS = HERE.parent / "results" / "aurora_agents"

STEP_S, SURGE_T, WORKSHOP_T, DRAIN_S = 120.0, 30.0, 70.0, 30.0
POOL = 6
N_LLM = 600          # concurrent LLM agent sessions (back-to-back decisions, 10 s pause)
LLM_PAUSE_S = 10.0
N_SCRIPTS = 400      # unannounced no-pause API scripts from SURGE_T
WORKSHOP = {"education": 8 * 40}
SCRIPT_SLO_MS = 1000
LLM_CALL_SLO_MS = 1000
ARMS = ["shared", "static", "reactive", "forecast"]
# E3 task -> read template of the AURORA copy used for its database tool call
TASK_T = {"research": "archive_search", "novice": "chip_summary", "pid": "pid_lookup",
          "planner": "planner", "tile": "viewer", "ehs": "removed_audit"}
NO_DB = {"list_skills", "read_skill"}


def traces():
    """E3 decisions as [(model_s, n_db_calls)] per turn, with the template of their database calls."""
    out = []
    for f in ("e3_A.jsonl", "e3_A-V.jsonl", "e3_B.jsonl"):
        p = AGENTS / f
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            d = json.loads(line)
            if not d.get("finished", True):
                continue
            turns = [(t["model_s"], sum(1 for x in t["tools"] if x["name"] not in NO_DB)) for t in d["turns"]]
            out.append(dict(case=d["case"], tpl=TASK_T.get(d["task"], "pid_lookup"), turns=turns))
    return out


def klass(mode):
    return "script" if mode == "script" else ("llm" if mode == "llm" else "people")


class Run:
    def __init__(self, arm, seed, Aa, wp, tr, svc0, n_scripts=None, extra=None):
        self.arm, self.Aa, self.wp, self.tr = arm, Aa, wp, tr
        self.n_scripts = N_SCRIPTS if n_scripts is None else n_scripts
        self.extra = extra or {}                  # unannounced people burst from SURGE_T (E4b)
        self.r = random.Random(seed)            # arrivals: identical across arms of a seed
        self.heap, self.hl, self.seq = [], threading.Lock(), itertools.count()
        self.done, self.decisions, self.trace = [], [], []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        split = arm != "shared"
        self.qs = {"interactive": queue.Queue(), "bulk": queue.Queue()} if split else {"all": queue.Queue()}
        n_i = int(arm[6]) if arm.startswith("static") and len(arm) > 6 else 4   # static51, static33 (E4b)
        self.assign = (["all"] * POOL if not split else ["interactive"] * n_i + ["bulk"] * (POOL - n_i))
        self.rate = None                          # script admissions per s (None = unlimited)
        self.tokens, self.tok_t = 0.0, None
        self.throttled = 0
        self.dropped = 0
        self.svc = dict(svc0)                     # template -> mean service ms (behaviour model, online)
        self.arr = defaultdict(deque)             # class -> recent arrival times
        self.recent = deque()                     # (t_done, class, over)

    # ------------------------------------------------------------ events
    def push(self, t, kind, payload):
        with self.hl:
            heapq.heappush(self.heap, (t, next(self.seq), kind, payload))

    def qname(self, cls):
        if "all" in self.qs:
            return "all"
        return "bulk" if cls == "script" else "interactive"

    def submit(self, t_arr, mode, tpls, extra=None):
        cls = klass(mode)
        self.arr[cls].append(time.time())
        self.qs[self.qname(cls)].put((t_arr, time.time(), mode, tpls, extra))

    # ------------------------------------------------------------ workers
    def worker(self, i):
        wc = dst()
        wc.execute("SET statement_timeout = '30s'")
        while not self.stop.is_set():
            j = None
            if self.arm == "forecast" and self.assign[i] == "bulk":
                try:  # unreserved connection: people and LLM tool calls first, scripts with what is left
                    j = self.qs["interactive"].get_nowait()
                except queue.Empty:
                    pass
            if j is None:
                try:
                    j = self.qs[self.assign[i]].get(timeout=0.05)
                except queue.Empty:
                    continue
            t_arr, t_q, mode, tpls, extra = j
            start, err = time.time(), None
            for t in tpls:
                try:
                    wc.execute(U.T[t], self.Aa(t)).fetchall()
                except Exception as e:
                    err = type(e).__name__
            end = time.time()
            ms, svc = (end - t_arr) * 1000, (end - start) * 1000
            key = "+".join(tpls)
            with self.lock:
                self.svc[key] = 0.9 * self.svc.get(key, svc) + 0.1 * svc
            slo = (SCRIPT_SLO_MS if mode == "script" else LLM_CALL_SLO_MS if mode == "llm" else U.SLO_MS[mode])
            over = bool(err) or ms > slo
            with self.lock:
                self.done.append(dict(mode=mode, t=t_arr - self.t0, ms=ms, svc_ms=svc, wait_ms=(start - t_q) * 1000,
                                      err=err, over=over))
                self.recent.append((end, klass(mode), over))
            if mode == "llm":
                self.llm_call_done(extra, end, ms)

    # ------------------------------------------------------------ LLM agents (E3 traces)
    def llm_start(self, sess, t):
        d = self.r.choice(self.tr)
        st = dict(sess=sess, d=d, turn=0, t0=t, db_ms=0.0, pending=0)
        self.push(t + d["turns"][0][0], "llm_turn", st)

    def llm_turn(self, st, now):
        n = st["d"]["turns"][st["turn"]][1]
        if n == 0:
            self.llm_next(st, now)
            return
        st["pending"] = n
        for _ in range(n):
            self.submit(now, "llm", [st["d"]["tpl"]], st)

    def llm_call_done(self, st, end, ms):
        st["db_ms"] += ms
        st["pending"] -= 1
        if st["pending"] == 0:
            self.llm_next(st, end)

    def llm_next(self, st, now):
        st["turn"] += 1
        turns = st["d"]["turns"]
        if st["turn"] < len(turns):
            self.push(now + turns[st["turn"]][0], "llm_turn", st)
            return
        with self.lock:
            self.decisions.append(dict(case=st["d"]["case"], start=st["t0"] - self.t0, s=now - st["t0"],
                                       model_s=sum(m for m, _ in turns), db_ms=st["db_ms"]))
        if now - self.t0 < STEP_S:
            self.push(now + LLM_PAUSE_S, "llm_start", st["sess"])

    # ------------------------------------------------------------ controllers
    def forecast_rate(self, cls, now, hl=3.0):
        """Exponentially weighted arrival rate per s over the recent arrivals of a class."""
        dq = self.arr[cls]
        while dq and now - dq[0] > 15:
            dq.popleft()
        w = sum(0.5 ** ((now - t) / hl) for t in dq)
        return w / (hl / math.log(2))

    def mean_svc(self, tpls):
        key = "+".join(tpls)
        if key in self.svc:
            return self.svc[key]
        return sum(self.svc.get(t, 5.0) for t in tpls)

    def control(self):
        tick = 2.0 if self.arm == "reactive" else 1.0
        nxt = time.time() + tick
        calm = 0.0
        while not self.stop.is_set():
            time.sleep(max(0.0, nxt - time.time()))
            nxt += tick
            now = time.time()
            el = now - self.t0
            if self.arm == "reactive":
                with self.lock:
                    while self.recent and now - self.recent[0][0] > 5:
                        self.recent.popleft()
                    rec = list(self.recent)
                inter = [o for _, c, o in rec if c != "script"]
                scr = [o for _, c, o in rec if c == "script"]
                over_i = sum(inter) / max(1, len(inter))
                nb = self.assign.count("bulk")
                if over_i > 0.02 and nb > 1:
                    self.assign[self.assign.index("bulk")] = "interactive"
                    calm = 0.0
                elif over_i < 0.005 and self.qs["interactive"].qsize() == 0:
                    calm += tick
                    if calm >= 10 and nb < 3:
                        self.assign[self.assign.index("interactive")] = "bulk"
                        calm = 0.0
                if len(scr) > 20:   # cap scripts at what they were served in the last 5 s, probing 10 % up
                    self.rate = max(5.0, 1.1 * len(scr) / 5.0)
            else:  # forecast
                horizon = 10.0
                # work per s by class = forecast arrivals x service ms of what that class calls
                work = {}
                for cls in ("people", "llm", "script"):
                    work[cls] = self.forecast_rate(cls, now) * self.cls_ms[cls]
                if WORKSHOP_T - horizon <= el:   # calendar: the workshop is announced
                    work["people"] += sum(n * U.MODES[m][0] / 60 for m, n in WORKSHOP.items()) * \
                        self.mean_svc(U.MODES["education"][1])
                inter = (work["people"] + work["llm"]) / 1000.0     # connection-seconds per s
                need_i = min(POOL - 1, max(2, math.ceil(inter * 2.0 + 0.5)))  # headroom x2 for queueing
                nb = POOL - need_i
                self.assign[:] = ["interactive"] * need_i + ["bulk"] * nb
                ms_script = self.cls_ms["script"]
                free_ms = POOL * 1000.0 - 1.5 * inter * 1000.0   # connection-ms per s left after people + LLM
                self.rate = max(2.0, 0.9 * free_ms / max(ms_script, 1.0))
            self.trace.append(dict(t=round(el, 2), interactive=self.assign.count("interactive"),
                                   bulk=self.assign.count("bulk"), rate=self.rate))

    @property
    def cls_ms(self):
        return {"people": self.people_ms, "llm": self.mean_svc(["archive_search"]) * 0.5 +
                self.mean_svc(["pid_lookup"]) * 0.5, "script": self.mean_svc(N.U.MODES["agent"][1])}

    # ------------------------------------------------------------ one arm
    def run(self, people):
        tot = sum(n * U.MODES[m][0] for m, n in people.items())
        self.people_ms = sum(n * U.MODES[m][0] * (self.mean_svc(self.staff_tpl()) if m == "staff"
                                                  else self.mean_svc(U.MODES[m][1]))
                             for m, n in people.items()) / max(tot, 1)
        ws = [threading.Thread(target=self.worker, args=(i,), daemon=True) for i in range(POOL)]
        for w in ws:
            w.start()
        wt = threading.Thread(target=self.writer, daemon=True)
        self.t0 = t0 = time.time()
        wt.start()
        end = t0 + STEP_S
        # open-loop arrivals (people from 0, workshop at WORKSHOP_T, scripts from SURGE_T)
        def gen(us, start, mode_override=None):
            for m, n in us.items():
                lam = n * U.MODES[m][0] / 60.0
                t = start
                while lam > 0:
                    t += self.r.expovariate(lam)
                    if t >= end:
                        break
                    mode = mode_override or m
                    tpl = ([self.r.choices([x for x, _ in U.STAFF_MIX], [w for _, w in U.STAFF_MIX])[0]]
                           if m == "staff" else U.MODES[m][1])
                    self.push(t, "arrive", (mode, tpl, t))
        gen(people, t0)
        gen(WORKSHOP, t0 + WORKSHOP_T)
        gen({"agent": self.n_scripts}, t0 + SURGE_T, "script")
        if self.extra:
            gen(self.extra, t0 + SURGE_T)
        for s in range(N_LLM):
            self.push(t0 + self.r.uniform(0, 20), "llm_start", s)
        if self.arm in ("reactive", "forecast"):
            ct = threading.Thread(target=self.control, daemon=True)
            ct.start()
        lag = []
        while True:
            now = time.time()
            if now > end + DRAIN_S:
                break
            with self.hl:
                ev = heapq.heappop(self.heap) if self.heap and self.heap[0][0] <= now else None
            if ev is None:
                if now > end and all(q.empty() for q in self.qs.values()):
                    break
                time.sleep(0.002)
                continue
            t, _, kind, p = ev
            lag.append(now - t)
            if kind == "arrive":
                mode, tpl, t_first = p[:3]
                tries = p[3] if len(p) > 3 else 0
                if mode == "script" and self.rate is not None:
                    if self.tok_t is None:
                        self.tok_t = now
                    self.tokens = min(self.rate, self.tokens + (now - self.tok_t) * self.rate)
                    self.tok_t = now
                    full = (self.arm == "forecast" and  # admit only what can be answered within the target
                            self.qs["bulk"].qsize() >= max(1, int(self.rate * SCRIPT_SLO_MS / 1000)))
                    if self.tokens < 1.0 or full:
                        self.throttled += 1
                        if tries < 4 and now + 2 ** tries < end:  # 429: retry after 1, 2, 4, 8 s
                            self.push(now + 2 ** tries, "arrive", (mode, tpl, t_first, tries + 1))
                        else:
                            self.dropped += 1
                        continue
                    self.tokens -= 1.0
                self.submit(t_first, mode, tpl)
            elif kind == "llm_start":
                if now < end:
                    self.llm_start(p, now)
            elif kind == "llm_turn":
                self.llm_turn(p, now)
        self.stop.set()
        left = defaultdict(int)
        for q in self.qs.values():
            while True:
                try:
                    left[q.get_nowait()[2]] += 1
                except queue.Empty:
                    break
        for w in ws:
            w.join(timeout=60)
        wt.join(timeout=10)
        lag.sort()
        return dict(left=dict(left), throttled=self.throttled, dropped=self.dropped,
                    gen_lag_p95_ms=lag[int(0.95 * (len(lag) - 1))] * 1000 if lag else 0.0)

    def staff_tpl(self):
        return ["review"]

    def writer(self):
        nxt = time.time()
        rate = 2.0 * self.wp["images_per_active_minute"]["p50"] / 60.0
        wr = random.Random(7)
        while not self.stop.is_set():
            nxt += wr.expovariate(rate)
            time.sleep(max(0.0, nxt - time.time()))
            if self.stop.is_set():
                break
            self.Aa.lab.act("scan")
            self.Aa.lab.act("detect")


def phase(t):
    return "before" if t < SURGE_T else ("surge" if t < WORKSHOP_T else "workshop")


def summarise(run, info):
    out = {}
    for ph in ("before", "surge", "workshop"):
        d = [x for x in run.done if phase(x["t"]) == ph]
        by = defaultdict(list)
        for x in d:
            by[x["mode"]].append(x)

        def pct(v, q):
            v = sorted(v)
            return v[int(q * (len(v) - 1))] if v else None
        people = [x for x in d if klass(x["mode"]) == "people"]
        scripts = [x for x in d if x["mode"] == "script"]
        llm = [x for x in d if x["mode"] == "llm"]
        span = SURGE_T if ph == "before" else (WORKSHOP_T - SURGE_T if ph == "surge" else STEP_S - WORKSHOP_T)
        dec = [x for x in run.decisions if phase(x["start"]) == ph]
        out[ph] = dict(
            people_over=sum(x["over"] for x in people) / max(1, len(people)), people_n=len(people),
            people_p95_ms=pct([x["ms"] for x in people], 0.95),
            modes={m: dict(n=len(v), over=sum(x["over"] for x in v) / len(v), p95_ms=pct([x["ms"] for x in v], 0.95))
                   for m, v in by.items()},
            llm_call_p95_ms=pct([x["ms"] for x in llm], 0.95), llm_call_over=sum(x["over"] for x in llm) / max(1, len(llm)),
            llm_decisions=len(dec), llm_decision_p50_s=pct([x["s"] for x in dec], 0.5),
            llm_decision_p95_s=pct([x["s"] for x in dec], 0.95),
            llm_db_share=(sum(x["db_ms"] for x in dec) / 1000) / max(1e-9, sum(x["s"] for x in dec)),
            llm_added_s_p95=pct([x["s"] - x["model_s"] for x in dec], 0.95),
            script_served_per_s=len(scripts) / span, script_p95_ms=pct([x["ms"] for x in scripts], 0.95),
            script_over=sum(x["over"] for x in scripts) / max(1, len(scripts)))
    out["throttled"] = info["throttled"]
    out["dropped"] = info["dropped"]
    out["undrained"] = info["left"]
    out["gen_lag_p95_ms"] = info["gen_lag_p95_ms"]
    return out


def cmd_run(a):
    sc = {s["key"]: s for s in N.scenarios()}
    people = dict(sc["N2"]["users"])
    tr = traces()
    wp, r, c, Aa = N._setup(a.seed)
    # behaviour model: service ms per template measured once on this copy (no load)
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
    res = {}
    try:
        for arm in (a.arms or ARMS):
            time.sleep(3)
            Aa.r = random.Random(a.seed * 7 + 1)
            run = Run(arm, a.seed, Aa, wp, tr, svc0)
            info = run.run(people)
            s = summarise(run, info)
            s["controller"] = run.trace[::2]
            res[arm] = s
            print(f"{arm:9s} " + " | ".join(
                f"{ph}: people over {100 * s[ph]['people_over']:.1f}% llm call p95 {s[ph]['llm_call_p95_ms'] or 0:.0f} ms "
                f"llm +{s[ph]['llm_added_s_p95'] or 0:.2f} s scripts {s[ph]['script_served_per_s']:.0f}/s"
                for ph in ("before", "surge", "workshop")) + f" throttled={info['throttled']} dropped={info['dropped']} left={sum(info['left'].values())}",
                flush=True)
    finally:
        Aa.lab.cleanup()
    (OUT / f"e4_admission_s{a.seed}.json").write_text(json.dumps(dict(
        seed=a.seed, step_s=STEP_S, surge_t=SURGE_T, workshop_t=WORKSHOP_T, pool=POOL, n_llm=N_LLM,
        n_scripts=N_SCRIPTS, workshop=WORKSHOP, people=people, svc0=svc0, arms=res), indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("run")
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--arms", type=lambda x: x.split(","))
    a = p.parse_args()
    {"run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
