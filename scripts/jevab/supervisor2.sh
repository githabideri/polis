#!/bin/bash
# jevab (the CPU batch box, ) supervisor: Decider 2B then SemIf 4B, serial, resumable.
# Weights live on the host's shared model store, mounted at /models/jevab
# (symlinked into /var/jevab/weights/). Completion markers are touched by the
# host-side download; results land in /var/jevab/results/ and get pulled back
# to the polis repo data/ by the operator.
set -u
cd /var/jevab
mkdir -p results
log(){ echo "[$(date)] $1" >> results/sup2.log; }

VDEC=/var/jevab/vdec/bin/python
VSEM=/var/jevab/vsem/bin/python
SETS="corpus/data/*.json"

run(){
  local m=$1 py=$2 pypath=$3
  log "run $m"
  PYTHONPATH="$pypath" "$py" ab-runner.py --model "$m" --sets "$SETS" --out "results/$m.json" > "results/$m-run.log" 2>&1
  log "run $m rc=$?"
}

pass(){
  # wait for the venv build (setup-venvs2.sh touches setup2-done when finished)
  if [ ! -f setup2-done ]; then
    log "waiting for setup2-done"
    return 0
  fi
  # decider 2B (Qwen3.5-2B-Base, pure-torch reference gated-delta-net on CPU)
  if [ -f /models/jevab/decider-2b.done ] && [ ! -f results/decider.json ]; then
    run decider "$VDEC" /var/jevab/weights/decider-2b
  fi
  # semif 4B (frozen Qwen3.5-4B, logit readout)
  if [ -f /models/jevab/qwen3.5-4b.done ] && [ ! -f results/semif.json ]; then
    run semif "$VSEM" /var/jevab/src/SemIf/src
  fi
}

log "=== supervisor2 pass start ==="
pass
log "=== pass done, idling (recheck in 30m) ==="
while true; do
  sleep 1800
  log "idle recheck"
  pass
done
