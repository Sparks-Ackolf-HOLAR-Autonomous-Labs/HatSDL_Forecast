"""Sample CPU seconds of the PostgreSQL processes and of the load generator while a capacity step runs.

Usage: python gym/cpu_probe.py <workdir> <python> -m gym.aurora_capacity reads --arm plan --pool 6 --ks 1,4,8 --tag _cpuprobe
Writes cpu_probe_series.json in <workdir>: (seconds, cumulative postgres CPU s, cumulative generator CPU s)."""
import os, subprocess, sys, time, json
HZ = os.sysconf("SC_CLK_TCK")
def procs():
    out = {}
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        try:
            st = open(f"/proc/{p}/stat").read()
            comm = st[st.index("(")+1:st.rindex(")")]
            f = st[st.rindex(")")+2:].split()
            out[int(p)] = (comm, (int(f[11]) + int(f[12])) / HZ)
        except Exception: pass
    return out
gen = subprocess.Popen(sys.argv[2:], cwd=sys.argv[1])
seen = {}; t0 = time.time(); series = []
while gen.poll() is None:
    snap = procs()
    for pid, (comm, cpu) in snap.items():
        seen[pid] = (comm, cpu)
    pg = sum(c for pid, (n, c) in seen.items() if n == "postgres")
    me = seen.get(gen.pid, ("", 0))[1]
    series.append((round(time.time() - t0, 1), round(pg, 2), round(me, 2)))
    time.sleep(1.0)
json.dump(series, open(os.path.join(sys.argv[1], "cpu_probe_series.json"), "w"))
print("done", series[-1])
