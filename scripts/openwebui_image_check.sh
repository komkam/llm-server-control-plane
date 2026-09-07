#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
DEPLOY="$BASE/deploy/.openwebui-image.env"
OUT="$BASE/data/image-update-proposals"
IMAGE=ghcr.io/open-webui/open-webui:main
install -d -m 0750 "$OUT"

current=$(grep '^OPENWEBUI_IMAGE=' "$DEPLOY" 2>/dev/null | cut -d= -f2- || /usr/bin/docker inspect --format '{{.Image}}' open-webui)
manifest=$(/usr/bin/docker manifest inspect "$IMAGE")
remote=$(printf '%s' "$manifest" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("Descriptor",{}).get("digest") or d.get("config",{}).get("digest") or "")')
test -n "$remote"

if [[ "$current" != *"$remote"* ]]; then
  id="openwebui-proposal-$(date -u +%Y%m%dT%H%M%SZ)"
  printf '{"id":"%s","state":"PROPOSED","image":"%s","current":"%s","remote_digest":"%s","checked_at":"%s","next":"prepare image candidate after approval"}\n' "$id" "$IMAGE" "$current" "$remote" "$(date -u +%FT%TZ)" > "$OUT/$id.json"
fi
