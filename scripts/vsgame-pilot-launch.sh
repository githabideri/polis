#!/bin/bash
# vsgame-pilot-launch.sh - autonomous game start for unattended pilot runs.
#
# Vintage Story's in-game (singleplayer) server suspends ticking when the
# client sits on a full-screen screen at world entry (loading/intro). The
# server logs "Server ticking has been suspended" ~60-95s after start and
# stays suspended until the screen is dismissed. Escape is the game's own
# skip key. This script:
#   1. starts vsgame
#   2. polls the harness status for tick progress (timeMs)
#   3. sends Escape only while the tick is frozen (conditional, so an
#      early press can never navigate a menu)
#   4. reports when the tick is running again
#
# Usage: vsgame-pilot-launch.sh [--harness-port 8585] [--max-wait 300]
set -u
export DISPLAY=:1
PORT=8585
MAXWAIT=300
while [ $# -gt 0 ]; do
  case "$1" in
    --harness-port) PORT="$2"; shift 2;;
    --max-wait) MAXWAIT="$2"; shift 2;;
    *) shift;;
  esac
done

get_ms() {
  curl -s -m 5 "http://127.0.0.1:${PORT}/polis/status" 2>/dev/null \
    | grep -o 'timeMs": [0-9]*' | grep -o '[0-9]*' || true
}

systemctl start vsgame || { echo "vsgame failed to start"; exit 1; }

deadline=$(( $(date +%s) + MAXWAIT ))
frozen_since=0
escs=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  ms=$(get_ms)
  if [ -z "$ms" ]; then
    # harness not up yet (game still booting) - keep waiting
    sleep 10
    continue
  fi
  sleep 8
  ms2=$(get_ms)
  if [ -n "$ms2" ] && [ "$ms2" != "$ms" ]; then
    echo "OK: tick running (timeMs $ms -> $ms2) after $escs unblock(s)"
    exit 0
  fi
  # tick frozen
  if [ "$frozen_since" -eq 0 ]; then
    frozen_since=$(date +%s)
    echo "tick frozen at timeMs $ms - waiting before unblocking"
  fi
  # give the frozen state 20s to be a real stall, then unblock
  now=$(date +%s)
  if [ $(( now - frozen_since )) -gt 20 ] && [ "$frozen_since" -gt 0 ]; then
    # only one Escape per frozen episode
    if [ "${last_esc:-0}" != "$frozen_since" ]; then
      xdotool key --clearmodifiers Escape 2>/dev/null
      last_esc=$frozen_since
      escs=$((escs + 1))
      echo "sent Escape (unblock #$escs)"
    fi
  fi
done

echo "WARNING: tick still frozen after ${MAXWAIT}s ($escs unblocks sent)" >&2
exit 1
