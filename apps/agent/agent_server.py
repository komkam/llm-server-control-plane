"""Small OpenAI-compatible HTTP facade for the LangGraph diagnostic agent."""

import json
import os
import time
import uuid
from threading import Lock
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent import LANGUAGE_POLICY_VERSION, run_agent


HOST = "127.0.0.1"
PORT = 5100
PUBLIC_MODEL_NAME = "server-diagnostician"
MAX_REQUEST_BYTES = 1_000_000
METRICS_LOCK = Lock()
METRICS = {"requests_total": 0, "requests_failed": 0, "latency_ms_total": 0.0, "last_latency_ms": None}
METRICS_FILE = "/opt/llm-server/apps/agent/data/metrics.json"


def load_metrics():
    try:
        with open(METRICS_FILE, "r") as handle:
            stored = json.load(handle)
        METRICS.update({key: stored[key] for key in METRICS if key in stored})
    except (OSError, ValueError, TypeError):
        pass


def save_metrics():
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    temporary = f"{METRICS_FILE}.tmp"
    with open(temporary, "w") as handle:
        json.dump(METRICS, handle)
    os.replace(temporary, METRICS_FILE)


def record_request(latency_ms, failed=False):
    with METRICS_LOCK:
        METRICS["requests_total"] += 1
        METRICS["requests_failed"] += int(failed)
        METRICS["latency_ms_total"] += latency_ms
        METRICS["last_latency_ms"] = round(latency_ms, 2)
        save_metrics()


def public_metrics():
    with METRICS_LOCK:
        count = METRICS["requests_total"]
        return {**METRICS, "average_latency_ms": round(METRICS["latency_ms_total"] / count, 2) if count else None}


def last_user_prompt(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
    return ""


class AgentHandler(BaseHTTPRequestHandler):
    def send_json(self, status: HTTPStatus, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {
                "status": "ok",
                "language_policy_version": LANGUAGE_POLICY_VERSION,
            })
        elif path == "/v1/models":
            self.send_json(HTTPStatus.OK, {"object": "list", "data": [{
                "id": PUBLIC_MODEL_NAME, "object": "model", "owned_by": "local",
            }]})
        elif path == "/metrics":
            self.send_json(HTTPStatus.OK, public_metrics())
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/v1/chat/completions":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(length))
            prompt = last_user_prompt(body.get("messages", []))
            if not prompt:
                raise ValueError("a user message is required")
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        started = time.perf_counter()
        try:
            answer = run_agent(prompt)
        except Exception as exc:
            record_request((time.perf_counter() - started) * 1000, failed=True)
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": f"diagnostic agent failed: {exc}"})
            return

        record_request((time.perf_counter() - started) * 1000)

        self.send_json(HTTPStatus.OK, {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": PUBLIC_MODEL_NAME,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    def log_message(self, format: str, *args: object) -> None:
        print(f"[agent-api] {self.address_string()} {format % args}")


if __name__ == "__main__":
    load_metrics()
    ThreadingHTTPServer((HOST, PORT), AgentHandler).serve_forever()
