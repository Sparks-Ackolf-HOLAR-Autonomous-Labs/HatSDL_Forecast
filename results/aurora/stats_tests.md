# Paired tests over seeds

Two-sided Wilcoxon signed-rank test on values paired by seed; Holm correction over all rows; 95 % percentile-bootstrap interval of the median paired difference (a - b), 10,000 resamples.

| Quantity | a | b | n | median a | median b | median diff [95 % CI] | seeds a < b | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| E1 95th pct over the day (ms) | plan-aware | history | 30 | 1.28 | 2.06 | -0.689 [-0.774, -0.512] | 30 | 4.5e-08 |
| E1 time to ready, review (s) | plan-aware | history | 30 | 0.272 | 10.5 | -10.3 [-12.8, -9.99] | 30 | 4.5e-08 |
| E1 time to ready, stacking (s) | plan-aware | history | 30 | 0.143 | 10.8 | -10.6 [-12.4, -10.4] | 30 | 4.5e-08 |
| E1 slow calls first 15 s, review | plan-aware | history | 30 | 22 | 18 | 0.5 [-5, 12] | 14 | 1 |
| E1 slow calls first 15 s, stacking | plan-aware | history | 30 | 3 | 13 | -10 [-10.5, -6.5] | 30 | 2.6e-05 |
| E1 95th pct over the day (ms) | plan-aware | production | 30 | 1.28 | 9.5 | -8.46 [-11.8, -7.48] | 30 | 4.5e-08 |
| E2 actions over target, today: development staff (%) | plan-aware | history | 30 | 0 | 10.1 | -9.76 [-12.1, -7.69] | 30 | 2.6e-05 |
| E2 actions over target, today: development staff (%) | plan-aware | production | 30 | 0 | 0 | 0 [0, 0] | 3 | 1 |
| E2 actions over target, beta (18 mo): pilot users (%) | plan-aware | history | 30 | 0 | 6.1 | -5.56 [-7.51, -4.51] | 30 | 4.5e-08 |
| E2 actions over target, beta (18 mo): pilot users (%) | plan-aware | production | 30 | 0 | 0 | 0 [0, 0] | 4 | 1 |
| E2 actions over target, user service (24 mo): workshop (%) | plan-aware | history | 30 | 0 | 6.07 | -5.74 [-6.73, -4.74] | 30 | 4.5e-08 |
| E2 actions over target, user service (24 mo): workshop (%) | plan-aware | production | 30 | 0 | 0 | 0 [0, 0] | 5 | 1 |
| E2 actions over target, year 4: 20 % of US groups (%) | plan-aware | history | 30 | 0 | 0 | 0 [0, 0] | 5 | 1 |
| E2 actions over target, year 4: 20 % of US groups (%) | plan-aware | production | 30 | 0 | 0 | 0 [0, 0] | 7 | 1 |
| E4 people over target, surge (%) | self-driving | reactive | 30 | 0 | 0.148 | -0.148 [-0.159, 0] | 16 | 0.0042 |
| E4 people over target, surge (%) | self-driving | static | 30 | 0 | 0 | 0 [0, 0] | 6 | 0.22 |
| E4 people over target, workshop (%) | self-driving | reactive | 30 | 0 | 0.0531 | -0.0531 [-0.0807, 0] | 18 | 0.0022 |
| E4 people over target, workshop (%) | self-driving | static | 30 | 0 | 0 | 0 [0, 0] | 7 | 0.65 |
| E4 time added to agent decision, surge (s) | self-driving | reactive | 30 | 0.109 | 0.133 | -0.0294 [-0.0415, -0.0222] | 29 | 1.1e-06 |
| E4 time added to agent decision, surge (s) | self-driving | static | 30 | 0.109 | 0.123 | -0.0123 [-0.0282, -0.00618] | 22 | 0.011 |
| E4 time added to agent decision, workshop (s) | self-driving | reactive | 30 | 0.0813 | 0.0992 | -0.0128 [-0.0265, -0.00875] | 26 | 2.6e-05 |
| E4 time added to agent decision, workshop (s) | self-driving | static | 30 | 0.0813 | 0.0961 | -0.0226 [-0.0258, -0.0172] | 27 | 3.9e-05 |
| E4 script requests within 1 s, surge (per s) | self-driving | reactive | 30 | 17.7 | 9.5 | 9.73 [5.9, 12] | 3 | 6.6e-06 |
| E4 script requests within 1 s, surge (per s) | self-driving | static | 30 | 17.7 | 2.34 | 15.3 [13, 17.6] | 0 | 2.6e-05 |

## Pooling check: seeds 1-3 (run alone) against seeds 4-30 (parallel lanes), Mann-Whitney U

| Experiment | Arm | n alone | n lanes | median alone | median lanes | p |
|---|---|---|---|---|---|---|
| E1 | history | 3 | 27 | 1.47 | 2.22 | 0.041 |
| E1 | plan | 3 | 27 | 1.04 | 1.28 | 0.2 |
| E1 | production | 3 | 27 | 9.43 | 12.4 | 0.43 |
| E2 (stage 1) | history | 3 | 27 | 9.76 | 10.3 | 0.97 |
| E2 (stage 1) | plan | 3 | 27 | 0 | 0 | 0.31 |
| E2 (stage 1) | production | 3 | 27 | 0 | 0 | 0.35 |
