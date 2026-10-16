| Agent | Decisions | Median (s) | Range (s) | Model turns | Model time per turn (s) | Database / HTTP, median (ms) | Database + HTTP share (%) |
|---|---|---|---|---|---|---|---|
| a: Qwen3.5-9B on DGX, tools in-process (E3) | 12 | 16.9 | 8.4-42.9 | 2 | 8.4 | 58 / 0.1 | 0.18 |
| a: Qwen3.5-9B on DGX, REST API | 12 | 17.3 | 8.2-47.2 | 2 | 8.6 | 89 / 2.0 | 0.29 |
| a: Claude Opus 5.5 (hosted), REST API | 6 | 2.8 | 2.5-3.2 | 2 | 1.3 | 145 / 2.0 | 5.19 |
| b: Qwen3.5-9B on DGX, skills + SQL in-process (E3) | 12 | 57.5 | 32.7-91.5 | 4 | 13.5 | 24 / 0.1 | 0.05 |
| b: Qwen3.5-9B on DGX, API guide + SQL over REST | 12 | 59.0 | 38.1-92.0 | 4 | 13.3 | 29 / 2.0 | 0.06 |
| b: Claude Opus 5.5 (hosted), API guide + SQL over REST | 6 | 4.9 | 4.0-7.6 | 4 | 1.2 | 135 / 5.3 | 2.20 |

| REST overhead (200 calls each) | In-process (ms) | Over HTTP (ms) | HTTP p95 (ms) |
|---|---|---|---|
| aurora_get_flake | 0.35 | 0.80 | 1.20 |
| aurora_chip_summary | 2.81 | 4.92 | 5.93 |
| aurora_stack_candidates | 12.31 | 16.23 | 19.29 |

| Round trip from the DGX (20 requests, no credentials) | Median (ms) | TLS done (ms) |
|---|---|---|
| Anthropic (api.anthropic.com) | 91.0 | 20.4 |
| OpenAI (api.openai.com) | 90.7 | 28.2 |
| AURORA REST API (loopback) | 1.4 | 0.0 |
