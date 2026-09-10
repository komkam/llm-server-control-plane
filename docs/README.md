# Local LLM Server

## Request path

```text
Open WebUI (:3000) -> LLM Gateway (:5000) -> Ollama/Qwen (:11434)

```

Open WebUI is the only user-facing chat UI. The LLM Gateway is the single policy
boundary: it removes unsupported tool payloads, uses hard safety rules and a
local CPU-only embedding classifier to delegate system, electrical, and
mechanical requests to their proposal-only specialists, uses Qwen for general
requests, applies the language guard, and reports the chosen backend in each
answer. Ambiguous requests stay with Qwen.

Select `server-diagnostician` in Open WebUI for system diagnostics.  LLM Gateway
forwards that explicit model choice to the local LangGraph agent (`:5100`),
which can inspect services, hardware, Docker, logs, and endpoint health.

## Services

| Component | Runtime | Port | Purpose |
| --- | --- | --- | --- |
| Open WebUI | Docker Compose | 3000 | Chat UI and persistent user data |
| LLM Gateway | systemd (`llm-gateway.service`) | 5000 | Model selection and proxy |
| Embedding Classifier | systemd (`embedding-classifier.service`) | 5400 (loopback) | Read-only semantic intent routing |
| Ollama | systemd (`ollama.service`) | 11434 | Qwen inference |
| Electrical Engineering Agent | systemd (`electrical-engineer.service`) | 5301 (loopback) | Proposal-only electrical analysis |
| Dashboard | systemd (`dashboard.service`) | 7000 | Server status UI |
| Monitor | systemd (`monitor.service`) | — | Writes system metrics every 2 seconds |
| Diagnostic Agent | systemd (`agent.service`) | 5100 (loopback) | LangGraph tool-calling diagnostics |
| Autonomy Supervisor | systemd (`autonomy.service`) | — | Health checks, diagnosis, constrained restarts |

## Configuration ownership

- - `router/app.py`: backend URLs and backend-native model names.
- `agent/agent.py`: LangGraph workflow and diagnostic tools.
- `agent/agent_server.py`: loopback OpenAI-compatible facade for the agent.
- `autonomy.py`: constrained health supervisor; its service allowlist is the
  only restart authority.
- `compose.yaml`: Open WebUI and observability stack.
- `/etc/systemd/system/*.service`: process startup configuration.

## Operations

```bash
cd /opt/llm-server
docker compose ps
systemctl status embedding-classifier llm-gateway ollama monitor dashboard --no-pager
```

Recovery material is deliberately retained in `backups/` and
`FINAL-BEFORE.tar.gz`.  Do not store mutable application data outside
`open-webui/` and `data/`.

The autonomy supervisor waits for three consecutive failed checks (30-second
interval) before a restart, then applies a five-minute per-service cooldown.
Every failed check, diagnosis, recovery, and restart attempt is appended to
`logs/autonomy.jsonl`.
