# How the 30 seeds of E1, E2, E2c and E4 were run

Seeds 1-3 of E1 and E2 and seeds 1-3 of the E2c surge were run first, one at a
time. Seeds 4-30 of E1 and E2, and all 30 seeds of E4, were run with the scripts
in this folder (7-8 Oct 2026) from a run directory `$WORK` that holds a copy of
this folder as `p3/`.

| Stage | What | Database | Seeds | Script |
|---|---|---|---|---|
| lanes 1-2 | E1 (lab events; production, history, plan tuners) | own copies `sddb_aurora_l1`, `_l2` | 4-17, 18-30 | `lane.sh` |
| lanes 3-4 | E2 (seven user modes, four growth stages) | own copies `sddb_aurora_l3`, `_l4` | 4-17, 18-30 | `lane.sh` |
| phase 2 | E4 admission control, four arms | `sddb_aurora`, alone | 1-30 | `phase2.sh` |
| phase 2 | E2c unannounced surge of 400 API clients, three arms | `sddb_aurora`, alone | 4-30 | `phase2.sh` |

- **Why lanes.** Serially the E1 and E2 seeds take about 14 h. Each lane has
  its own copy of the AURORA database, so one lane's tuner never sees another
  lane's indexes. The four lanes used about 5 of the DGX Spark's 20 cores;
  seeds 1-3 ran alone, so `gym/stats_tests.py` compares seeds 1-3 with seeds
  4-30 (Mann-Whitney U test) before pooling them.
- **Why phase 2 runs alone.** E4 and the E2c surge measure what happens when
  the 6 connections saturate, so another load on the machine would change the
  result. `chain.sh` starts them after all four lanes write `LANEDONE`.
- **E2b capacity** has one seed: a ramp is a saturation test too, and it was
  not repeated.

Example: `WORK=/scratch/p3 bash lane.sh 1 aurora_gym e1a 4 17`; `chain.sh`
starts `phase2.sh` when all four lane logs end with `LANEDONE`.

All stages finished without error (lanes in 17:49-18:25 UTC on 7 Oct, phase 2
at 01:49 UTC on 8 Oct). Tables: `../e1a_summary.md`, `../e2_summary.md`,
`../e2c_summary.md`, `../e4_summary.md`. The per-run files of E1 seeds 4-30
(516 MB) are not kept with the code; the per-run statistics and per-seed
latency curves of all 30 E1 seeds are in `../e1a_run_stats.json` and
`../e1a_curves.json`. Seeds 1-3 of E1 and all E2, E2c and E4 run files are in
`../`.
