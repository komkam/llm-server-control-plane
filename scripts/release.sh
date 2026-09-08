#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
RELEASES="${BASE}/releases"
STAGING="${BASE}/staging"
LOCK="${RELEASES}/deploy.lock"
PACKAGE_PATHS=(apps services config deploy scripts docs compose.yaml install.sh README.md CHANGELOG.md .gitignore)
SERVICES=(ollama electrical-engineer mechanical-engineer monitor router agent dashboard autonomy)

release_dir() {
  printf '%s/%s\n' "$RELEASES" "$1"
}

state() {
  cat "$(release_dir "$1")/status" 2>/dev/null || true
}

package_application() {
  local source=$1 archive=$2
  tar \
    --exclude='apps/*/data' \
    --exclude='apps/*/.venv' \
    --exclude='apps/**/__pycache__' \
    --exclude='config/observability/secrets' \
    --exclude='config/secrets/age.key' \
    --exclude='config/security' \
    --exclude='deploy/.openwebui-image.env' \
    -C "$source" -czf "$archive" "${PACKAGE_PATHS[@]}"
}

verify_archive() {
  local directory
  directory=$(release_dir "$1")
  test -f "$directory/application.tar.gz"
  (cd "$directory" && sha256sum -c SHA256SUMS)
}

approval_checksum() {
  local approval=$1
  python3 - "$approval" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["checksum"])
PY
}

verify_approval() {
  local id=$1 directory actual expected
  directory=$(release_dir "$id")
  test "$(state "$id")" = APPROVED
  test -f "$directory/approval.json"
  actual=$(awk 'NR == 1 {print $1}' "$directory/SHA256SUMS")
  expected=$(approval_checksum "$directory/approval.json")
  test -n "$actual" && test "$actual" = "$expected"
}

deployment_event() {
  local file=$1 event_state=$2 backup_id=${3:-}
  printf '{"state":"%s","time":"%s","backup_id":"%s"}\n' \
    "$event_state" "$(date -u +%FT%TZ)" "$backup_id" >> "$file"
}

install_units() {
  local unit
  for unit in "$BASE"/config/systemd/*.service "$BASE"/config/systemd/*.timer; do
    test -f "$unit" || continue
    install -m 0644 "$unit" "/etc/systemd/system/$(basename "$unit")"
  done
  systemctl daemon-reload
}

start_services() {
  local service
  for service in "${SERVICES[@]}"; do
    systemctl start "${service}.service"
  done
}

baseline() {
  local id=${1:?baseline id required} directory previous
  directory=$(release_dir "$id")
  test ! -e "$directory"
  previous=$(readlink -f "$RELEASES/current" 2>/dev/null || true)
  install -d -m 0750 "$directory"
  package_application "$BASE" "$directory/application.tar.gz"
  (cd "$directory" && sha256sum application.tar.gz > SHA256SUMS)
  printf 'parent=\ncreated=%s\n' "$(date -u +%FT%TZ)" > "$directory/manifest"
  test -z "$previous" || echo SUPERSEDED > "$previous/status"
  echo ACTIVE > "$directory/status"
  ln -sfn "$directory" "$RELEASES/current"
  reconcile
  printf '%s\n' "$id"
}

stage() {
  local id=$1 current workspace
  current=$(readlink -f "$RELEASES/current")
  workspace="${STAGING}/${id}/workspace"
  test -n "$current" && test ! -e "$workspace"
  install -d -m 0750 "$workspace"
  tar -xzf "$current/application.tar.gz" -C "$workspace"
  printf 'parent=%s\ncreated=%s\n' "$(basename "$current")" "$(date -u +%FT%TZ)" > "${STAGING}/${id}/manifest"
  printf '%s\n' "$workspace"
}

candidate() {
  local id=$1 workspace directory
  workspace="${STAGING}/${id}/workspace"
  directory=$(release_dir "$id")
  test -d "$workspace" && test ! -e "$directory"
  install -d -m 0750 "$directory"
  package_application "$workspace" "$directory/application.tar.gz"
  (cd "$directory" && sha256sum application.tar.gz > SHA256SUMS)
  cp "${STAGING}/${id}/manifest" "$directory/manifest"
  echo PENDING > "$directory/status"
  printf '%s\n' "$id"
}

approve() {
  local id=$1 approver=${2:?approver required} reason=${3:?reason required}
  local directory checksum approval_id
  directory=$(release_dir "$id")
  test "$(state "$id")" = PENDING
  checksum=$(awk 'NR == 1 {print $1}' "$directory/SHA256SUMS")
  test -n "$checksum"
  approval_id="approval-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
  python3 - "$directory/approval.json" "$approval_id" "$id" "$checksum" "$approver" "$reason" "${STAGING}/${id}/artifacts/policy.json" <<'PY'
import json
import sys
from datetime import datetime, timezone
path, approval_id, candidate_id, checksum, approver, reason, policy_artifact = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({
        "approval_id": approval_id,
        "candidate_id": candidate_id,
        "checksum": checksum,
        "approver": approver,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy_artifact": policy_artifact,
    }, handle, separators=(",", ":"))
    handle.write("\n")
PY
  chmod 0640 "$directory/approval.json"
  echo APPROVED > "$directory/status"
}

list_releases() {
  local directory id release_state checksum manifest approval
  for directory in "$RELEASES"/*; do
    test -d "$directory" && test ! -L "$directory" && test -f "$directory/status" || continue
    id=$(basename "$directory")
    release_state=$(tr -d '\n' < "$directory/status")
    checksum=$(awk 'NR == 1 {print $1}' "$directory/SHA256SUMS" 2>/dev/null || true)
    manifest=$(tr '\n' ';' < "$directory/manifest" 2>/dev/null || true)
    approval=$(python3 - "$directory/approval.json" <<'PY' 2>/dev/null || true
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("approval_id", ""))
PY
)
    printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$release_state" "$checksum" "$manifest" "$approval"
  done
}

reconcile() {
  local active directory id release_state parent
  active=$(basename "$(readlink -f "$RELEASES/current")")
  for directory in "$RELEASES"/*; do
    test -d "$directory" && test ! -L "$directory" && test -f "$directory/status" || continue
    id=$(basename "$directory")
    release_state=$(state "$id")
    parent=$(sed -n 's/^parent=//p' "$directory/manifest")
    if test "$release_state" = ACTIVE && test "$id" != "$active"; then
      echo SUPERSEDED > "$directory/status"
    elif { test "$release_state" = PENDING || test "$release_state" = APPROVED; } && test "$parent" != "$active"; then
      echo STALE > "$directory/status"
    fi
  done
}

restore() {
  local id=$1 directory
  directory=$(release_dir "$id")
  verify_archive "$id"
  tar -xzf "$directory/application.tar.gz" -C "$BASE"
  install_units
  start_services
  "$BASE/scripts/verify.sh"
  ln -sfn "$directory" "$RELEASES/current"
  echo ACTIVE > "$directory/status"
  reconcile
}

deploy() {
  local id=$1 previous directory deployment_id parent record backup
  verify_approval "$id"
  verify_archive "$id"
  previous=$(basename "$(readlink -f "$RELEASES/current")")
  directory=$(release_dir "$id")
  parent=$(sed -n 's/^parent=//p' "$directory/manifest")
  test "$parent" = "$previous" || { echo "candidate parent $parent does not match active release $previous" >&2; exit 1; }

  deployment_id="deploy-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
  install -d -m 0750 "$RELEASES/deployments"
  record="$RELEASES/deployments/${deployment_id}.json"
  printf '{"deployment_id":"%s","candidate_id":"%s","parent_release":"%s","started":"%s"}\n' \
    "$deployment_id" "$id" "$previous" "$(date -u +%FT%TZ)" > "$record"

  deployment_event "$record" BACKUP_STARTED
  if ! backup=$("$BASE/scripts/backup.sh"); then
    deployment_event "$record" BACKUP_FAILED
    exit 1
  fi
  deployment_event "$record" BACKED_UP "${backup##*/}"
  deployment_event "$record" APPLYING

  local service
  for service in "${SERVICES[@]}"; do
    systemctl stop "${service}.service" || true
  done
  if ! tar -xzf "$directory/application.tar.gz" -C "$BASE" || ! install_units || ! start_services || ! "$BASE/scripts/verify.sh"; then
    deployment_event "$record" VERIFY_FAILED "${backup##*/}"
    echo FAILED > "$directory/status"
    if restore "$previous"; then
      deployment_event "$record" ROLLED_BACK "${backup##*/}"
    else
      deployment_event "$record" ROLLBACK_FAILED "${backup##*/}"
    fi
    exit 1
  fi

  ln -sfn "$directory" "$RELEASES/current"
  echo SUPERSEDED > "$(release_dir "$previous")/status"
  echo ACTIVE > "$directory/status"
  deployment_event "$record" SUCCESS "${backup##*/}"
}

rollback() {
  local current target
  current=$(basename "$(readlink -f "$RELEASES/current")")
  target=$(sed -n 's/^parent=//p' "$(release_dir "$current")/manifest")
  test -n "$target" && test -d "$(release_dir "$target")" || { echo "current release has no rollback parent" >&2; exit 1; }
  restore "$target"
  echo ROLLED_BACK > "$(release_dir "$current")/status"
}

timeline() {
  local record
  for record in "$RELEASES"/deployments/*.json; do
    test -f "$record" && cat "$record"
  done
}

run_locked() {
  (
    flock -n 9 || { echo 'deploy lock busy' >&2; exit 1; }
    "$@"
  ) 9>"$LOCK"
}

install -d -m 0750 "$RELEASES" "$STAGING"
case "${1:-}" in
  baseline|create) baseline "${2:?release id required}" ;;
  stage) stage "${2:?staging id required}" ;;
  candidate) candidate "${2:?candidate id required}" ;;
  approve) approve "${2:?candidate id required}" "${3:?approver required}" "${4:?reason required}" ;;
  list) list_releases ;;
  timeline) timeline ;;
  reconcile) reconcile ;;
  deploy) run_locked deploy "${2:?candidate id required}" ;;
  rollback) run_locked rollback ;;
  *) echo 'usage: release.sh {baseline|stage|candidate|approve|list|timeline|reconcile|deploy|rollback}' >&2; exit 2 ;;
esac
