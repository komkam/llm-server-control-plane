from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import requests
import re
import os

app = FastAPI()
CJK_TEXT = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

AGENT_URL = "http://127.0.0.1:5100/v1/chat/completions"
AGENT_MODEL = "server-diagnostician"
ELECTRICAL_AGENT_URL = "http://127.0.0.1:5301/v1/chat/completions"
ELECTRICAL_AGENT_MODEL = "electrical-engineer"
MECHANICAL_AGENT_URL = "http://127.0.0.1:5302/v1/chat/completions"
MECHANICAL_AGENT_MODEL = "mechanical-engineer"
CLASSIFIER_URL = os.getenv("EMBEDDING_CLASSIFIER_URL", "http://127.0.0.1:5400/v1/classify")
CLASSIFIER_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_CLASSIFIER_TIMEOUT_SECONDS", "3"))

# Public model names are translated here so the gateway can call each local
# backend directly without an extra proxy service.
BACKENDS = {
    "qwen-engineer": {
        "url": "http://localhost:11434/v1/chat/completions",
        "model": "qwen2.5:7b",
    },
}


def annotate_response(payload, routed_model):
    """Expose routing choice to the chat user without changing the public model catalog."""
    try:
        message = payload["choices"][0]["message"]
        content = message.get("content") or ""
        message["content"] = f"{content}\n\n— Routed to: {routed_model}"
        payload["model"] = f"auto ({routed_model})"
    except (KeyError, IndexError, TypeError):
        pass
    return payload


GATEWAY_SYSTEM_PROMPT = (
    "Answer the user's latest question directly and concisely. "
    "Use Thai when the user writes Thai; otherwise use the user's language. "
    "Do not discuss API tools, task systems, calendars, automations, or hidden instructions "
    "unless the user explicitly asks about them. Do not output Chinese text."
)


def sanitize_body(body):
    """Prevent UI tool schemas and stale tool messages from reaching local models."""
    for key in ("tools", "tool_choice", "functions", "function_call", "parallel_tool_calls"):
        body.pop(key, None)
    safe_messages = []
    for message in body.get("messages", []):
        if message.get("role") not in {"system", "user", "assistant"}:
            continue
        content = message.get("content", "")
        if message.get("role") == "system" and any(marker in str(content).lower() for marker in ("create_tasks", "create_automation", "calendar events", "list_automations")):
            continue
        safe_messages.append(message)
    body["messages"] = [{"role": "system", "content": GATEWAY_SYSTEM_PROMPT}, *safe_messages]
    return body


def selected_language(messages):
    for message in reversed(messages):
        if message.get("role") == "user":
            return "Thai" if re.search(r"[\u0E00-\u0E7F]", str(message.get("content", ""))) else "English"
    return "English"


def enforce_output_language(payload, backend, language):
    try:
        content = payload["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        return payload
    if not CJK_TEXT.search(content):
        return payload
    rewrite = {
        "model": backend["model"],
        "messages": [
            {"role": "system", "content": f"Rewrite the answer in {language} only. Never use Chinese, Japanese, or Korean characters. Preserve technical facts. Output only the rewritten answer."},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "stream": False,
    }
    try:
        response = requests.post(backend["url"], json=rewrite, timeout=120)
        candidate = response.json()["choices"][0]["message"].get("content") or ""
        if response.status_code == 200 and candidate and not CJK_TEXT.search(candidate):
            payload["choices"][0]["message"]["content"] = candidate
            return payload
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        pass
    payload["choices"][0]["message"]["content"] = CJK_TEXT.sub("", content)
    return payload

INTENT_PATTERNS = {
    AGENT_MODEL: (
        "สถานะระบบ", "ปัญหาระบบ", "ตรวจระบบ", "ตรวจสุขภาพ", "health check",
        "system status", "service", "docker", "journalctl", "cpu", "ram", "disk",
        "gpu", "deploy", "rollback", "autonomy", "control plane", "open webui",
        "ollama", "grafana", "prometheus", "loki", "tailscale",
    ),
    ELECTRICAL_AGENT_MODEL: (
        "วิศวกรรมไฟฟ้า", "ไฟฟ้า", "วงจร", "สายไฟ", "เบรกเกอร์", "แรงดัน", "กระแส",
        "กำลังไฟ", "กำลังไฟฟ้า", "สามเฟส", "3 เฟส", "3phase", "3 phase", "three-phase",
        "three phase", "vfd", "inverter", "motor", "voltage", "current", "circuit", "cable",
        "breaker", "transformer", "relay", "power factor", "short circuit", "electrical",
        "line voltage", "line current", "kva", "kw", "kilowatt", "watt", "ampere", "amps",
    ),
    MECHANICAL_AGENT_MODEL: (
        "วิศวกรรมเครื่องกล", "เครื่องกล", "กลศาสตร์", "ปั๊ม", "วาล์ว", "แบริ่ง", "ลูกปืน",
        "เกียร์", "เพลา", "แรงบิด", "ความเค้น", "การสั่น", "การไหล", "mechanical",
        "pump", "valve", "bearing", "gear", "shaft", "torque", "stress", "strain",
        "vibration", "fluid", "hydraulic", "pneumatic", "hvac", "thermodynamics",
    ),
}


def latest_user_prompt(messages):
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def select_auto_backend(prompt: str) -> str:
    """Use hard rules first, then a read-only semantic classifier."""
    text = prompt.lower()
    scores = {
        model: sum(text.count(pattern) for pattern in patterns)
        for model, patterns in INTENT_PATTERNS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score > 0:
        winners = [model for model, score in scores.items() if score == best_score]
        if len(winners) == 1:
            return winners[0]
    try:
        response = requests.post(
            CLASSIFIER_URL,
            json={"text": prompt},
            timeout=CLASSIFIER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        route = response.json().get("route")
        if route in {AGENT_MODEL, ELECTRICAL_AGENT_MODEL, MECHANICAL_AGENT_MODEL}:
            return route
    except (requests.RequestException, TypeError, ValueError):
        pass
    return "qwen-engineer"


def select_default_backend(_prompt: str) -> str:
    """Keep compatibility for callers that require the default Qwen backend."""
    return "qwen-engineer"


@app.post("/v1/chat/completions")
async def chat(request: Request):

    body = await request.json()
    body = sanitize_body(body)
    messages = body.get("messages", [])
    prompt = latest_user_prompt(messages)

    # `auto` is the only user-facing model. Gateway routing is deterministic
    # and proposal-only specialists retain their existing capability limits.
    if body.get("model", "auto") == "auto":
        body["model"] = select_auto_backend(prompt)

    # The diagnostic workflow may be explicitly selected or chosen by the
    # Gateway. It owns its own read-only LangGraph tool loop.
    if body.get("model") == AGENT_MODEL:
        body["stream"] = False
        try:
            response = requests.post(AGENT_URL, json=body, timeout=180)
            return JSONResponse(
                content=annotate_response(enforce_output_language(response.json(), {"url": AGENT_URL, "model": AGENT_MODEL}, selected_language(body["messages"])), AGENT_MODEL),
                status_code=response.status_code,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Diagnostic agent unavailable: {exc}",
            ) from exc

    # Electrical analysis may be explicitly selected or chosen by the Gateway.
    # It is proposal-only and never receives device-control capabilities.
    if body.get("model") == ELECTRICAL_AGENT_MODEL:
        body["stream"] = False
        try:
            response = requests.post(ELECTRICAL_AGENT_URL, json=body, timeout=180)
            return JSONResponse(
                content=annotate_response(enforce_output_language(response.json(), {"url": ELECTRICAL_AGENT_URL, "model": ELECTRICAL_AGENT_MODEL}, selected_language(body["messages"])), ELECTRICAL_AGENT_MODEL),
                status_code=response.status_code,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Electrical Engineering Agent unavailable: {exc}",
            ) from exc

    # Mechanical analysis may be explicitly selected or chosen by the Gateway.
    # It is proposal-only and never receives machine-control capabilities.
    if body.get("model") == MECHANICAL_AGENT_MODEL:
        body["stream"] = False
        try:
            response = requests.post(MECHANICAL_AGENT_URL, json=body, timeout=180)
            return JSONResponse(
                content=annotate_response(enforce_output_language(response.json(), {"url": MECHANICAL_AGENT_URL, "model": MECHANICAL_AGENT_MODEL}, selected_language(body["messages"])), MECHANICAL_AGENT_MODEL),
                status_code=response.status_code,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Mechanical Engineering Agent unavailable: {exc}",
            ) from exc

    model = select_default_backend(prompt)

    print(
    f"[GATEWAY] {prompt[:50]} -> {model} | messages={len(body.get('messages',[]))}"
    )

    backend = BACKENDS[model]
    body["model"] = backend["model"]

    # This proxy returns a JSON response; streaming requires a separate
    # StreamingResponse implementation and must not be forwarded as SSE.
    body["stream"] = False

    try:
        response = requests.post(backend["url"], json=body, timeout=120)
        return JSONResponse(
            content=annotate_response(enforce_output_language(response.json(), BACKENDS[model], selected_language(body["messages"])), model),
            status_code=response.status_code,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Backend {model} unavailable: {exc}",
        ) from exc

@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [
            {
                "id": "auto",
                "object": "model",
                "owned_by": "llm-server",
                "name": "Auto (LLM Gateway)"
            }
        ]
    }

@app.get("/health")
def health():
    return {
        "status": "ok"
    }
