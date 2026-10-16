#!/bin/bash
cd "${WORK:?set WORK to the run directory}"
until [ $(cat lane1.log lane2.log lane3.log lane4.log 2>/dev/null | grep -c LANEDONE) -ge 4 ]; do sleep 60; done
echo "PHASE2 START $(date -u +%T)" >> phase2.log
bash phase2.sh >> phase2.log 2>&1
echo "PHASE2 DONE $(date -u +%T)" >> phase2.log
