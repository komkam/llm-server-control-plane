#!/usr/bin/env bash
set -euo pipefail

# Installs repository-owned systemd definitions and creates only a local
# runtime configuration. It never enables or starts services automatically.

BASE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
RUNTIME_DIR=/etc/llm-server
RUNTIME_ENV=${RUNTIME_DIR}/runtime.env

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh" >&2
  exit 1
fi

for required in \
  "${BASE_DIR}/config/runtime.env.example" \
  "${BASE_DIR}/config/systemd/dashboard.service"; do
  [[ -f ${required} ]] || { echo "Missing required file: ${required}" >&2; exit 1; }
done

install -d -m 0750 "${RUNTIME_DIR}"
if [[ ! -e ${RUNTIME_ENV} ]]; then
  install -m 0640 "${BASE_DIR}/config/runtime.env.example" "${RUNTIME_ENV}"
  echo "Created ${RUNTIME_ENV}; edit it before enabling services."
else
  echo "Preserved existing ${RUNTIME_ENV}."
fi
GRAFANA_SECRET="${BASE_DIR}/config/observability/secrets/grafana_admin_password"
if [[ ! -s ${GRAFANA_SECRET} ]]; then
  command -v openssl >/dev/null || { echo "openssl is required to create the Grafana credential" >&2; exit 1; }
  install -d -m 0750 "$(dirname "${GRAFANA_SECRET}")"
  umask 077
  openssl rand -base64 24 > "${GRAFANA_SECRET}"
  chmod 0600 "${GRAFANA_SECRET}"
  echo "Created a local Grafana credential at ${GRAFANA_SECRET}."
fi


units=(
  action-engine.service agent.service autonomy.service dashboard.service monitor.service router.service electrical-engineer.service
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
echo "Next: review /etc/llm-server/runtime.env, then enable only the services you need."
