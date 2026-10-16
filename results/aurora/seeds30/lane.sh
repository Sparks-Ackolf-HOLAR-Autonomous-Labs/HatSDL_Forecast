#!/bin/bash
# usage: lane.sh <lane> <module> <prefix> <first> <last>
L=$1; MOD=$2; PFX=$3; A=$4; B=$5
cd "${WORK:?set WORK to the run directory that holds a copy of this folder as p3/}/p3"
export SDDB_AURORA_DB=sddb_aurora_l$L
PY=${PY:-python}
for s in $(seq $A $B); do for arm in production history plan; do
  echo "== lane$L $MOD $arm s$s $(date -u +%T)" >> ../lane$L.log
  $PY -m gym.$MOD run --arm $arm --seed $s >> ../lane$L.log 2>&1
  gzip -9f results/aurora/${PFX}_${arm}_s${s}.json
done; done
echo LANEDONE $(date -u +%T) >> ../lane$L.log
