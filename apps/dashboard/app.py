from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import os
import json
import hmac
import subprocess
from datetime import datetime, timezone
from collections import deque
from urllib.request import urlopen, Request as URLRequest
from urllib.error import URLError
from pydantic import BaseModel


BASE_DIR = "/opt/llm-server"

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

STATE_FILE = os.path.join(
    DATA_DIR,
    "state.json"
)

HISTORY_FILE = os.path.join(
    DATA_DIR,
    "history.json"
)

AUTONOMY_STATE_FILE = os.path.join(DATA_DIR, "autonomy-state.json")
AUTONOMY_AUDIT_LOG = os.path.join(BASE_DIR, "logs", "autonomy.jsonl")
CONTROL_AUDIT_LOG = os.path.join(BASE_DIR, "dashboard", "data", "control.jsonl")
CONTROLLED_SERVICES = {"router", "agent", "dashboard", "ollama", "llama-server", "monitor", "autonomy"}


class RestartRequest(BaseModel):
    service: str


app = FastAPI(
    title="AI Server Dashboard"
)


app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static"
)


templates = Jinja2Templates(
    directory="templates"
)



def read_json(path, default):

    try:

        with open(
            path,
            "r"
        ) as f:

            return json.load(f)


    except Exception:

        return default


def read_recent_jsonl(path, limit=20):
    """Read a bounded tail of the supervisor audit log without loading it all."""
    try:
        with open(path, "r") as handle:
            lines = deque(handle, maxlen=limit)
        return [json.loads(line) for line in lines if line.strip()]
    except Exception:
        return []


def read_agent_metrics():
    try:
        with urlopen("http://127.0.0.1:5100/metrics", timeout=2) as response:
            return json.loads(response.read())
    except Exception:
        return {"available": False}


INCIDENT_EVENTS = {"health_check_failed", "recovered", "restart_attempted", "restart_suppressed_circuit_breaker", "restart_requires_approval"}


def incidents(service=None, limit=100):
    events = [event for event in read_recent_jsonl(AUTONOMY_AUDIT_LOG, 1000) if event.get("event") in INCIDENT_EVENTS]
    if service:
        events = [event for event in events if event.get("service") == service]
    return events[-limit:]


def audit_control(action: str, service: str, success: bool, detail: str) -> None:
    entry = {"time": datetime.now(timezone.utc).isoformat(), "action": action, "service": service, "success": success, "detail": detail}
    with open(CONTROL_AUDIT_LOG, "a") as handle:
        handle.write(json.dumps(entry) + "\n")



@app.get("/")
async def dashboard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

@app.get("/api/system")
def api_system():

    data = read_json(
        STATE_FILE,
        {}
    )

    return JSONResponse(
        content=data
    )



@app.get("/api/history")
def api_history():

    data = read_json(
        HISTORY_FILE,
        []
    )

    return JSONResponse(
        content=data
    )



@app.get("/api/services")
def api_services():

    data = read_json(
        STATE_FILE,
        {}
    )

    return JSONResponse(content=data.get("services", []))


@app.get("/api/overview")
def api_overview():
    """Single operational snapshot for the dashboard refresh loop."""
    return JSONResponse(content={
        "system": read_json(STATE_FILE, {}),
        "history": read_json(HISTORY_FILE, [])[-180:],
        "autonomy": read_json(AUTONOMY_STATE_FILE, {"services": {}}),
        "autonomy_events": read_recent_jsonl(AUTONOMY_AUDIT_LOG),
        "agent_metrics": read_agent_metrics(),
    })


@app.get("/api/incidents")
def api_incidents(service: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500)):
    events = incidents(service, limit)
    summary = {event: 0 for event in INCIDENT_EVENTS}
    for item in events:
        summary[item["event"]] += 1
    return {"events": events, "summary": summary, "service": service}


@app.post("/api/control/restart")
def restart_service(request: RestartRequest):
    if request.service not in CONTROLLED_SERVICES:
        raise HTTPException(status_code=400, detail="service is not controllable")
    payload = json.dumps({"action": "restart_service", "target": request.service, "reason": "dashboard control panel"}).encode()
    try:
        response = URLRequest("http://127.0.0.1:5200/v1/actions", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(response, timeout=90) as result:
            data = json.loads(result.read())
    except (URLError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"action engine unavailable: {exc}") from exc
    audit_control("restart", request.service, data["state"] == "SUCCESS", data.get("detail", ""))
    return data





@app.get("/api/health")
def api_health():

    return {

        "status": "ok"

    }

@app.exception_handler(
    Exception
)
async def global_exception_handler(
    request: Request,
    exc: Exception
):

    return JSONResponse(

        status_code=500,

        content={

            "error": str(exc)

        }

    )



def get_app_info():

    return {

        "name": "AI SERVER DASHBOARD",

        "version": "1.0"

    }



@app.get("/api/info")
def api_info():

    return get_app_info()

if __name__ == "__main__":

    import uvicorn


    uvicorn.run(

        "app:app",

        host=os.environ.get("DASHBOARD_HOST", "127.0.0.1"),

        port=7000,

        reload=False

    )
