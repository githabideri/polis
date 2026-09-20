#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
REPO_DIR="$(realpath "${SCRIPT_DIR}/..")"

DATA_DIR_DEFAULT="/home/${USER}/.var/app/at.vintagestory.VintageStory/config/VintagestoryData"
DATA_DIR="${DATA_DIR:-${DATA_DIR_DEFAULT}}"
LOG_DIR_DEFAULT="${DATA_DIR}/Logs"
LOG_DIR="${LOG_DIR:-${LOG_DIR_DEFAULT}}"

WORLD_NAME="${WORLD_NAME:-test-lands}"
COMMANDS_FILE="${COMMANDS_FILE:-${SCRIPT_DIR}/polis-commands.example.txt}"
CHAT_KEY="${CHAT_KEY:-t}"
CMD_DELAY_SECONDS="${CMD_DELAY_SECONDS:-0.4}"
LOAD_WAIT_SECONDS="${LOAD_WAIT_SECONDS:-180}"
POST_LOAD_WAIT_SECONDS="${POST_LOAD_WAIT_SECONDS:-5}"
READY_LOG_REGEX="${READY_LOG_REGEX:-Entering runphase WorldReady}"
READY_LOG_FILE="${READY_LOG_FILE:-${LOG_DIR}/server-main.log}"
LOG_QUIET_SECONDS="${LOG_QUIET_SECONDS:-5}"
FOCUS_CLICK="${FOCUS_CLICK:-0}"
EXIT_KEYS="${EXIT_KEYS:-Alt+F4}"
EXIT_AFTER_COMMANDS="${EXIT_AFTER_COMMANDS:-1}"
BEFORE_EXIT_WAIT_SECONDS="${BEFORE_EXIT_WAIT_SECONDS:-5}"
AFTER_COMMANDS_WAIT_SECONDS="${AFTER_COMMANDS_WAIT_SECONDS:-15}"
WINDOW_NAME="${WINDOW_NAME:-Vintage Story}"
WINDOW_CLASS="${WINDOW_CLASS:-Vintage Story.Vintage Story}"
VERIFY_FOCUS="${VERIFY_FOCUS:-1}"
WINDOW_ID_OVERRIDE="${WINDOW_ID_OVERRIDE:-}"
VERIFY_LOG_FILE="${VERIFY_LOG_FILE:-${LOG_DIR}/server-main.log}"
EXPECT_LOG_TIMEOUT_SECONDS="${EXPECT_LOG_TIMEOUT_SECONDS:-90}"
EXPECT_LOG_POLL_SECONDS="${EXPECT_LOG_POLL_SECONDS:-1}"
EXPECT_LOG_TOTAL_TIMEOUT_SECONDS="${EXPECT_LOG_TOTAL_TIMEOUT_SECONDS:-300}"
EXPECT_LOG_RETRY_INTERVAL_SECONDS="${EXPECT_LOG_RETRY_INTERVAL_SECONDS:-10}"
PRE_ACTION_KEYS="${PRE_ACTION_KEYS:-Escape}"
INITIAL_ACTION_WAIT_SECONDS="${INITIAL_ACTION_WAIT_SECONDS:-40}"
CHAT_OPEN_KEYS="${CHAT_OPEN_KEYS:-Return t}"
CHAT_OPEN_DELAY_SECONDS="${CHAT_OPEN_DELAY_SECONDS:-0.2}"

CLIENT_LOG="${LOG_DIR}/client-main.log"
SERVER_LOG="${LOG_DIR}/server-main.log"

FLATPAK_APP_ID="at.vintagestory.VintageStory"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd flatpak
require_cmd xdotool

search_log() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -n "${pattern}" "${file}"
  else
    grep -En "${pattern}" "${file}"
  fi
}

log_line_count() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    wc -l "${file}" | awk '{print $1}'
  else
    echo 0
  fi
}

wait_for_log_match() {
  local pattern="$1"
  local file="$2"
  local start_line="$3"
  local timeout="$4"
  local poll="${5}"
  local elapsed=0
  local poll_int
  poll_int=$(printf "%.0f" "${poll}")
  if [[ "${poll_int}" -lt 1 ]]; then
    poll_int=1
  fi

  while [[ "${elapsed}" -lt "${timeout}" ]]; do
    if [[ -f "${file}" ]]; then
      if command -v rg >/dev/null 2>&1; then
        tail -n +"$((start_line + 1))" "${file}" | rg -n "${pattern}" >/dev/null 2>&1 && return 0
      else
        tail -n +"$((start_line + 1))" "${file}" | grep -En "${pattern}" >/dev/null 2>&1 && return 0
      fi
    fi
    sleep "${poll_int}"
    elapsed=$((elapsed + poll_int))
  done

  return 1
}

wait_for_log_quiet() {
  local file="$1"
  local quiet_seconds="$2"
  local last_ts=0
  local stable_for=0
  while true; do
    if [[ -f "${file}" ]]; then
      current_ts=$(stat -c %Y "${file}" 2>/dev/null || echo 0)
      if [[ "${current_ts}" -eq "${last_ts}" ]]; then
        stable_for=$((stable_for + 1))
      else
        stable_for=0
        last_ts="${current_ts}"
      fi

      if [[ "${stable_for}" -ge "${quiet_seconds}" ]]; then
        break
      fi
    fi
    sleep 1
  done
}

ensure_focus() {
  if [[ "${VERIFY_FOCUS}" -ne 1 ]]; then
    return 0
  fi
  active_name="$(xdotool getactivewindow getwindowname 2>/dev/null || true)"
  if [[ "${active_name}" != *"${WINDOW_NAME}"* ]]; then
    echo "Focus check failed. Active window: ${active_name}" >&2
    exit 1
  fi
}

repeat_action() {
  local action_type="$1"
  local payload="$2"
  local window_id="$3"

  case "${action_type}" in
    KEY)
      xdotool windowactivate --sync "${window_id}"
      xdotool key --window "${window_id}" --clearmodifiers ${payload}
      ;;
    CHAT)
      xdotool windowactivate --sync "${window_id}"
      if [[ -n "${CHAT_OPEN_KEYS}" ]]; then
        xdotool key --window "${window_id}" --clearmodifiers ${CHAT_OPEN_KEYS}
        sleep "${CHAT_OPEN_DELAY_SECONDS}"
      else
        xdotool key --window "${window_id}" --clearmodifiers "${CHAT_KEY}"
        sleep 0.1
      fi
      xdotool type --window "${window_id}" --delay 20 "${payload}"
      xdotool key --window "${window_id}" --clearmodifiers Return
      ;;
    *)
      ;;
  esac
}

if [[ ! -f "${COMMANDS_FILE}" ]]; then
  echo "Commands file not found: ${COMMANDS_FILE}" >&2
  exit 1
fi

EXTRA_ARGS=()
if [[ "${LOG_DIR}" != "${DATA_DIR}/Logs" ]]; then
  EXTRA_ARGS+=(--logPath "${LOG_DIR}")
fi

echo "Launching Vintage Story client..."
flatpak run "${FLATPAK_APP_ID}" --openWorld "${WORLD_NAME}" "${EXTRA_ARGS[@]}" >/dev/null 2>&1 &
CLIENT_PID=$!

cleanup() {
  if kill -0 "${CLIENT_PID}" >/dev/null 2>&1; then
    kill "${CLIENT_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

get_window_id() {
  local win_id=""
  if [[ -n "${WINDOW_ID_OVERRIDE}" ]]; then
    echo "${WINDOW_ID_OVERRIDE}"
    return 0
  fi

  if [[ -n "${WINDOW_CLASS}" ]]; then
    win_id="$(xdotool search --class "${WINDOW_CLASS}" | head -n 1 || true)"
  fi
  if [[ -z "${win_id}" ]]; then
    win_id="$(xdotool search --name "${WINDOW_NAME}" | head -n 1 || true)"
  fi
  if [[ -z "${win_id}" ]] && command -v wmctrl >/dev/null 2>&1; then
    win_id="$(wmctrl -lx | rg -i 'vintage|story' | awk '{print $1}' | head -n 1 || true)"
  fi
  echo "${win_id}"
}

echo "Waiting for client window..."
WINDOW_ID=""
for _ in $(seq 1 60); do
  WINDOW_ID="$(get_window_id)"
  if [[ -n "${WINDOW_ID}" ]]; then
    break
  fi
  sleep 0.5
done

if [[ -z "${WINDOW_ID}" ]]; then
  echo "Could not find Vintage Story window. Try WINDOW_CLASS, WINDOW_NAME, or WINDOW_ID_OVERRIDE." >&2
  exit 1
fi

if [[ -n "${READY_LOG_REGEX}" ]]; then
  echo "Waiting for log readiness: ${READY_LOG_REGEX} in ${READY_LOG_FILE}"
  for _ in $(seq 1 240); do
    if [[ -f "${READY_LOG_FILE}" ]] && search_log "${READY_LOG_REGEX}" "${READY_LOG_FILE}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
else
  echo "Waiting ${LOAD_WAIT_SECONDS}s for world load..."
  sleep "${LOAD_WAIT_SECONDS}"
fi

if [[ "${LOG_QUIET_SECONDS}" -gt 0 ]]; then
  echo "Waiting for log quiet (${LOG_QUIET_SECONDS}s): ${READY_LOG_FILE}"
  wait_for_log_quiet "${READY_LOG_FILE}" "${LOG_QUIET_SECONDS}"
fi

sleep "${POST_LOAD_WAIT_SECONDS}"
if [[ "${INITIAL_ACTION_WAIT_SECONDS}" -gt 0 ]]; then
  echo "Waiting ${INITIAL_ACTION_WAIT_SECONDS}s before first action..."
  sleep "${INITIAL_ACTION_WAIT_SECONDS}"
fi

xdotool windowactivate --sync "${WINDOW_ID}"
sleep 0.2

echo "Running commands from: ${COMMANDS_FILE}"
log_checkpoint="$(log_line_count "${VERIFY_LOG_FILE}")"
last_action_type=""
last_action_payload=""
while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
  line="$(echo "${raw_line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  if [[ -z "${line}" ]] || [[ "${line}" == \#* ]]; then
    continue
  fi

  WINDOW_ID="$(get_window_id)"
  if [[ -z "${WINDOW_ID}" ]]; then
    echo "Window not found before action; aborting." >&2
    exit 1
  fi

  xdotool windowactivate --sync "${WINDOW_ID}"
  if [[ "${FOCUS_CLICK}" -ge 1 ]]; then
    xdotool windowfocus "${WINDOW_ID}"
    if [[ "${FOCUS_CLICK}" -ge 2 ]]; then
      eval "$(xdotool getwindowgeometry --shell "${WINDOW_ID}")"
      center_x=$((X + (WIDTH / 2)))
      center_y=$((Y + (HEIGHT / 2)))
      xdotool mousemove "${center_x}" "${center_y}"
    fi
    xdotool click --window "${WINDOW_ID}" 1
  fi
  ensure_focus

  if [[ -n "${PRE_ACTION_KEYS}" ]]; then
    xdotool key --window "${WINDOW_ID}" --clearmodifiers ${PRE_ACTION_KEYS}
    sleep 0.2
  fi

  if [[ "${line}" == CHECKPOINT ]]; then
    log_checkpoint="$(log_line_count "${VERIFY_LOG_FILE}")"
    last_action_type=""
    last_action_payload=""
  elif [[ "${line}" == EXPECT_LOG:* ]]; then
    pattern="${line#EXPECT_LOG:}"
    pattern="$(echo "${pattern}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ -z "${pattern}" ]]; then
      continue
    fi
    if [[ ! -f "${VERIFY_LOG_FILE}" ]]; then
      echo "EXPECT_LOG skipped; log file not found: ${VERIFY_LOG_FILE}" >&2
      continue
    fi
    echo "Waiting for log match: ${pattern}"
    elapsed_total=0
    until wait_for_log_match "${pattern}" "${VERIFY_LOG_FILE}" "${log_checkpoint}" "${EXPECT_LOG_TIMEOUT_SECONDS}" "${EXPECT_LOG_POLL_SECONDS}"; do
      elapsed_total=$((elapsed_total + EXPECT_LOG_TIMEOUT_SECONDS))
      if [[ "${elapsed_total}" -ge "${EXPECT_LOG_TOTAL_TIMEOUT_SECONDS}" ]]; then
        echo "EXPECT_LOG total timeout after ${elapsed_total}s: ${pattern}" >&2
        break
      fi

      if [[ -n "${last_action_type}" ]]; then
        echo "Retrying last action for EXPECT_LOG..."
        repeat_action "${last_action_type}" "${last_action_payload}" "${WINDOW_ID}"
      fi

      sleep "${EXPECT_LOG_RETRY_INTERVAL_SECONDS}"
    done
  elif [[ "${line}" == WAIT:* ]]; then
    wait_secs="${line#WAIT:}"
    wait_secs="$(echo "${wait_secs}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ -n "${wait_secs}" ]]; then
      sleep "${wait_secs}"
    fi
  elif [[ "${line}" == KEY:* ]]; then
    key_seq="${line#KEY:}"
    key_seq="$(echo "${key_seq}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ -n "${key_seq}" ]]; then
      xdotool windowactivate --sync "${WINDOW_ID}"
      xdotool key --window "${WINDOW_ID}" --clearmodifiers ${key_seq}
      last_action_type="KEY"
      last_action_payload="${key_seq}"
    fi
  elif [[ "${line}" == CHAT:* ]]; then
    chat_msg="${line#CHAT:}"
    chat_msg="$(echo "${chat_msg}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    xdotool windowactivate --sync "${WINDOW_ID}"
    if [[ -n "${CHAT_OPEN_KEYS}" ]]; then
      xdotool key --window "${WINDOW_ID}" --clearmodifiers ${CHAT_OPEN_KEYS}
      sleep "${CHAT_OPEN_DELAY_SECONDS}"
    else
      xdotool key --window "${WINDOW_ID}" --clearmodifiers "${CHAT_KEY}"
      sleep 0.1
    fi
    xdotool type --window "${WINDOW_ID}" --delay 20 "${chat_msg}"
    xdotool key --window "${WINDOW_ID}" --clearmodifiers Return
    last_action_type="CHAT"
    last_action_payload="${chat_msg}"
  else
    xdotool windowactivate --sync "${WINDOW_ID}"
    if [[ -n "${CHAT_OPEN_KEYS}" ]]; then
      xdotool key --window "${WINDOW_ID}" --clearmodifiers ${CHAT_OPEN_KEYS}
      sleep "${CHAT_OPEN_DELAY_SECONDS}"
    else
      xdotool key --window "${WINDOW_ID}" --clearmodifiers "${CHAT_KEY}"
      sleep 0.1
    fi
    xdotool type --window "${WINDOW_ID}" --delay 20 "${line}"
    xdotool key --window "${WINDOW_ID}" --clearmodifiers Return
    last_action_type="CHAT"
    last_action_payload="${line}"
  fi
  sleep "${CMD_DELAY_SECONDS}"
done < "${COMMANDS_FILE}"

if [[ "${EXIT_AFTER_COMMANDS}" -eq 1 ]]; then
  if [[ "${BEFORE_EXIT_WAIT_SECONDS}" -gt 0 ]]; then
    echo "Waiting ${BEFORE_EXIT_WAIT_SECONDS}s before exit..."
    sleep "${BEFORE_EXIT_WAIT_SECONDS}"
  fi
  echo "Exiting client..."
  xdotool key --window "${WINDOW_ID}" --clearmodifiers ${EXIT_KEYS}

  sleep 2
  if kill -0 "${CLIENT_PID}" >/dev/null 2>&1; then
    echo "Client still running; terminating."
    kill "${CLIENT_PID}" >/dev/null 2>&1 || true
  fi
else
  echo "EXIT_AFTER_COMMANDS=0; leaving client running."
  if [[ "${AFTER_COMMANDS_WAIT_SECONDS}" -gt 0 ]]; then
    echo "Waiting ${AFTER_COMMANDS_WAIT_SECONDS}s after commands..."
    sleep "${AFTER_COMMANDS_WAIT_SECONDS}"
  fi
fi

echo "Log summary:"
if [[ -f "${SERVER_LOG}" ]]; then
  echo "-- server-main.log --"
  search_log "\\[polis\\]|error|exception" "${SERVER_LOG}" || true
else
  echo "Server log not found: ${SERVER_LOG}"
fi

if [[ -f "${CLIENT_LOG}" ]]; then
  echo "-- client-main.log --"
  search_log "\\[polis\\]|error|exception" "${CLIENT_LOG}" || true
else
  echo "Client log not found: ${CLIENT_LOG}"
fi
