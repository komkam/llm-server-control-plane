#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=/opt/llm-server
TAILSCALE_IP=100.69.21.124
SERVICES=(ollama llama-server monitor router agent dashboard autonomy)

wait_for_http() {
  local url=$1 attempts=${2:-15}
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    curl --fail --silent --show-error "$url" >/dev/null && return 0
    sleep 2
  done
  echo "health endpoint did not become ready: $url" >&2
  return 1
}

for service in "${SERVICES[@]}"; do
  systemctl is-active --quiet "${service}.service"
done

"${BASE_DIR}/venv/bin/python" -m py_compile \
  "${BASE_DIR}/services/autonomy.py" \
  "${BASE_DIR}/services/monitor.py" \
  "${BASE_DIR}/apps/dashboard/app.py"
"${BASE_DIR}/apps/agent/.venv/bin/python" -m py_compile \
  "${BASE_DIR}/apps/agent/agent_server.py"

systemd-analyze verify /etc/systemd/system/{agent,autonomy,dashboard,monitor,router}.service
visudo -cf /etc/sudoers.d/action-engine

wait_for_http http://127.0.0.1:5100/health
wait_for_http http://127.0.0.1:5000/health
wait_for_http "http://${TAILSCALE_IP}:7000/api/health"

echo "Verification passed"
