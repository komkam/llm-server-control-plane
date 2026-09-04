"""Constrained Action Engine for the local LLM server."""

import json
import os
import subprocess
import time
import uuid
import re
from datetime import datetime, timezone
from threading import Lock
from collections import deque
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

BASE_DIR = "/opt/llm-server"
DATA_DIR = f"{BASE_DIR}/apps/action-engine/data"
AUDIT_LOG = f"{DATA_DIR}/actions.jsonl"
SERVICES = {
    "router": "http://127.0.0.1:5000/health",
    "agent": "http://127.0.0.1:5100/health",
    "dashboard": "http://100.69.21.124:7000/api/health",
    "ollama": "http://127.0.0.1:11434/api/tags",
    "llama-server": "http://127.0.0.1:8082/health",
    "open-webui": "http://127.0.0.1:3000/",
    "monitor": None,
    "autonomy": None,
}
NON_SYSTEMD_SERVICES = {"open-webui"}
LOCK = Lock()
app = FastAPI(title="LLM Server Action Engine")


class ActionRequest(BaseModel):
    action: str
    target: str | None = None
    reason: str = "manual request"
    release_id: str | None = None
    approver: str | None = None


def now():
    return datetime.now(timezone.utc).isoformat()


def audit(**entry):
    os.makedirs(DATA_DIR, exist_ok=True)
    entry["time"] = now()
    with open(AUDIT_LOG, "a") as handle:
        handle.write(json.dumps(entry) + "\n")


def recent_actions(limit: int):
    try:
        with open(AUDIT_LOG, "r") as handle:
            rows = deque(handle, maxlen=limit)
        return [json.loads(row) for row in rows if row.strip()]
    except OSError:
        return []


def healthy(service):
    if service not in NON_SYSTEMD_SERVICES:
        active = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, timeout=10)
        if active.stdout.strip() != "active":
            return False, active.stdout.strip() or active.stderr.strip()
    endpoint = SERVICES[service]
    if endpoint is None:
        return True, "systemd active"
    try:
        with urlopen(endpoint, timeout=10) as response:
            return 200 <= response.status < 300, f"HTTP {response.status}"
    except OSError as exc:
        return False, str(exc)


def run(command, timeout):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


def releases():
    ok, output = run(["/usr/bin/sudo", "-n", f"{BASE_DIR}/scripts/release.sh", "list"], 30)
    if not ok:
        raise HTTPException(502, f"release inventory unavailable: {output}")
    return [{"id": p[0], "status": p[1], "checksum": p[2], "manifest": p[3], "approval_id": p[4]} for line in output.splitlines() if len((p := line.split("\t"))) == 5]


def execute(request: ActionRequest):
    action_id = uuid.uuid4().hex
    if request.action not in {"restart_service", "health_check", "create_backup", "verify_deployment", "create_release", "approve_release", "deploy_release", "rollback_release"}:
        raise HTTPException(400, "action is not allowed")
    if request.action in {"restart_service", "health_check"} and request.target not in SERVICES:
        raise HTTPException(400, "target is not allowed")
    if request.action == "restart_service" and request.target in NON_SYSTEMD_SERVICES:
        raise HTTPException(400, "target supports health checks only")
    if request.action == "approve_release":
        if not request.release_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", request.release_id):
            raise HTTPException(400, "invalid release id")
        if not request.approver or not request.reason or "\n" in request.reason or len(request.reason) > 240:
            raise HTTPException(400, "approver and a short single-line reason are required")
    with LOCK:
        audit(id=action_id, state="REQUESTED", action=request.action, target=request.target, reason=request.reason)
        if request.action == "health_check":
            ok, detail = healthy(request.target)
            audit(id=action_id, state="SUCCESS" if ok else "FAILED", detail=detail)
            return {"id": action_id, "state": "SUCCESS" if ok else "FAILED", "detail": detail}
        audit(id=action_id, state="PRECHECK")
        if request.action == "restart_service":
            ok, detail = run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "restart", request.target], 60)
            if not ok:
                audit(id=action_id, state="FAILED", detail=detail)
                return {"id": action_id, "state": "FAILED", "detail": detail}
            audit(id=action_id, state="VERIFYING")
            for _ in range(3):
                time.sleep(5)
                ok, detail = healthy(request.target)
                if ok:
                    audit(id=action_id, state="SUCCESS", detail=detail)
                    return {"id": action_id, "state": "SUCCESS", "detail": detail}
            audit(id=action_id, state="ESCALATED", detail=detail)
            return {"id": action_id, "state": "ESCALATED", "detail": detail}
        if request.action in {"create_release", "approve_release", "deploy_release", "rollback_release"}:
            command = ["/usr/bin/sudo", "-n", f"{BASE_DIR}/scripts/release.sh", request.action.removesuffix("_release")]
            if request.action == "approve_release":
                command.extend([request.release_id, request.approver, request.reason])
            if request.action == "deploy_release":
                if not request.release_id:
                    raise HTTPException(400, "release_id is required")
                command.append(request.release_id)
            ok, detail = run(command, 300)
        else:
            script = "backup.sh" if request.action == "create_backup" else "verify.sh"
            ok, detail = run(["/usr/bin/sudo", "-n", f"{BASE_DIR}/scripts/{script}"], 180)
        audit(id=action_id, state="SUCCESS" if ok else "FAILED", detail=detail)
        return {"id": action_id, "state": "SUCCESS" if ok else "FAILED", "detail": detail}


@app.get("/health")
def health():
    return {"status": "ok", "actions": ["restart_service", "health_check", "create_backup", "verify_deployment", "create_release", "approve_release", "deploy_release", "rollback_release"]}


@app.get("/v1/releases")
def release_inventory():
    return {"releases": releases()}


@app.get("/v1/actions")
def action_history(limit: int = 40):
    return {"actions": recent_actions(max(1, min(limit, 200)))}


@app.post("/v1/actions")
def action(request: ActionRequest):
    return execute(request)
