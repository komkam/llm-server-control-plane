#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/llm-server
ID=${1:?staging id required}
WORK="$BASE/staging/${ID}/workspace"
ARTIFACTS="$BASE/staging/${ID}/artifacts"
REFERENCE="$BASE/staging/${ID}/reference"
if ! test -d "$WORK"; then "$BASE/scripts/release.sh" stage "$ID" >/dev/null; fi
install -d -m 0750 "$ARTIFACTS"
if ! test -d "$REFERENCE"; then install -d -m 0750 "$REFERENCE"; tar -xzf "$(readlink -f "$BASE/releases/current")/application.tar.gz" -C "$REFERENCE"; fi

# Build from current source but never stage runtime state or private material.
for component in apps services config deploy scripts docs; do
  rsync -a --exclude='data' --exclude='__pycache__' --exclude='.venv' --exclude='logs' "$BASE/$component/" "$WORK/$component/"
done
cp -f "$BASE/.sops.yaml" "$WORK/.sops.yaml" 2>/dev/null || true
rm -rf "$WORK/apps/agent/data" "$WORK/apps/action-engine/data" "$WORK/apps/dashboard/data"
rm -f "$WORK/config/secrets/age.key" "$WORK/deploy/.openwebui-image.env"

> "$ARTIFACTS/diff.patch"
for component in apps services config deploy scripts docs .sops.yaml; do
  diff -ruN --exclude='__pycache__' --exclude='.venv' --exclude='data' --exclude='logs' "$REFERENCE/$component" "$WORK/$component" >> "$ARTIFACTS/diff.patch" || test $? -eq 1
done
grep '^diff -ruN ' "$ARTIFACTS/diff.patch" | awk '{print $NF}' | sed "s|$WORK/||" | sort -u > "$ARTIFACTS/changed-paths.txt" || true
python3 "$BASE/scripts/policy_engine.py" < "$ARTIFACTS/changed-paths.txt" > "$ARTIFACTS/policy.json"
find "$WORK" -type f -name '*.py' -not -path '*/.venv/*' -not -path '*/__pycache__/*' -print0 | xargs -0 -r python3 -m py_compile
find "$WORK" -type f -name '*.sh' -not -path '*/.venv/*' -print0 | xargs -0 -r bash -n
"$BASE/scripts/security_scan.sh" "$ID"
grep -q '"decision":"ALLOW"' "$ARTIFACTS/security.json" || { echo "security artifact is not ALLOW" >&2; exit 1; }
printf '{"syntax":"passed","security":"passed","builder":"candidate_builder","workspace":"%s"}\n' "$WORK" > "$ARTIFACTS/validation.json"
"$BASE/scripts/release.sh" candidate "$ID"
