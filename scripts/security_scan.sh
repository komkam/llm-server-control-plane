#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
ID=${1:?candidate id required}
WORK="$BASE/staging/$ID/workspace"
ARTIFACTS="$BASE/staging/$ID/artifacts"
CACHE="$BASE/data/trivy-cache"
TRIVY_IMAGE=aquasec/trivy:0.68.2
GITLEAKS_IMAGE=zricethezav/gitleaks:v8.30.0
install -d -m 0750 "$ARTIFACTS" "$CACHE"

if ! /usr/bin/docker run --rm --network none -v "$WORK:/workspace:ro" -v "$ARTIFACTS:/artifacts" "$GITLEAKS_IMAGE" dir --redact --report-format json --report-path /artifacts/gitleaks.json /workspace; then
  printf '{"decision":"REJECT","reason":"gitleaks findings"}\n' > "$ARTIFACTS/security.json"; exit 1
fi
/usr/bin/docker run --rm -v "$WORK:/workspace:ro" -v "$ARTIFACTS:/artifacts" -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" fs --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed --format json --output /artifacts/trivy-filesystem.json /workspace
if ! /usr/bin/docker run --rm -v "$WORK:/workspace:ro" -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" fs --scanners vuln,secret --severity CRITICAL --ignore-unfixed --exit-code 1 /workspace; then
  printf '{"decision":"REJECT","reason":"critical filesystem vulnerability or secret finding"}\n' > "$ARTIFACTS/security.json"; exit 1
fi

mapfile -t COMPOSE_FILES < <(find "$WORK/deploy" -maxdepth 1 -type f \( -name '*compose*.yaml' -o -name '*compose*.yml' \) -print | sort)
> "$ARTIFACTS/image-inventory.txt"
for compose in "${COMPOSE_FILES[@]}"; do /usr/bin/docker compose -f "$compose" config --images >> "$ARTIFACTS/image-inventory.txt"; done
sort -u -o "$ARTIFACTS/image-inventory.txt" "$ARTIFACTS/image-inventory.txt"
index=0
exception(){ test "$ID" = "observability-corrective2-20260907" && grep -Fxq "$1" "$BASE/config/security/one-time-cve-exception.images"; }
while IFS= read -r image; do
  test -n "$image" || continue; index=$((index+1)); report="trivy-image-${index}.json"
  if /usr/bin/docker image inspect "$image" >/dev/null 2>&1; then
    archive="$ARTIFACTS/image-${index}.tar"
    /usr/bin/docker save -o "$archive" "$image"
    /usr/bin/docker run --rm -v "$archive:/image.tar:ro" -v "$ARTIFACTS:/artifacts" -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" image --input /image.tar --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/artifacts/$report"
    if ! /usr/bin/docker run --rm -v "$archive:/image.tar:ro" -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" image --input /image.tar --severity CRITICAL --ignore-unfixed --exit-code 1; then
      if exception "$image"; then printf "%s\n" "$image" >> "$ARTIFACTS/cve-exceptions-used.txt"; else printf "{\"decision\":\"REJECT\",\"reason\":\"critical image vulnerability\",\"image\":\"%s\"}\n" "$image" > "$ARTIFACTS/security.json"; exit 1; fi
    fi
  else
    /usr/bin/docker run --rm -v "$ARTIFACTS:/artifacts" -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" image --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/artifacts/$report" "$image"
    if ! /usr/bin/docker run --rm -v "$CACHE:/root/.cache/" "$TRIVY_IMAGE" image --severity CRITICAL --ignore-unfixed --exit-code 1 "$image"; then
      if exception "$image"; then printf "%s\n" "$image" >> "$ARTIFACTS/cve-exceptions-used.txt"; else printf "{\"decision\":\"REJECT\",\"reason\":\"critical image vulnerability\",\"image\":\"%s\"}\n" "$image" > "$ARTIFACTS/security.json"; exit 1; fi
    fi
  fi
done < "$ARTIFACTS/image-inventory.txt"
printf '{"decision":"ALLOW","gitleaks":"passed","trivy":"passed","image_count":%s}\n' "$index" > "$ARTIFACTS/security.json"
