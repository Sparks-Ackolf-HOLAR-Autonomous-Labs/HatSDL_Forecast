# E1 on AURORA: summary

Seeds per arm: production 30, history 30, plan 30. Phases of 45 s, each after an announced idle window of 15 s.

| Tuner | Median (ms) | 95th pct (ms) | 99th pct (ms) | Decisions > 50 ms (%) | Decisions | Crystallite secondary indexes at end (MB) |
|---|---|---|---|---|---|---|
| production index set (fixed) | 2.2 ± 0.6 | 11.5 ± 3.7 | 40.3 ± 20.3 | 0.6 ± 0.5 | 34696 | 869 |
| history-based tuner | 0.1 ± 0.0 | 2.2 ± 0.6 | 4.9 ± 2.2 | 0.0 ± 0.0 | 249218 | 130 |
| plan-aware tuner | 0.1 ± 0.0 | 1.4 ± 0.4 | 4.1 ± 2.0 | 0.0 ± 0.0 | 406600 | 88 |

## 95th-percentile decision latency per phase (ms; decisions completed in brackets)

| Phase | production index set (fixed) | history-based tuner | plan-aware tuner |
|---|---|---|---|
| chip scan and flake detection | 5.0 (10160) | 5.3 (10094) | 4.6 (10683) |
| review of the new chips | 13.8 (6707) | 4.3 (24319) | 3.6 (35985) |
| stacking planner | 274.9 (2659) | 0.6 (199472) | 0.4 (343538) |
| detection with web viewing | 5.0 (15170) | 5.0 (15333) | 4.6 (16393) |

## After a lab event: slow decisions of the new action in the first 15 s; time until it is first served in under 1 ms (mean over seeds)

| Phase | production index set (fixed) | history-based tuner | plan-aware tuner |
|---|---|---|---|
| review of the new chips | 1144 slow; never | 20 slow; 11.7 s | 26 slow; 0.3 s |
| stacking planner | 370 slow; 8.8 s | 12 slow; 11.8 s | 3 slow; 0.1 s |

## 95th-percentile latency per lab action (ms)

| Action | production index set (fixed) | history-based tuner | plan-aware tuner |
|---|---|---|---|
| scan | 5.4 | 5.9 | 5.1 |
| detect | 5.5 | 5.5 | 5.0 |
| review | 15.5 | 0.6 | 0.5 |
| plan | 297.4 | 0.7 | 0.4 |
| view | 1.0 | 0.8 | 0.7 |

## Index actions per run (first seed)

- production index set (fixed): 0 builds, 0 drops; final set: crystallite_area_num_idx, crystallite_chip_id_idx, crystallite_classification_ai_idx, crystallite_image_id_idx, crystallite_image_path_idx, crystallite_image_process_info_id_idx, crystallite_reviewed_checked, crystallite_reviewed_idx, crystallite_reviewed_true_created_idx, crystallite_unreviewed_created_idx, crystallite_user_id_idx, idx_crystallite_bulk_crystal_id, idx_crystallite_removed_at
- history-based tuner: 3 builds, 12 drops; final set: crystallite_classification_ai_idx, crystallite_image_path_idx, ix_monolayer_area, ix_review_queue
- plan-aware tuner: 3 builds, 15 drops; final set: crystallite_image_path_idx
