#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=/opt/llm-server
TAILSCALE_IP=100.69.21.124
SERVICES=(ollama llama-server monitor router agent dashboard autonomy)

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

curl --fail --silent --show-error http://127.0.0.1:5100/health >/dev/null
curl --fail --silent --show-error http://127.0.0.1:5000/health >/dev/null
curl --fail --silent --show-error "http://${TAILSCALE_IP}:7000/api/health" >/dev/null

echo "Verification passed"
