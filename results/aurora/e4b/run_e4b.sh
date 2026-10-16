#!/bin/bash
# E4b: 30 seeds, one at a time (a saturation test; parallel lanes slow each other and break the pairing).
cd "${WORK:?set WORK to the run directory that holds a copy of this folder as p3/}/p3"
PY=${PY:-python}
export SDDB_AURORA_DB=sddb_aurora_l1
for s in $(seq ${1:-1} ${2:-30}); do
  [ -f results/aurora/e4b_surge_s$s.json ] && continue
  echo "== e4b s$s $(date -u +%FT%T)"
  $PY -m gym.aurora_surge run --seed $s
done
echo "E4BDONE $(date -u +%FT%T)"
