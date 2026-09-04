"""Constrained autonomous supervisor for the local LLM server.

It can observe all approved services and restart only those exact service
names after repeated health-check failures.  It cannot execute arbitrary
commands, modify models, packages, or application data.
"""

import json
import os
import subprocess
import tempfile
import grp
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen


BASE_DIR = "/opt/llm-server"
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
STATE_FILE = os.path.join(DATA_DIR, "autonomy-state.json")
AUDIT_LOG = os.path.join(LOG_DIR, "autonomy.jsonl")

CHECK_INTERVAL_SECONDS = 30
FAILURES_BEFORE_RESTART = 3
RESTART_COOLDOWN_SECONDS = 300
MAX_RESTARTS_PER_HOUR = 3
RESTART_WINDOW_SECONDS = 3600
POST_RESTART_DELAY_SECONDS = 5
POST_RESTART_ATTEMPTS = 3
HTTP_TIMEOUT_SECONDS = 10
ACTION_MODE = os.environ.get("AUTONOMY_ACTION_MODE", "observe").lower()

# This allowlist is the complete authority of the supervisor.  Do not accept
# service names from a request, model response, environment variable, or file.
SERVICES = {
    "router": "http://127.0.0.1:5000/health",
    "agent": "http://127.0.0.1:5100/health",
    "dashboard": "http://100.69.21.124:7000/api/health",
    "ollama": "http://127.0.0.1:11434/api/tags",
    "llama-server": "http://127.0.0.1:8082/health",
    "monitor": None,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(dir=directory, prefix=".tmp-autonomy-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2)
        os.chmod(temporary_path, 0o640)
        os.chown(temporary_path, -1, grp.getgrnam("dashboard-agent").gr_gid)
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def load_state() -> dict:
    try:
        with open(STATE_FILE, "r") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"services": {}}


def audit(event: str, **details: object) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    entry = {"time": now(), "event": event, **details}
    with open(AUDIT_LOG, "a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.chmod(AUDIT_LOG, 0o640)
    os.chown(AUDIT_LOG, -1, grp.getgrnam("dashboard-agent").gr_gid)


def systemd_is_active(service: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["systemctl", "is-active", service],
        capture_output=True,
        text=True,
        timeout=10,
    )
    status = result.stdout.strip() or result.stderr.strip() or "unknown"
    return status == "active", status


def endpoint_is_healthy(url: str) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return True, f"HTTP {response.status}"
            return False, f"HTTP {response.status}"
    except (URLError, TimeoutError, OSError) as exc:
        return False, str(exc)


def check_service(service: str) -> tuple[bool, str]:
    active, detail = systemd_is_active(service)
    if not active:
        return False, f"systemd: {detail}"

    endpoint = SERVICES[service]
    if endpoint is None:
        return True, "systemd: active"
    return endpoint_is_healthy(endpoint)


def diagnose(service: str, failure: str) -> str | None:
    """Ask the restricted diagnostic agent for facts; it has no restart authority."""
    payload = {
        "model": "server-diagnostician",
        "messages": [{
            "role": "user",
            "content": (
                f"Autonomous health check detected a failure in {service}: {failure}. "
                "Diagnose the likely cause using relevant read-only tools. "
                "Do not recommend or execute destructive actions."
            ),
        }],
        "stream": False,
    }
    try:
        request = Request(
            "http://127.0.0.1:5100/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            data = json.loads(response.read())
        return data["choices"][0]["message"].get("content", "")[:4000]
    except Exception as exc:
        return f"diagnosis unavailable: {exc}"


def restart_allowed_service(service: str) -> tuple[bool, str]:
    if service not in SERVICES:
        raise ValueError(f"service is not allowlisted: {service}")
    payload = json.dumps({"action": "restart_service", "target": service, "reason": "autonomy health check"}).encode()
    request = Request("http://127.0.0.1:5200/v1/actions", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read())
    except Exception as exc:
        return False, f"action engine unavailable: {exc}"
    return result.get("state") == "SUCCESS", result.get("detail", "no detail")


def restarts_in_window(record: dict, current_time: float) -> int:
    history = record.setdefault("restart_history", [])
    record["restart_history"] = [
        stamp for stamp in history if current_time - stamp < RESTART_WINDOW_SECONDS
    ]
    return len(record["restart_history"])


def supervise_once(state: dict | None = None) -> dict:
    state = state or load_state()
    state["mode"] = ACTION_MODE
    service_state = state.setdefault("services", {})
    current_time = time.time()

    for service in SERVICES:
        record = service_state.setdefault(
            service, {"failures": 0, "last_restart": 0, "restart_history": []}
        )
        healthy, detail = check_service(service)
        record["last_check"] = now()
        record["last_detail"] = detail

        if healthy:
            if record["failures"]:
                audit("recovered", service=service, detail=detail)
            record["failures"] = 0
            continue

        record["failures"] += 1
        audit("health_check_failed", service=service, detail=detail, failures=record["failures"])

        eligible = record["failures"] >= FAILURES_BEFORE_RESTART
        cooling_down = current_time - record.get("last_restart", 0) < RESTART_COOLDOWN_SECONDS
        if not eligible or cooling_down:
            continue

        if restarts_in_window(record, current_time) >= MAX_RESTARTS_PER_HOUR:
            audit(
                "restart_suppressed_circuit_breaker",
                service=service,
                failures=record["failures"],
                restarts_last_hour=len(record["restart_history"]),
            )
            continue

        if ACTION_MODE != "auto":
            audit(
                "restart_requires_approval",
                service=service,
                mode=ACTION_MODE,
                failure=detail,
            )
            continue

        diagnosis = diagnose(service, detail)
        success, restart_detail = restart_allowed_service(service)
        record["last_restart"] = current_time
        record.setdefault("restart_history", []).append(current_time)
        record["failures"] = 0
        audit(
            "restart_attempted",
            service=service,
            success=success,
            detail=restart_detail,
            diagnosis=diagnosis,
        )

    atomic_write(STATE_FILE, state)
    return state


def run() -> None:
    audit("supervisor_started", services=list(SERVICES), mode=ACTION_MODE)
    while True:
        try:
            supervise_once()
        except Exception as exc:
            audit("supervisor_error", error=str(exc))
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
