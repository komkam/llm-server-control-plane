"""OpenAI-compatible HTTP facade for the proposal-only Mechanical Engineering Agent."""

import json
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from mechanical_agent import run_mechanical_agent

HOST = "127.0.0.1"
PORT = 5302
PUBLIC_MODEL_NAME = "mechanical-engineer"
MAX_REQUEST_BYTES = 1_000_000


def last_user_prompt(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: HTTPStatus, value: dict) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok", "mode": "proposal-only", "device_control": False})
        elif path == "/v1/models":
            self.send_json(HTTPStatus.OK, {"object": "list", "data": [{"id": PUBLIC_MODEL_NAME, "object": "model", "owned_by": "local"}]})
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
        try:
            answer = run_mechanical_agent(prompt)
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": f"mechanical agent failed: {exc}"})
            return
        self.send_json(HTTPStatus.OK, {
            "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()),
            "model": PUBLIC_MODEL_NAME,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
