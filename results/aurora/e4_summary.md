# E4 admission control: 30 seeds (mean [min-max] over seeds)

## People: actions over target (%)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 0.0 [0.0-0.0] | 78.0 [61.6-98.0] | 99.9 [98.9-100.0] |
| hand-set split | 0.0 [0.0-0.6] | 0.1 [0.0-0.6] | 0.1 [0.0-3.7] |
| reactive (history) | 0.0 [0.0-0.4] | 0.2 [0.0-2.5] | 0.1 [0.0-0.4] |
| self-driving (plan + forecast) | 0.0 [0.0-0.2] | 0.0 [0.0-0.2] | 0.0 [0.0-0.2] |

## Workshop students over target (%)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | n/a | n/a | 100.0 [100.0-100.0] |
| hand-set split | n/a | n/a | 0.2 [0.0-4.4] |
| reactive (history) | n/a | n/a | 0.1 [0.0-0.4] |
| self-driving (plan + forecast) | n/a | n/a | 0.0 [0.0-0.0] |

## LLM tool call, 95th percentile (ms)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 76 [60-97] | 4478 [2539-13450] | 9264 [5509-25361] |
| hand-set split | 79 [58-120] | 96 [76-153] | 98 [72-327] |
| reactive (history) | 84 [67-126] | 108 [87-147] | 103 [76-134] |
| self-driving (plan + forecast) | 78 [65-111] | 95 [73-120] | 87 [72-130] |

## LLM decision time added by the database, 95th percentile (s)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 10.24 [4.76-18.09] | 7.48 [4.46-21.78] | 8.91 [5.37-24.35] |
| hand-set split | 0.13 [0.10-0.24] | 0.14 [0.10-0.49] | 0.11 [0.08-0.27] |
| reactive (history) | 0.14 [0.11-0.20] | 0.14 [0.10-0.24] | 0.10 [0.08-0.13] |
| self-driving (plan + forecast) | 0.13 [0.10-0.19] | 0.11 [0.08-0.23] | 0.08 [0.06-0.12] |

## LLM decision, median (s)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 32.9 [29.5-38.9] | 29.7 [23.6-35.4] | 18.2 [15.1-33.6] |
| hand-set split | 32.7 [29.5-37.7] | 32.0 [28.8-37.7] | 19.8 [13.2-21.0] |
| reactive (history) | 32.7 [29.5-37.7] | 29.2 [28.7-29.6] | 10.4 [9.9-12.4] |
| self-driving (plan + forecast) | 32.7 [29.5-37.7] | 27.3 [21.0-29.5] | 10.0 [9.9-10.1] |

## Database share of LLM decisions (%)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 4.39 [1.96-10.94] | 11.97 [6.97-27.57] | 30.02 [21.89-53.38] |
| hand-set split | 0.07 [0.06-0.17] | 0.08 [0.06-0.26] | 0.09 [0.07-0.25] |
| reactive (history) | 0.08 [0.06-0.14] | 0.10 [0.07-0.19] | 0.11 [0.09-0.20] |
| self-driving (plan + forecast) | 0.07 [0.06-0.16] | 0.08 [0.06-0.26] | 0.10 [0.07-0.20] |

## Scripts served per s

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 0 [0-0] | 200 [196-207] | 200 [196-203] |
| hand-set split | 0 [0-0] | 197 [137-207] | 9 [0-20] |
| reactive (history) | 0 [0-0] | 107 [41-122] | 95 [39-110] |
| self-driving (plan + forecast) | 0 [0-0] | 116 [82-143] | 68 [42-92] |

## Script request, 95th percentile (ms)

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | n/a | 4493 [2543-13462] | 9306 [5528-25496] |
| hand-set split | n/a | 73738 [67738-89897] | 77425 [74779-79576] |
| reactive (history) | n/a | 19492 [18463-28917] | 22122 [20608-30986] |
| self-driving (plan + forecast) | n/a | 16123 [9605-16653] | 16714 [16275-17311] |

## Script requests answered within 1 s, per s

| Arm | before | surge | workshop |
|---|---|---|---|
| shared pool | 0 [0-0] | 55 [4-138] | 0 [0-0] |
| hand-set split | 0 [0-0] | 2 [2-4] | 0 [0-0] |
| reactive (history) | 0 [0-0] | 9 [1-17] | 0 [0-0] |
| self-driving (plan + forecast) | 0 [0-0] | 18 [10-28] | 2 [0-6] |

## Script requests turned away and left unserved (per run)

| Arm | 429 responses | dropped after 4 retries | still queued at the end |
|---|---|---|---|
| shared pool | 0 [0-0] | 0 [0-0] | 0 [0-0] |
| hand-set split | 0 [0-0] | 0 [0-0] | 9712 [8979-12611] |
| reactive (history) | 53392 [49103-73062] | 8950 [7837-14533] | 0 [0-0] |
| self-driving (plan + forecast) | 55995 [47203-65591] | 10009 [7734-12483] | 0 [0-0] |
