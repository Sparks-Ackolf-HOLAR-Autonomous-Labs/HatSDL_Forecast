# E2 on AURORA: from development staff to a community service

Seeds per arm: production 30, history 30, plan 30. Stages of 60 s, each announced 15 s ahead; 6 pooled connections serve all users.

## Share of user actions over their latency target, per stage (%; mean over seeds)

| Stage | production index set (fixed) | history-based tuner | plan-aware tuner (allocation calendar) |
|---|---|---|---|
| today: development staff (6 users, writes x1) | 0.7 ± 1.5 | 13.0 ± 8.5 | 0.7 ± 1.3 |
| beta (18 mo): pilot users (18 users, writes x1.5) | 0.6 ± 1.0 | 7.0 ± 3.5 | 0.6 ± 1.2 |
| user service (24 mo): workshop (70 users, writes x2) | 0.8 ± 1.4 | 8.8 ± 6.7 | 1.1 ± 1.5 |
| year 4: 20 % of US groups (123 users, writes x2) | 1.0 ± 1.7 | 1.2 ± 1.8 | 1.4 ± 1.8 |

## First 15 s of each stage: actions over target (count; mean over seeds)

| Stage | production index set (fixed) | history-based tuner | plan-aware tuner (allocation calendar) |
|---|---|---|---|
| today: development staff | 0 | 3 | 0 |
| beta (18 mo): pilot users | 0 | 6 | 0 |
| user service (24 mo): workshop | 1 | 29 | 1 |
| year 4: 20 % of US groups | 2 | 2 | 3 |

## 95th-percentile latency per user mode, stage 'year 4: 20 % of US groups' (ms; target in brackets)

| User mode | production index set (fixed) | history-based tuner | plan-aware tuner (allocation calendar) |
|---|---|---|---|
| development staff (100) | 59.8 | 42.7 | 24.6 |
| first-time users (300) | 181.8 | 201.9 | 199.8 |
| research users (500) | 187.4 | 201.3 | 209.9 |
| power users (3000) | 492.1 | 536.7 | 546.4 |
| innovation / prototyping (500) | 14.9 | 23.7 | 22.7 |
| industry users (300) | 209.6 | 219.3 | 228.1 |
| education users (300) | 19.4 | 21.5 | 22.9 |
| safety-critical / EHS (1000) | nan | nan | nan |

## 95th-percentile latency per user mode over the whole run (ms)

| User mode | production index set (fixed) | history-based tuner | plan-aware tuner (allocation calendar) |
|---|---|---|---|
| development staff | 55.6 | 450.6 | 17.3 |
| first-time users | 179.5 | 396.3 | 203.0 |
| research users | 181.9 | 331.6 | 206.7 |
| power users | 478.8 | 666.7 | 534.8 |
| innovation / prototyping | 11.3 | 245.0 | 13.7 |
| industry users | 210.5 | 1399.3 | 235.1 |
| education users | 12.7 | 1428.3 | 17.5 |
| safety-critical / EHS | 4.8 | 948.3 | 10.0 |

## Writes (one tile plus its flakes) and index space

| | production index set (fixed) | history-based tuner | plan-aware tuner (allocation calendar) |
|---|---|---|---|
| write p95 (ms) | 24.0 | 23.8 | 24.2 |
| tiles written per run | 858 | 858 | 857 |
| crystallite secondary indexes at end (MB) | 869 | 617 | 617 |
| user actions served | 1171 | 1171 | 1171 |

## Index actions (first seed)

- production index set (fixed): 0 builds, 0 drops; final set: crystallite_area_num_idx, crystallite_chip_id_idx, crystallite_classification_ai_idx, crystallite_image_id_idx, crystallite_image_path_idx, crystallite_image_process_info_id_idx, crystallite_reviewed_checked, crystallite_reviewed_idx, crystallite_reviewed_true_created_idx, crystallite_unreviewed_created_idx, crystallite_user_id_idx, idx_crystallite_bulk_crystal_id, idx_crystallite_removed_at
- history-based tuner: 11 builds, 15 drops; final set: crystallite_chip_id_idx, crystallite_classification_ai_idx, crystallite_image_path_idx, crystallite_image_process_info_id_idx, crystallite_reviewed_true_created_idx, crystallite_user_id_idx, idx_crystallite_removed_at, ix_archive, ix_review_queue
  - t=23 s drop crystallite_area_num_idx (history: decayed observed calls)
  - t=23 s drop crystallite_chip_id_idx (history: decayed observed calls)
  - t=23 s drop crystallite_classification_ai_idx (history: decayed observed calls)
  - t=23 s drop crystallite_image_id_idx (history: decayed observed calls)
  - t=23 s drop crystallite_image_process_info_id_idx (history: decayed observed calls)
  - t=23 s drop crystallite_reviewed_checked (history: decayed observed calls)
  - t=23 s drop crystallite_reviewed_idx (history: decayed observed calls)
  - t=23 s drop crystallite_reviewed_true_created_idx (history: decayed observed calls)
  - t=23 s drop crystallite_unreviewed_created_idx (history: decayed observed calls)
  - t=23 s drop crystallite_user_id_idx (history: decayed observed calls)
  - t=23 s drop idx_crystallite_bulk_crystal_id (history: decayed observed calls)
  - t=23 s drop idx_crystallite_removed_at (history: decayed observed calls)
  - t=23 s build ix_archive (history: decayed observed calls)
  - t=31 s build crystallite_classification_ai_idx (history: decayed observed calls)
  - t=34 s build crystallite_image_process_info_id_idx (history: decayed observed calls)
  - t=37 s build ix_review_queue (history: decayed observed calls)
  - t=63 s build ix_monolayer_area (history: decayed observed calls)
  - t=98 s build crystallite_chip_id_idx (history: decayed observed calls)
  - t=130 s build idx_crystallite_removed_at (history: decayed observed calls)
  - t=174 s drop ix_monolayer_area (history: decayed observed calls)
  - t=174 s build crystallite_reviewed_true_created_idx (history: decayed observed calls)
  - t=175 s build crystallite_user_id_idx (history: decayed observed calls)
  - t=221 s build ix_monolayer_area (history: decayed observed calls)
  - t=264 s drop ix_monolayer_area (history: decayed observed calls)
  - t=272 s build ix_monolayer_area (history: decayed observed calls)
  - t=296 s drop ix_monolayer_area (history: decayed observed calls)
- plan-aware tuner (allocation calendar): 7 builds, 10 drops; final set: crystallite_chip_id_idx, crystallite_classification_ai_idx, crystallite_image_path_idx, crystallite_image_process_info_id_idx, crystallite_reviewed_true_created_idx, crystallite_user_id_idx, idx_crystallite_removed_at, ix_archive, ix_monolayer_area, ix_review_queue
  - t=0 s drop crystallite_area_num_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_chip_id_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_image_id_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_reviewed_checked (plan: before 'today: development staff')
  - t=0 s drop crystallite_reviewed_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_reviewed_true_created_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_unreviewed_created_idx (plan: before 'today: development staff')
  - t=0 s drop crystallite_user_id_idx (plan: before 'today: development staff')
  - t=0 s drop idx_crystallite_bulk_crystal_id (plan: before 'today: development staff')
  - t=0 s drop idx_crystallite_removed_at (plan: before 'today: development staff')
  - t=0 s build ix_archive (plan: before 'today: development staff')
  - t=7 s build ix_monolayer_area (plan: before 'today: development staff')
  - t=8 s build ix_review_queue (plan: before 'today: development staff')
  - t=75 s build crystallite_chip_id_idx (plan: before 'beta (18 mo): pilot users')
  - t=79 s build idx_crystallite_removed_at (plan: before 'beta (18 mo): pilot users')
  - t=150 s build crystallite_reviewed_true_created_idx (plan: before 'user service (24 mo): workshop')
  - t=151 s build crystallite_user_id_idx (plan: before 'user service (24 mo): workshop')
