#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=/opt/llm-server
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DESTINATION="${BASE_DIR}/backups/snapshots/${STAMP}"

install -d -m 0750 "${DESTINATION}"
tar -C "${BASE_DIR}" -czf "${DESTINATION}/application.tar.gz" \
  apps services config deploy scripts docs \
  data/autonomy-state.json data/state.json data/history.json \
  logs/autonomy.jsonl
cp /etc/systemd/system/{agent,autonomy,dashboard,monitor,router}.service "${DESTINATION}/"
cp /etc/sudoers.d/action-engine "${DESTINATION}/"
sha256sum "${DESTINATION}"/* > "${DESTINATION}/SHA256SUMS"
echo "Backup created: ${DESTINATION}"
