from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import yaml
import requests
import re
import copy

app = FastAPI()
CJK_TEXT = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

with open("rules.yaml") as f:
    rules = yaml.safe_load(f)

PHI_CLASSIFIER_URL = "http://localhost:8082/v1/chat/completions"
AGENT_URL = "http://127.0.0.1:5100/v1/chat/completions"
AGENT_MODEL = "server-diagnostician"

# Public model names are translated here so the router can call each local
# backend directly without an extra proxy service.
BACKENDS = {
    "qwen-engineer": {
        "url": "http://localhost:11434/v1/chat/completions",
        "model": "qwen2.5:7b",
    },
    "phi-fast": {
        "url": "http://localhost:8082/v1/chat/completions",
        "model": "Phi-3-mini",
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

def classify_with_phi(prompt):

    prompt = prompt[-2000:]

    payload = {

        "model": "phi-fast",

        "messages": [

            {
                "role": "system",
                "content": """
You are a strict task routing classifier.

Your ONLY job is to classify the user's task.

Return exactly ONE word:

HARD

or

EASY

Never return anything else.

HARD:
- coding
- debugging
- engineering
- calculations
- Linux
- Docker
- servers
- networking
- CPU/GPU/RAM troubleshooting
- hardware diagnostics
- PLC
- VFD
- electrical systems
- configuration
- system administration
- performance analysis
- troubleshooting
- technical design
- multi-step reasoning

EASY:
- greetings
- casual conversation
- simple translation
- simple definitions
- simple factual questions
- short summaries

CLASSIFICATION:
"""
            },

            {
                "role": "user",
                "content": prompt
            }

        ],

        "temperature": 0,

        "max_tokens": 5
    }

    response = requests.post(
        PHI_CLASSIFIER_URL,
        json=payload,
        timeout=10
    )

    result = response.json()

    decision = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    decision = decision.strip().upper()

    print(f"[CLASSIFIER RAW] {decision}")

    if decision == "HARD":
        return "HARD"

    if decision == "EASY":
        return "EASY"

    # FAIL-SAFE
    print(
        f"[CLASSIFIER INVALID] {decision} -> FAILSAFE HARD"
    )

    return "HARD"

def trim_context(body, model):

    # Phi context 4k จำกัดมาก
    if model == rules["light_model"]:

        messages = body.get("messages", [])

        system = []
        user = None

        for msg in messages:

            if msg.get("role") == "system":
                system.append(msg)


        for msg in reversed(messages):

            if msg.get("role") == "user":
                user = msg
                break


        new_messages = system

        if user:
            new_messages.append(user)


        body["messages"] = new_messages


    return body

def keyword_route(prompt):

    keywords = rules.get("heavy_keywords", [])
    thai_keywords = rules.get("heavy_keywords_th", [])

    prompt_lower = prompt.lower()

    matched = []

    for keyword in keywords:

        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"

        if re.search(pattern, prompt_lower):
            matched.append(keyword)

    if matched:

        print(
            f"[KEYWORD ROUTE] HARD keywords={matched}"
        )

        return "HARD"

    matched_thai = [keyword for keyword in thai_keywords if keyword in prompt]
    if matched_thai:
        print(f"[KEYWORD ROUTE] HARD Thai keywords={matched_thai}")
        return "HARD"

    return None

def select_model(prompt):

    try:

        # Layer 1: deterministic keyword routing
        level = keyword_route(prompt)

        if level == "HARD":

            return rules["heavy_model"]

        # Layer 2: LLM classifier
        level = classify_with_phi(prompt)

        print(
            f"[CLASSIFIER] {level}"
        )

        if level == "HARD":

            return rules["heavy_model"]

        return rules["light_model"]

    except Exception as e:

        print(
            f"[ROUTER ERROR] {e}"
        )

        # Fail-safe:
        # Technical routing failures should prefer the
        # stronger model rather than silently downgrading.
        return rules["heavy_model"]

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

    messages = body.get("messages", [])

    prompt = ""

    for msg in reversed(messages):

        if msg.get("role") == "user":

            prompt = msg.get("content", "")

            break


# จำกัดข้อความที่ส่งให้ Phi classifier
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
    body = trim_context(body, model)

    # This proxy returns a JSON response; streaming requires a separate
    # StreamingResponse implementation and must not be forwarded as SSE.
    body["stream"] = False

    try:
        response = requests.post(backend["url"], json=body, timeout=120)
        if response.status_code >= 500:
            fallback_model = rules["light_model"] if model == rules["heavy_model"] else rules["heavy_model"]
            fallback = BACKENDS[fallback_model]
            fallback_body = trim_context(copy.deepcopy(body), fallback_model)
            fallback_body["model"] = fallback["model"]
            print(f"[ROUTER FALLBACK] {model} -> {fallback_model} ({response.status_code})")
            response = requests.post(fallback["url"], json=fallback_body, timeout=120)
            model = fallback_model
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
