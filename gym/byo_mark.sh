#!/bin/bash
# E3b: decision marks for a bring-your-own-LLM agent session (here: Claude driving the REST API by curl).
# usage: byo_mark.sh <case> <task> start|end [answer]   -> one JSON line with a wall-clock timestamp
f=${BYO_MARKS:-$(dirname "$0")/../results/aurora_agents/e3b_claude_marks.jsonl}
python3 -c 'import json,sys,time; print(json.dumps({"t": float(sys.argv[1]), "case": sys.argv[2], "task": sys.argv[3], "event": sys.argv[4], "answer": sys.argv[5][:600]}))' \
  "$(date +%s.%N)" "$1" "$2" "$3" "${4:-}" >> "$f"
