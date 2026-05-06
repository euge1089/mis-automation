#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs/scheduler"
LOCK_DIR="${PROJECT_DIR}/.scheduler-lock"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_scheduled_pipeline.sh monthly [--with-scrape]
  bash scripts/run_scheduled_pipeline.sh weekly-sold-rented [--headless]
  bash scripts/run_scheduled_pipeline.sh daily-active [--with-scrape] [--with-geocode] [--no-load-db]

Examples:
  bash scripts/run_scheduled_pipeline.sh monthly
  bash scripts/run_scheduled_pipeline.sh weekly-sold-rented --headless
  bash scripts/run_scheduled_pipeline.sh daily-active
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

COMMAND="$1"
shift

if [[ "${COMMAND}" != "monthly" && "${COMMAND}" != "weekly-sold-rented" && "${COMMAND}" != "daily-active" ]]; then
  echo "Error: command must be monthly, weekly-sold-rented, or daily-active." >&2
  usage
  exit 2
fi

mkdir -p "${LOG_DIR}"
mkdir -p "${PROJECT_DIR}/logs"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  SKIP_MSG="SCHEDULER_STATUS=SKIPPED_LOCK timestamp=${TIMESTAMP} command=${COMMAND} lock_dir=${LOCK_DIR}"
  echo "${SKIP_MSG}" >&2
  echo "${SKIP_MSG}" >> "${LOG_DIR}/skipped_runs.log"
  echo "Another scheduled run is already active (${LOCK_DIR}). Exiting."
  exit 0
fi
trap 'rmdir "${LOCK_DIR}"' EXIT

TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
LOG_FILE="${LOG_DIR}/${COMMAND}_${TIMESTAMP}.log"
RUN_EXIT=0

# Do not shell-source .env here. Values like MLS_PASSWORD may contain shell-special
# characters that get expanded/altered by `source`, causing bad credentials.
# Python entrypoints already load .env safely via python-dotenv.

# Cron-friendly log flushing (otherwise Python may buffer until process exit).
export PYTHONUNBUFFERED=1

if [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

{
  echo "=== Scheduled run start: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
  echo "Project dir: ${PROJECT_DIR}"
  echo "Python: ${PYTHON_BIN}"
  echo "Command: pipeline.py ${COMMAND} $*"
  cd "${PROJECT_DIR}"
  "${PYTHON_BIN}" pipeline.py "${COMMAND}" "$@" || RUN_EXIT=$?
  if [[ "${RUN_EXIT}" -eq 0 ]]; then
    echo "=== Scheduled run complete: $(date -u +"%Y-%m-%dT%H:%M:%SZ") status=ok ==="
  else
    echo "=== Scheduled run complete: $(date -u +"%Y-%m-%dT%H:%M:%SZ") status=failed exit_code=${RUN_EXIT} ==="
  fi
} >> "${LOG_FILE}" 2>&1

if [[ "${RUN_EXIT}" -eq 0 ]]; then
  echo "SCHEDULER_STATUS=OK log=${LOG_FILE}"
  echo "Run complete. Log: ${LOG_FILE}"
else
  echo "SCHEDULER_STATUS=FAILED exit_code=${RUN_EXIT} log=${LOG_FILE}" >&2
  echo "Run failed. Log: ${LOG_FILE}" >&2
  exit "${RUN_EXIT}"
fi
