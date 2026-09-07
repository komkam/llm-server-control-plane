#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
DEPLOY_DIR="$BASE/deploy"
ENV_FILE="$DEPLOY_DIR/.openwebui-image.env"
UPDATE_DIR="$BASE/image-updates"
IMAGE=ghcr.io/open-webui/open-webui:main
COMPOSE=(/usr/bin/docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yaml")

candidate_dir(){ printf '%s/%s' "$UPDATE_DIR" "$1"; }
state(){ cat "$(candidate_dir "$1")/status" 2>/dev/null || true; }
wait_for_webui(){ local attempt; for ((attempt=1; attempt<=15; attempt++)); do curl --fail --silent http://127.0.0.1:3000/ >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
current_image(){ grep '^OPENWEBUI_IMAGE=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || /usr/bin/docker inspect --format '{{.Image}}' open-webui; }

prepare(){
  local id=$1 dir previous resolved
  dir=$(candidate_dir "$id"); test ! -e "$dir"; install -d -m 0750 "$dir"
  previous=$(current_image)
  /usr/bin/docker pull "$IMAGE" >/dev/null
  resolved=$(/usr/bin/docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}')
  test -n "$resolved" && test "$resolved" != "<no value>"
  printf '{"id":"%s","image":"%s","previous_image":"%s","created_at":"%s"}\n' "$id" "$resolved" "$previous" "$(date -u +%FT%TZ)" > "$dir/manifest.json"
  echo PENDING > "$dir/status"
  echo "$id"
}

approve(){
  local id=$1 approver=$2 reason=$3 dir
  dir=$(candidate_dir "$id"); test "$(state "$id")" = PENDING
  python3 - "$dir/manifest.json" "$dir/approval.json" "$approver" "$reason" <<'PY'
import json, sys
manifest, output, approver, reason = sys.argv[1:]
with open(manifest) as handle: data = json.load(handle)
data.update({"approver": approver, "reason": reason, "approved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
with open(output, "w") as handle: json.dump(data, handle, separators=(",", ":"))
PY
  echo APPROVED > "$dir/status"
}

deploy(){
  local id=$1 dir image previous backup_env
  dir=$(candidate_dir "$id"); test "$(state "$id")" = APPROVED; test -f "$dir/approval.json"
  image=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$dir/manifest.json")
  previous=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["previous_image"])' "$dir/manifest.json")
  backup_env="$dir/previous.env"; test ! -e "$ENV_FILE" || cp "$ENV_FILE" "$backup_env"
  printf 'OPENWEBUI_IMAGE=%s\n' "$image" > "$ENV_FILE"
  if "${COMPOSE[@]}" up -d --no-deps open-webui && wait_for_webui; then
    echo DEPLOYED > "$dir/status"; printf '{"state":"SUCCESS","time":"%s"}\n' "$(date -u +%FT%TZ)" >> "$dir/events.jsonl"; return 0
  fi
  if test -f "$backup_env"; then cp "$backup_env" "$ENV_FILE"; else printf 'OPENWEBUI_IMAGE=%s\n' "$previous" > "$ENV_FILE"; fi
  "${COMPOSE[@]}" up -d --no-deps open-webui
  wait_for_webui
  echo ROLLED_BACK > "$dir/status"; printf '{"state":"ROLLED_BACK","time":"%s"}\n' "$(date -u +%FT%TZ)" >> "$dir/events.jsonl"
  return 1
}

install -d -m 0750 "$UPDATE_DIR"
case "${1:-}" in prepare) prepare "$2";; approve) approve "$2" "$3" "$4";; deploy) deploy "$2";; *) echo 'usage: openwebui_image_update.sh {prepare <id>|approve <id> <approver> <reason>|deploy <id>}' >&2; exit 2;; esac
