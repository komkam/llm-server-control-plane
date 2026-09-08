from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import requests
import re

app = FastAPI()
CJK_TEXT = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

AGENT_URL = "http://127.0.0.1:5100/v1/chat/completions"
AGENT_MODEL = "server-diagnostician"
ELECTRICAL_AGENT_URL = "http://127.0.0.1:5301/v1/chat/completions"
ELECTRICAL_AGENT_MODEL = "electrical-engineer"
MECHANICAL_AGENT_URL = "http://127.0.0.1:5302/v1/chat/completions"
MECHANICAL_AGENT_MODEL = "mechanical-engineer"

# Public model names are translated here so the router can call each local
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


ROUTER_SYSTEM_PROMPT = (
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
    body["messages"] = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}, *safe_messages]
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

def select_model(_prompt: str) -> str:
    """Route normal chat directly to the primary engineering model."""
    return "qwen-engineer"


@app.post("/v1/chat/completions")
async def chat(request: Request):

    body = await request.json()
    body = sanitize_body(body)

    # The diagnostic workflow is an explicit model choice.  It must not pass
    # through the classifier because it owns its own LangGraph tool loop.
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

    # Electrical analysis is an explicit specialist route. It is proposal-only
    # and never receives Action Engine or device-control capabilities.
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

    # Mechanical analysis is an explicit specialist route. It is proposal-only
    # and never receives Action Engine or machine-control capabilities.
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

    messages = body.get("messages", [])

    prompt = ""

    for msg in reversed(messages):

        if msg.get("role") == "user":

            prompt = msg.get("content", "")

            break


    if len(prompt) > 1500:

        prompt_for_router = prompt[-1500:]

    else:

        prompt_for_router = prompt



    model = select_model(prompt_for_router)

    print(
    f"[ROUTER] {prompt[:50]} -> {model} | messages={len(body.get('messages',[]))}"
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
                "name": "Auto (Smart Router)"
            }
        ]
    }

@app.get("/health")
def health():
    return {
        "status": "ok"
    }
