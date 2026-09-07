#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
CONFIG="$BASE/config/restic/backup.env"
STATE="$BASE/data/restic-state.json"
LOG_DIR="$BASE/logs"

record() {
  install -d -m 0750 "$BASE/data" "$LOG_DIR"
  printf '{"time":"%s","state":"%s","detail":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" > "$STATE"
}

if [[ ! -f "$CONFIG" ]]; then
  record CONFIG_REQUIRED "remote repository is not configured"
  exit 0
fi

# The file is root-owned, mode 0600, and contains only restic backend settings.
set -a
. "$CONFIG"
set +a
if [[ -z "${RESTIC_REPOSITORY:-}" || -z "${RESTIC_PASSWORD_FILE:-}" || ! -r "$RESTIC_PASSWORD_FILE" ]]; then
  record CONFIG_INVALID "RESTIC_REPOSITORY or readable RESTIC_PASSWORD_FILE is missing"
  exit 1
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
