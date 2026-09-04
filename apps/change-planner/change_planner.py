import json
import re
import uuid
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ACTION_ENGINE = "http://127.0.0.1:5200/v1/actions"
QWEN = "http://127.0.0.1:11434/v1/chat/completions"
app = FastAPI(title="LLM Server Change Planner")
ALLOWED_PATHS = ["/opt/llm-server/apps/router/app.py", "/opt/llm-server/apps/router/rules.yaml", "/opt/llm-server/apps/agent/", "/opt/llm-server/apps/dashboard/", "/opt/llm-server/services/", "/opt/llm-server/config/systemd/", "/opt/llm-server/deploy/"]


class ChangeRequest(BaseModel):
    request: str


@app.post("/v1/plans")
def create_plan(change: ChangeRequest):
    plan_id = f"plan-{uuid.uuid4().hex[:12]}"
    prompt = ("Create a JSON-only change plan for this local LLM server request. "
              "Fields: summary, affected_paths, dependencies, risks, rollback, tests. "
              "Never include shell commands or deployment approval. Paths must be chosen only from this inventory: " + json.dumps(ALLOWED_PATHS) + ". Request: " + change.request)
    try:
        body = json.dumps({"model": "qwen2.5:7b", "messages": [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": prompt}], "temperature": 0, "stream": False}).encode()
        with urlopen(Request(QWEN, data=body, headers={"Content-Type": "application/json"}, method="POST"), timeout=120) as response:
            content = json.loads(response.read())["choices"][0]["message"]["content"]
        proposal = json.loads(re.search(r"\{.*\}", content, re.S).group())
    except Exception as exc:
        raise HTTPException(502, f"planner model failed: {exc}") from exc
    invalid = [path for path in proposal.get("affected_paths", []) if not any(path.startswith(allowed) for allowed in ALLOWED_PATHS)]
    if invalid:
        proposal["affected_paths"] = [path for path in proposal.get("affected_paths", []) if path not in invalid]
    return {"id": plan_id, "state": "PROPOSED", "request": change.request, "plan": proposal, "validation": {"invalid_paths_removed": invalid}, "next": "Create staging only after explicit approval"}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "proposal-only"}
