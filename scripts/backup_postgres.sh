#!/usr/bin/env bash
# Nightly Postgres backup (run as root or a user in the docker group).
# Writes custom-format dumps under BACKUP_ROOT and prunes files older than RETAIN_DAYS.

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/opt/backups/mls}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
CONTAINER="${CONTAINER:-mls-postgis}"
DB_USER="${DB_USER:-mls_user}"
DB_NAME="${DB_NAME:-mls_analytics}"

mkdir -p "$BACKUP_ROOT"
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
OUT="$BACKUP_ROOT/mls_${STAMP}.dump"

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "backup_postgres: container '$CONTAINER' not found" >&2
  exit 1
fi

docker exec -e PGPASSWORD="${PGPASSWORD:-mls_pass}" "$CONTAINER" \
  pg_dump -U "$DB_USER" -Fc "$DB_NAME" >"$OUT"

echo "backup_postgres: wrote $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_ROOT" -maxdepth 1 -name 'mls_*.dump' -mtime "+${RETAIN_DAYS}" -delete 2>/dev/null || true
