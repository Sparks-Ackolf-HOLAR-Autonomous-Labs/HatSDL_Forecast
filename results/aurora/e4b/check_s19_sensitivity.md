# E4b sensitivity check: seed 19 replaced by its rerun (9 Oct 2026, 03:00 UTC, DGX idle). Not the reported result; the reported 30 seeds are in summary.md.

Each seed draws an unannounced burst of research users (log-uniform 100-2,400) and a script surge (log-uniform 25-1,200), the same for every arm of the seed. Values cover the surge and workshop phases together. Mean [min-max] over seeds.

| Arm | people over target (%) | research users over target (%) | seeds with people over 1 % in a phase | added to agent decision, p95 (s) | scripts answered within 1 s (per s) | scripts still queued at end |
|---|---|---|---|---|---|---|
| fixed split 5:1 | 0.6 [0.0-12.7] | 0.5 [0.0-12.2] | 3/30 | 0.18 [0.10-0.73] | 7.3 [0.2-23.5] | 4375 [0-26076] |
| fixed split 4:2 (E4) | 6.9 [0.0-93.2] | 6.6 [0.0-92.9] | 7/30 | 0.63 [0.11-8.26] | 15.3 [0.7-49.2] | 2906 [0-22213] |
| fixed split 3:3 | 15.8 [0.1-98.2] | 14.9 [0.0-98.1] | 16/30 | 2.41 [0.12-27.82] | 28.0 [1.2-92.2] | 2025 [0-18570] |
| reactive (history) | 2.4 [0.0-32.8] | 2.0 [0.0-34.2] | 10/30 | 0.33 [0.13-1.38] | 16.2 [0.4-56.1] | 0 [0-0] |
| self-driving (plan + forecast) | 0.0 [0.0-0.3] | 0.0 [0.0-0.0] | 0/30 | 0.14 [0.09-0.32] | 12.8 [1.9-48.6] | 0 [0-0] |

## Best fixed split chosen with hindsight, per seed

Fewest people's actions over target, ties broken by scripts answered within 1 s.

| Fixed split | seeds where it was best |
|---|---|
| fixed split 5:1 | 17 |
| fixed split 4:2 (E4) | 13 |
| fixed split 3:3 | 0 |

Self-driving vs the hindsight-best fixed split: people over target 0.03 % vs 0.58 %; scripts within 1 s 12.8 vs 13.8 per s.

## Paired tests (Wilcoxon signed-rank by seed, Holm-corrected over these comparisons)

| Measure | Self-driving vs | median diff [95 % CI] | seeds where self-driving is lower | p (Holm) |
|---|---|---|---|---|
| people over target (%) | fixed split 5:1 | -0.0145 [-0.0237, 0] | 16/30 (ties 13) | 0.0037 |
| added to agent decision (s) | fixed split 5:1 | -0.0162 [-0.0209, -0.00829] | 23/30 (ties 0) | 0.0037 |
| scripts within 1 s (per s) | fixed split 5:1 | 2.39 [0.122, 3.08] | 10/30 (ties 0) | 0.015 |
| people over target (%) | fixed split 4:2 (E4) | -0.0572 [-0.115, -0.0275] | 24/30 (ties 5) | 0.00023 |
| added to agent decision (s) | fixed split 4:2 (E4) | -0.0363 [-0.058, -0.0238] | 28/30 (ties 0) | 2e-06 |
| scripts within 1 s (per s) | fixed split 4:2 (E4) | -0.0167 [-1.01, 1.16] | 19/30 (ties 0) | 1 |
| people over target (%) | fixed split 3:3 | -1.08 [-5.72, -0.255] | 30/30 (ties 0) | 2.6e-08 |
| added to agent decision (s) | fixed split 3:3 | -0.19 [-0.325, -0.0762] | 30/30 (ties 0) | 2.6e-08 |
| scripts within 1 s (per s) | fixed split 3:3 | -1.01 [-9.26, -0.0167] | 24/30 (ties 0) | 0.0064 |
| people over target (%) | reactive (history) | -0.565 [-0.907, -0.231] | 30/30 (ties 0) | 2.6e-08 |
| added to agent decision (s) | reactive (history) | -0.109 [-0.161, -0.0665] | 30/30 (ties 0) | 2.6e-08 |
| scripts within 1 s (per s) | reactive (history) | 0.611 [-2.4, 2.86] | 14/30 (ties 0) | 1 |
| people over target (%) | hindsight-best fixed | -0.0164 [-0.0275, 0] | 18/30 (ties 10) | 0.0041 |
| scripts within 1 s (per s) | hindsight-best fixed | -0.0111 [-0.0278, 2.6] | 16/30 (ties 0) | 1 |

## Per seed

| seed | research burst | script surge | fixed split 5:1: people % / scripts 1 s | fixed split 4:2 (E4): people % / scripts 1 s | fixed split 3:3: people % / scripts 1 s | reactive (history): people % / scripts 1 s | self-driving (plan + forecast): people % / scripts 1 s |
|---|---|---|---|---|---|---|---|
| 1 | 310 | 609 | 0.0 / 0 | 0.0 / 1 | 0.1 / 1 | 0.1 / 1 | 0.0 / 3 |
| 2 | 345 | 38 | 0.0 / 19 | 0.1 / 19 | 0.5 / 19 | 0.4 / 15 | 0.0 / 19 |
| 3 | 1605 | 25 | 12.7 / 13 | 93.2 / 13 | 98.2 / 13 | 32.8 / 10 | 0.3 / 3 |
| 4 | 688 | 298 | 0.0 / 0 | 0.9 / 1 | 9.6 / 4 | 0.8 / 6 | 0.0 / 4 |
| 5 | 1271 | 196 | 2.8 / 1 | 85.3 / 3 | 96.0 / 92 | 10.7 / 4 | 0.0 / 2 |
| 6 | 213 | 48 | 0.0 / 23 | 0.1 / 23 | 0.3 / 23 | 0.2 / 18 | 0.0 / 23 |
| 7 | 226 | 76 | 0.0 / 4 | 0.0 / 38 | 0.1 / 38 | 0.1 / 31 | 0.0 / 22 |
| 8 | 158 | 150 | 0.0 / 1 | 0.0 / 4 | 0.1 / 76 | 0.1 / 56 | 0.0 / 7 |
| 9 | 275 | 95 | 0.0 / 1 | 0.0 / 49 | 0.1 / 49 | 0.1 / 43 | 0.0 / 49 |
| 10 | 576 | 73 | 0.0 / 2 | 0.2 / 37 | 9.4 / 37 | 1.3 / 25 | 0.0 / 5 |
| 11 | 160 | 177 | 0.0 / 0 | 0.0 / 1 | 0.2 / 74 | 0.0 / 19 | 0.0 / 14 |
| 12 | 425 | 479 | 0.0 / 0 | 0.1 / 1 | 1.8 / 2 | 0.3 / 1 | 0.0 / 2 |
| 13 | 309 | 38 | 0.0 / 20 | 0.1 / 20 | 1.0 / 20 | 0.0 / 16 | 0.0 / 20 |
| 14 | 380 | 213 | 0.0 / 1 | 0.0 / 2 | 0.1 / 9 | 0.3 / 12 | 0.0 / 5 |
| 15 | 151 | 59 | 0.0 / 14 | 0.0 / 30 | 0.1 / 30 | 0.2 / 24 | 0.0 / 30 |
| 16 | 425 | 32 | 0.0 / 15 | 0.1 / 15 | 0.1 / 15 | 0.7 / 12 | 0.0 / 15 |
| 17 | 723 | 228 | 0.0 / 0 | 0.1 / 1 | 23.6 / 2 | 6.3 / 4 | 0.0 / 3 |
| 18 | 531 | 58 | 0.1 / 5 | 0.1 / 29 | 3.2 / 29 | 0.5 / 21 | 0.0 / 5 |
| 19 | 482 | 34 | 0.0 / 17 | 0.0 / 17 | 1.2 / 17 | 0.7 / 10 | 0.0 / 17 |
| 20 | 1081 | 34 | 0.1 / 17 | 4.8 / 17 | 93.6 / 17 | 5.9 / 12 | 0.0 / 14 |
| 21 | 624 | 493 | 0.0 / 1 | 0.1 / 1 | 2.0 / 2 | 0.9 / 2 | 0.0 / 3 |
| 22 | 1009 | 147 | 0.4 / 1 | 18.7 / 6 | 90.6 / 72 | 3.3 / 5 | 0.0 / 4 |
| 23 | 733 | 47 | 0.0 / 23 | 1.1 / 23 | 7.1 / 23 | 3.1 / 17 | 0.0 / 15 |
| 24 | 163 | 27 | 0.1 / 13 | 0.0 / 13 | 0.1 / 13 | 0.7 / 10 | 0.0 / 13 |
| 25 | 443 | 47 | 0.0 / 22 | 0.0 / 23 | 0.6 / 23 | 0.3 / 18 | 0.0 / 21 |
| 26 | 599 | 658 | 0.0 / 0 | 0.4 / 1 | 3.3 / 1 | 0.9 / 1 | 0.0 / 2 |
| 27 | 200 | 292 | 0.9 / 0 | 1.6 / 1 | 18.3 / 2 | 1.1 / 0 | 0.2 / 3 |
| 28 | 280 | 58 | 0.0 / 4 | 0.0 / 29 | 0.3 / 29 | 0.2 / 22 | 0.0 / 27 |
| 29 | 178 | 130 | 0.0 / 1 | 0.0 / 1 | 0.3 / 65 | 0.1 / 53 | 0.0 / 28 |
| 30 | 670 | 82 | 0.1 / 2 | 0.1 / 42 | 13.3 / 42 | 1.1 / 15 | 0.0 / 4 |
