#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
ENV_FILE="$BASE/.env"
STATE="$BASE/data/restic-state.json"
LOG_DIR="$BASE/logs"

record() {
  install -d -m 0750 "$BASE/data" "$LOG_DIR"
  printf '{"time":"%s","state":"%s","detail":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" > "$STATE"
}

set -a
. "$ENV_FILE"
set +a
if [[ -z "${RESTIC_REPOSITORY:-}" || -z "${RESTIC_PASSWORD:-}" ]]; then
  record CONFIG_REQUIRED "RESTIC_REPOSITORY and RESTIC_PASSWORD are required in .env"
  exit 0
fi

if ! /usr/bin/restic snapshots >/dev/null 2>&1; then
  /usr/bin/restic init
fi

if /usr/bin/restic backup --tag llm-server --one-file-system \
  "$BASE/apps" "$BASE/services" "$BASE/config" "$BASE/deploy" "$BASE/scripts" "$BASE/docs" \
  "$BASE/data" "$BASE/logs" "$BASE/open-webui" "$BASE/releases"; then
  /usr/bin/restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
  record SUCCESS "encrypted offsite backup completed"
else
  record FAILED "restic backup failed; inspect journalctl -u restic-backup.service"
  exit 1
fi
