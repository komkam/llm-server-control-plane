#!/usr/bin/env python3
"""Read-only Prometheus exporter for the constrained LLM control plane."""

import json
import os
import subprocess
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

BASE = "/opt/llm-server"
ACTION_LOG = f"{BASE}/apps/action-engine/data/actions.jsonl"
AUTONOMY_LOG = f"{BASE}/logs/autonomy.jsonl"
DEPLOYMENTS = f"{BASE}/releases/deployments"
SERVICES = (
    "llm-gateway", "embedding-classifier", "agent", "dashboard", "ollama", "monitor",
    "autonomy", "action-engine", "observability", "control-plane-exporter",
    "gpu-exporter", "docker-exporter", "electrical-engineer", "mechanical-engineer",
)


def label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def tail_json(path: str, limit: int = 5000) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            return [json.loads(row) for row in deque(handle, maxlen=limit) if row.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def service_up(service: str) -> int:
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", f"{service}.service"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    return int(result.returncode == 0)


def proposals() -> Counter:
    values: Counter = Counter()
    try:
        with urlopen("http://127.0.0.1:5200/v1/proposals", timeout=3) as response:
            for item in json.load(response).get("proposals", []):
                values[(item.get("type", "unknown"), item.get("state", "unknown"), item.get("risk", "unknown"))] += 1
    except OSError:
        values[("control_plane", "unavailable", "unknown")] = 1
    return values


def metrics() -> str:
    lines = [
        "# HELP llm_control_service_up Whether a managed control-plane service is active.",
        "# TYPE llm_control_service_up gauge",
    ]
    lines.extend(f'llm_control_service_up{{service="{label(service)}"}} {service_up(service)}' for service in SERVICES)

    actions = Counter((row.get("action", "unknown"), row.get("state", "unknown")) for row in tail_json(ACTION_LOG))
    lines += ["# HELP llm_action_engine_audit_events Recent Action Engine audit events.", "# TYPE llm_action_engine_audit_events gauge"]
    lines.extend(f'llm_action_engine_audit_events{{action="{label(action)}",state="{label(state)}"}} {count}' for (action, state), count in sorted(actions.items()))

    events = Counter(row.get("event", "unknown") for row in tail_json(AUTONOMY_LOG))
    lines += ["# HELP llm_autonomy_audit_events Recent autonomy supervisor events.", "# TYPE llm_autonomy_audit_events gauge"]
    lines.extend(f'llm_autonomy_audit_events{{event="{label(event)}"}} {count}' for event, count in sorted(events.items()))

    lines += ["# HELP llm_control_proposals Pending controlled-change proposals.", "# TYPE llm_control_proposals gauge"]
    lines.extend(f'llm_control_proposals{{type="{label(kind)}",state="{label(state)}",risk="{label(risk)}"}} {count}' for (kind, state, risk), count in sorted(proposals().items()))

    deployment_count = len([name for name in os.listdir(DEPLOYMENTS) if name.endswith(".json")]) if os.path.isdir(DEPLOYMENTS) else 0
    lines += ["# HELP llm_deployment_records Number of deployment audit records.", "# TYPE llm_deployment_records gauge", f"llm_deployment_records {deployment_count}"]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/metrics", "/health"):
            self.send_error(404)
            return
        body = ("ok\n" if self.path == "/health" else metrics()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    host = os.environ.get("METRICS_HOST", "172.17.0.1")
    port = int(os.environ.get("METRICS_PORT", "9400"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
