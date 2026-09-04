# Local LLM Server

## Request path

```text
Open WebUI (:3000) -> Router (:5000) -> Ollama/Qwen (:11434)
                                      -> llama.cpp/Phi (:8082)
```

Open WebUI is the only user-facing chat UI.  The Router is the single policy
layer: it chooses `qwen-engineer` for technical requests and `phi-fast` for
simple requests, then translates those public names to backend-specific model
names.

Select `server-diagnostician` in Open WebUI for system diagnostics.  Router
forwards that explicit model choice to the local LangGraph agent (`:5100`),
which can inspect services, hardware, Docker, logs, and endpoint health.

## Services

| Component | Runtime | Port | Purpose |
| --- | --- | --- | --- |
| Open WebUI | Docker Compose | 3000 | Chat UI and persistent user data |
| Router | systemd (`router.service`) | 5000 | Model selection and proxy |
| Ollama | systemd (`ollama.service`) | 11434 | Qwen inference |
| llama.cpp | systemd (`llama-server.service`) | 8082 | Phi inference |
| Dashboard | systemd (`dashboard.service`) | 7000 | Server status UI |
| Monitor | systemd (`monitor.service`) | — | Writes system metrics every 2 seconds |
| Diagnostic Agent | systemd (`agent.service`) | 5100 (loopback) | LangGraph tool-calling diagnostics |
| Autonomy Supervisor | systemd (`autonomy.service`) | — | Health checks, diagnosis, constrained restarts |

## Configuration ownership

- `router/rules.yaml`: routing policy and public model names.
- `router/app.py`: backend URLs and backend-native model names.
- `agent/agent.py`: LangGraph workflow and diagnostic tools.
- `agent/agent_server.py`: loopback OpenAI-compatible facade for the agent.
- `autonomy.py`: constrained health supervisor; its service allowlist is the
  only restart authority.
- `compose.yaml`: Open WebUI only.
- `/etc/systemd/system/*.service`: process startup configuration.

## Operations

```bash
cd /opt/llm-server
docker compose ps
systemctl status router ollama llama-server monitor dashboard --no-pager
```

Recovery material is deliberately retained in `backups/` and
`FINAL-BEFORE.tar.gz`.  Do not store mutable application data outside
`open-webui/` and `data/`.

The autonomy supervisor waits for three consecutive failed checks (30-second
interval) before a restart, then applies a five-minute per-service cooldown.
Every failed check, diagnosis, recovery, and restart attempt is appended to
`logs/autonomy.jsonl`.
