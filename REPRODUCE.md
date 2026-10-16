# Reproducing the results

Three levels, from quickest to fullest. Every command runs from the root of this folder.

| Level | What it rebuilds | Needs | Time |
|---|---|---|---|
| 1 | every figure | Python 3.10+, numpy, matplotlib | 1 min |
| 2 | every table and statistical test | level 1 + scipy | 2 min |
| 3 | the run files themselves | level 2 + PostgreSQL 16, a copy of AURORA's database; for E3 also a GPU model server | hours (below) |

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Level 1: figures

```bash
for f in paper_figures/regen_figs/fig_*.py; do python "$f"; done
```

Each script reads committed result files (README, Figures table) and writes into `paper_figures/figures/`.
Compare with the committed images, or check the files with `sha256sum -c FILES.sha256` before running.

## Level 2: tables and tests

```bash
python -m gym.analyze_aurora       # E1 tables      -> results/aurora/e1a_summary.md (from e1a_run_stats.json)
python -m gym.analyze_users        # E2, Table A3   -> results/aurora/e2_summary.md
python -m gym.analyze_capacity     # E2b, Table A4  -> results/aurora/e2b_summary.md
python -m gym.analyze_national     # E2c, Tables A5-A6 -> results/aurora/e2c_summary.md
python -m gym.analyze_agents       # E3, Table 2    -> results/aurora_agents/e3_summary.md
python -m gym.analyze_byo          # E3b, Table 2   -> results/aurora_agents/e3b_summary.md
python -m gym.analyze_multi results/aurora_multi   # facility-wide question, Table A7 -> results/aurora_multi/e3c_summary.md
python -m gym.analyze_admission    # E4, Table A8   -> results/aurora/e4_summary.md
python -m gym.stats_tests          # paired tests, Holm correction, bootstrap intervals (E1, E2, E4), Table A9 -> results/aurora/stats_tests.md
python -m gym.analyze_surge        # E4b, Tables A10-A11 -> results/aurora/e4b/summary.md, stats.json
```

The regenerated `.md` files match the committed ones line for line. The raw run files of E1 seeds 4-30
(516 MB, every decision of every run) are not in this folder. What the paper uses from them is: the per-run
statistics in `results/aurora/e1a_run_stats.json` (E1 tables and tests) and the per-seed latency curves in
`results/aurora/e1a_curves.json` (Fig. 2). With the raw files at hand, `python -m gym.e1_run_stats <raw folder>`
and `python -m gym.e1_curves <raw folder>` rebuild both; the raw files of seeds 1-3 are included and show the
format.

## Level 3: rerunning the experiments

**Database server.** All runs used PostgreSQL 16.10 on one 20-core aarch64 machine (NVIDIA DGX Spark, 121 GiB
unified memory) shared with other jobs:

```bash
export SDLDB_STACK=$HOME/sddb_stack
bash stack/postgres_setup.sh
```

**Data.** The experiments run on a copy of AURORA's production database (6.24 M flakes, 0.81 M microscope
tiles, 812 chips). The copy is not redistributed; it is made through the facility's read-only role and
requires the facility's agreement. With access (a tunnel to the server on local port `AURORA_TUNNEL_PORT`,
default 15433, and the role's password in `~/secrets/pcl_chatbot_ro_password`):

```bash
python -m gym.aurora_src profile     # contents and usage counters -> results/aurora/profile.json (Table 1)
python -m gym.aurora_src load        # copy into the local database sddb_aurora (3.7 GB)
```

**Experiments.** Arms are `production`, `history` and `plan` unless stated. A seed fixes every random draw
(arrivals, surges), so all arms of a seed see the same workload. Times are per seed on the machine above.

| Experiment | Commands | Seeds | Time per seed |
|---|---|---|---|
| E1, laboratory events | `python -m gym.aurora_gym setup`, `calibrate`, then `run --arm <arm> --seed <s>` | 30 | 13 min (3 arms) |
| E2, user modes and growth | `python -m gym.aurora_users write-profile`, `calibrate`, then `run --arm <arm> --seed <s>` | 30 | 16 min (3 arms) |
| E2b, capacity ramps | `python -m gym.aurora_capacity reads --arm production --pool 6`, `reads --arm plan --pool 6`, `reads --arm plan --pool 12`, `writes --arm production --pool 6`, `writes --arm plan --pool 6`; then `reads ... --ks <k list> --tag _refine` adds steps where a ramp starts to fail (the steps run are listed in each `e2b_*.json`) | 1 | 30 s per step |
| E2b, CPU split | `python gym/cpu_probe.py . python -m gym.aurora_capacity reads --arm plan --pool 6 --ks 1,4,8 --tag _cpuprobe` | 1 | 5 min |
| E2c, national demand | `python -m gym.aurora_national demand`; `run --pool 6`; `ramp --base W`; `ramp --base N4 --agents-only`; `burst --agents 400 --seed <s>` and `burst --agents 400 --seed <s> --arms machine_limit` | 1 (burst: 30) | 3 min per burst seed |
| E4, admission control | `python -m gym.aurora_admission run --seed <s>` | 30 | 12 min |
| E4b, surge of unknown size | `python -m gym.aurora_surge run --seed <s>` | 30 | 11 min |

`results/aurora/seeds30/` holds the scripts that ran seeds 4-30 of E1 and E2 in four parallel lanes, each on
its own copy of the database (`CREATE DATABASE sddb_aurora_l1 TEMPLATE sddb_aurora`, selected with
`SDDB_AURORA_DB`), and then E4 and the E2c bursts alone; `results/aurora/e4b/run_e4b.sh` ran E4b one seed at
a time. Set `WORK` to a directory holding a copy of this folder as `p3/`.

**Agents (E3, E3b and the facility-wide question).** These need a GPU model server. The runs used
Qwen3.5-9B on vLLM (`results/aurora_agents/serve.sh`, port 8720, 35 % of the GPU memory):

```bash
bash results/aurora_agents/serve.sh &                  # cold start measured from serve.times
python -m gym.agent_latency run --case A --reps 2      # specialist agent with the AURORA tools
python -m gym.agent_latency run --case A-V --reps 3    # same, with a tile image
python -m gym.agent_latency run --case B --reps 2      # generic agent: finds the skill, writes its own SQL
python -m gym.agent_latency concurrency --n 1,4,16
python -m gym.agent_latency network                    # round trips to hosted model gateways
python -m gym.rest_api serve --port 8730 --log results/aurora_agents/e3b_rest_log.jsonl &
python -m gym.rest_api bench --n 200
AURORA_REST=http://127.0.0.1:8730 python -m gym.agent_latency run --case A --reps 2 --tag _rest
AURORA_REST=http://127.0.0.1:8730 python -m gym.agent_latency run --case B --reps 2 --tag _rest
```

The hosted-model rows of E3b were produced by a hosted agent client (Claude Opus 5.5) working through the
same REST interface; `gym/byo_mark.sh` time-stamped the start and end of each decision
(`results/aurora_agents/e3b_claude_marks.jsonl`), and the interface log gives the database time.

The facility-wide question also needs the labelled simulated projection of stacking, device and transport
records and, for the literature agent, a key for the Asta literature service in the environment variable
`ASTA_x-api-key` (`gym/asta_mcp.py`):

```bash
python -m gym.aurora_next build && python -m gym.aurora_next summary
for arm in single_archive single_all team; do python -m gym.multi_agent run --arm $arm --cond today --seeds 1-10 --par 10; done
for arm in single_all team; do python -m gym.multi_agent run --arm $arm --cond projected --seeds 1-10 --par 10; done
python -m gym.multi_agent run --arm team --cond projected --db raw --seeds 1-10 --par 10
```

**What will differ.** Absolute latencies depend on the machine, the engine version and other load; the paired
comparisons between arms of a seed are what the paper tests. Model timings depend on the GPU, the model
server version and, for hosted models and literature calls, the network.
