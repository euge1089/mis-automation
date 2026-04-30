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
  echo "Another scheduled run is already active (${LOCK_DIR}). Exiting."
  exit 0
fi
trap 'rmdir "${LOCK_DIR}"' EXIT

TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
LOG_FILE="${LOG_DIR}/${COMMAND}_${TIMESTAMP}.log"

ENV_FILE="${PROJECT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ENV_FILE}"
  set +a
fi

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
  "${PYTHON_BIN}" pipeline.py "${COMMAND}" "$@"
  echo "=== Scheduled run complete: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
} >> "${LOG_FILE}" 2>&1

echo "Run complete. Log: ${LOG_FILE}"
