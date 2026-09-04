from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

import os
import json
import hmac
import hashlib
import subprocess
from datetime import datetime, timezone
from collections import deque
from urllib.request import urlopen, Request as URLRequest
from urllib.error import URLError
from urllib.parse import parse_qs
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
CONTROL_AUDIT_LOG = os.path.join(BASE_DIR, "apps", "dashboard", "data", "control.jsonl")
CONTROLLED_SERVICES = {"router", "agent", "dashboard", "ollama", "llama-server", "monitor", "autonomy"}
CONTROLLED_ACTIONS = {"restart_service", "health_check", "create_backup", "verify_deployment"}
AUTH_FILE = os.path.join(BASE_DIR, "apps", "dashboard", "data", "auth.json")


class ControlRequest(BaseModel):
    action: str
    service: str | None = None


def load_auth_config():
    with open(AUTH_FILE, "r") as handle:
        return json.load(handle)


AUTH_CONFIG = load_auth_config()


def credentials_valid(username: str, password: str) -> bool:
    try:
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(AUTH_CONFIG["salt"]), n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(username, AUTH_CONFIG["username"]) and hmac.compare_digest(derived, AUTH_CONFIG["password_hash"])
    except (KeyError, ValueError):
        return False


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


@app.middleware("http")
async def disable_dashboard_cache(request: Request, call_next):
    public_paths = {"/login", "/api/health"}
    if request.url.path not in public_paths and not request.url.path.startswith("/static/") and not request.session.get("authenticated"):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "login required"})
        return RedirectResponse(url="/login", status_code=303)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(SessionMiddleware, secret_key=AUTH_CONFIG["session_secret"], session_cookie="llm_dashboard_session", same_site="strict", https_only=True, max_age=60 * 60 * 12)



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


@app.get("/login")
async def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": False})


@app.post("/login")
async def login(request: Request):
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    username = values.get("username", [""])[0].strip()
    password = values.get("password", [""])[0]
    if not credentials_valid(username, password):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": True}, status_code=401)
    request.session.clear()
    request.session["authenticated"] = True
    request.session["username"] = username
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)



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


def action_engine_request(payload):
    try:
        response = URLRequest("http://127.0.0.1:5200/v1/actions", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(response, timeout=90) as result:
            return json.loads(result.read())
    except (URLError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"action engine unavailable: {exc}") from exc


@app.get("/api/control/actions")
def control_action_history():
    try:
        with urlopen("http://127.0.0.1:5200/v1/actions?limit=60", timeout=5) as result:
            return JSONResponse(content=json.loads(result.read()))
    except (URLError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"action engine unavailable: {exc}") from exc


@app.post("/api/control")
def control(request: ControlRequest):
    if request.action not in CONTROLLED_ACTIONS:
        raise HTTPException(status_code=400, detail="action is not controllable")
    if request.action in {"restart_service", "health_check"} and request.service not in CONTROLLED_SERVICES:
        raise HTTPException(status_code=400, detail="service is not controllable")
    payload = json.dumps({"action": request.action, "target": request.service, "reason": "dashboard control panel"}).encode()
    data = action_engine_request(payload)
    audit_control(request.action, request.service or "platform", data["state"] == "SUCCESS", data.get("detail", ""))
    return data


@app.post("/api/control/restart")
def restart_service(request: ControlRequest):
    request.action = "restart_service"
    return control(request)





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
