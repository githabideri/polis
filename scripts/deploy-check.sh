#!/bin/bash
# deploy-check.sh - advisory post-deploy gate for the polis game container.
#
# Run after `build.sh --deploy` + a game restart:
#
#     scripts/deploy-check.sh
#
# Env (all optional): HARNESS_PORT (8585), OIKISTES_PORT (8587).
#
# Checks (advisory - this script never fails a deploy):
#   1. exec bits on the repo scripts (the git index is the source of truth;
#      a mirror consumer's `git reset --hard` must reproduce a working CLI)
#   2. harness answering on its loopback port
#   3. oikistes service answering
#   4. Xvnc display age - a stale display process is an entity-render
#      risk (2026-10-07: days-old display held broken GL state that a
#      plain game restart could not clear)
#   5. render smoke: a cinematic capture of a live bot. The deployer
#      LOOKS AT THE PNG. Picture over log line: a deploy that cannot show
#      its bot is not a done deploy.
#
# Public-safe: localhost + port numbers only; no host names, no PII.

set -u
HARNESS_PORT="${HARNESS_PORT:-8585}"
OIKISTES_PORT="${OIKISTES_PORT:-8587}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="http://127.0.0.1:$HARNESS_PORT"

pass() { echo "PASS  $1"; }
warn() { echo "WARN  $1"; }
skip() { echo "SKIP  $1"; }

# 1. exec bits (repo copy - what a fresh checkout/reset produces)
if [ -f "$SCRIPT_DIR/polisctl.py" ]; then
    if [ -x "$SCRIPT_DIR/polisctl.py" ]; then
        pass "polisctl.py executable (repo copy)"
    else
        warn "polisctl.py NOT executable - fix the git index: git update-index --chmod=+x scripts/polisctl.py"
    fi
else
    skip "exec-bit check (polisctl.py not in this checkout)"
fi

# 2. harness
if curl -s -m 3 "$BASE/polis/status" >/dev/null 2>&1; then
    pass "harness answering on :$HARNESS_PORT"
else
    warn "harness NOT answering on :$HARNESS_PORT"
fi

# 3. oikistes
if curl -s -m 3 "http://127.0.0.1:$OIKISTES_PORT/" >/dev/null 2>&1; then
    pass "oikistes answering on :$OIKISTES_PORT"
else
    warn "oikistes NOT answering on :$OIKISTES_PORT"
fi

# 4. Xvnc display age
XVNC_PID="$(pgrep -f 'Xvnc' | head -1 || true)"
if [ -n "$XVNC_PID" ]; then
    AGE_H=$(( ( $(date +%s) - $(stat -c %Y /proc/$XVNC_PID) ) / 3600 ))
    if [ "$AGE_H" -gt 48 ]; then
        warn "Xvnc display is ${AGE_H}h old - if a render check looks wrong, restart the whole stack (xvnc -> novnc -> game) before trusting it"
    else
        pass "Xvnc display age ${AGE_H}h"
    fi
else
    warn "no Xvnc process found"
fi

# 5. render smoke (cinematic capture of the first live bot)
if command -v polisctl >/dev/null 2>&1; then
    GEO="$(curl -s -m 3 "$BASE/polis/bots" 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(3)
bots = (d.get("Data") or {}).get("bots") or []
if not bots:
    sys.exit(3)
x, y, z = bots[0]["pos"]
# vantage a few blocks out and up; target the bot at head height
print("%d %d %d %d %d %d" % (x + 4, y + 3, z + 4, x, y + 1, z))' 2>/dev/null)"
    if [ -n "$GEO" ]; then
        OUT="$(polisctl shotat deploy-check $GEO 2>&1 | head -1)"
        PNG="${OUT%% *}"
        if [ -f "$PNG" ]; then
            pass "render smoke: $PNG   <-- LOOK AT THIS PNG: is the bot in it?"
        else
            warn "render smoke: $OUT"
        fi
    else
        skip "render smoke (no bot in /polis/bots or harness unreachable)"
    fi
else
    skip "render smoke (polisctl not on PATH)"
fi
