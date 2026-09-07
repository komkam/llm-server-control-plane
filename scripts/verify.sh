#!/usr/bin/env bash
set -euo pipefail

BASE_DIR=/opt/llm-server
DASHBOARD_HEALTH_URL=${DASHBOARD_HEALTH_URL:-http://127.0.0.1:7000/api/health}
SERVICES=(ollama llama-server monitor router agent dashboard autonomy)

wait_for_http() {
  local url=$1 attempts=${2:-15}
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    curl --fail --silent "$url" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "health endpoint did not become ready: $url" >&2
  return 1
}

verify_units() {
  local output
  if ! output=$(systemd-analyze verify /etc/systemd/system/{agent,autonomy,dashboard,monitor,router}.service 2>&1); then
    printf '%s\n' "$output" >&2
    return 1
  fi
  printf '%s\n' "$output" | grep -v 'Support for option CPUAccounting= has been removed and it is ignored' >&2 || true
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

verify_units
visudo -cf /etc/sudoers.d/action-engine

wait_for_http http://127.0.0.1:5100/health
wait_for_http http://127.0.0.1:5000/health
wait_for_http "${DASHBOARD_HEALTH_URL}"

echo "Verification passed"
