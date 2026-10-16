#!/bin/bash
# Saturation tests run alone on the main copy after the E1/E2 lanes finish.
cd "${WORK:?set WORK to the run directory that holds a copy of this folder as p3/}/p3"
PY=${PY:-python}
for s in $(seq 1 30); do
  echo "== e4 admission s$s $(date -u +%T)"
  $PY -m gym.aurora_admission run --seed $s
done
for s in $(seq 4 30); do
  echo "== e2c burst s$s $(date -u +%T)"
  $PY -m gym.aurora_national burst --agents 400 --seed $s
  $PY -m gym.aurora_national burst --agents 400 --seed $s --arms machine_limit
done
