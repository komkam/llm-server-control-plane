#!/usr/bin/env bash
set -euo pipefail

# Installs repository-owned systemd definitions and creates one machine-local
# .env file. It never enables or starts services automatically.

BASE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE=${BASE_DIR}/.env

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh" >&2
  exit 1
fi

for required in \
  "${BASE_DIR}/.env.example" \
  "${BASE_DIR}/config/systemd/dashboard.service"; do
  [[ -f ${required} ]] || { echo "Missing required file: ${required}" >&2; exit 1; }
done

if [[ ! -e ${ENV_FILE} ]]; then
  install -m 0600 "${BASE_DIR}/.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE}; replace every GENERATE_AT_INSTALL value before enabling services."
else
  chmod 0600 "${ENV_FILE}"
  echo "Preserved existing ${ENV_FILE}."
fi


units=(
  action-engine.service agent.service autonomy.service dashboard.service monitor.service router.service electrical-engineer.service mechanical-engineer.service
  control-plane-exporter.service docker-exporter.service gpu-exporter.service
  observability.service openwebui-image-check.service restic-backup.service restic-backup.timer
)

installed=0
for name in "${units[@]}"; do
  unit="${BASE_DIR}/config/systemd/${name}"
  [[ -f ${unit} ]] || { echo "Missing bundled unit: ${unit}" >&2; exit 1; }
  install -m 0644 "${unit}" "/etc/systemd/system/${name}"
  installed=$((installed + 1))
done

systemctl daemon-reload
echo "Installed ${installed} systemd unit files. No services were enabled or started."
echo "Next: review ${ENV_FILE}, then enable only the services you need."
