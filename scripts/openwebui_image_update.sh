#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
DEPLOY_DIR="$BASE/deploy"
ENV_FILE="$DEPLOY_DIR/.openwebui-image.env"
UPDATE_DIR="$BASE/image-updates"
IMAGE=llm-server/open-webui:security-patched
TRIVY_IMAGE=aquasec/trivy:0.68.2
COMPOSE=(/usr/bin/docker compose --project-name llm-server --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yaml")

candidate_dir(){ printf '%s/%s' "$UPDATE_DIR" "$1"; }
state(){ cat "$(candidate_dir "$1")/status" 2>/dev/null || true; }
wait_for_webui(){ local attempt; for ((attempt=1; attempt<=30; attempt++)); do curl --fail --silent http://127.0.0.1:3000/ >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
current_image(){ grep '^OPENWEBUI_IMAGE=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || /usr/bin/docker inspect --format '{{.Config.Image}}' open-webui; }

scan_image(){
  local archive=$1 report=$2
  /usr/bin/docker save -o "$archive" "$IMAGE"
  /usr/bin/docker run --rm -v "$archive:/image.tar:ro" -v "$(dirname "$report"):/artifacts" -v "$BASE/data/trivy-cache:/root/.cache" "$TRIVY_IMAGE" image --input /image.tar --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/artifacts/$(basename "$report")"
  /usr/bin/docker run --rm -v "$archive:/image.tar:ro" -v "$BASE/data/trivy-cache:/root/.cache" "$TRIVY_IMAGE" image --input /image.tar --severity CRITICAL --ignore-unfixed --exit-code 1
}

prepare(){
  local id=$1 dir previous
  dir=$(candidate_dir "$id"); test ! -e "$dir"; install -d -m 0750 "$dir"
  previous=$(current_image)
  /usr/bin/docker build --pull --tag "$IMAGE" -f "$DEPLOY_DIR/openwebui-patched/Dockerfile" "$DEPLOY_DIR/openwebui-patched"
  if ! scan_image "$dir/image.tar" "$dir/trivy.json"; then
    printf '{"decision":"REJECT","reason":"critical image vulnerability","image":"%s"}\n' "$IMAGE" > "$dir/security.json"
    echo REJECTED > "$dir/status"
    return 1
  fi
  /usr/bin/docker run --rm --entrypoint python "$IMAGE" -c 'import nltk; assert nltk.__version__ == "3.10.3"'
  printf '{"id":"%s","image":"%s","previous_image":"%s","created_at":"%s","security":"passed"}\n' "$id" "$IMAGE" "$previous" "$(date -u +%FT%TZ)" > "$dir/manifest.json"
  printf '{"decision":"ALLOW","scanner":"trivy","critical":0}\n' > "$dir/security.json"
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
