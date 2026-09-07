# LLM Server Control Plane

A private, Tailscale-accessible local LLM platform with controlled operations,
observability, and an approval-gated deployment workflow.

## Current architecture

```text
Open WebUI
  -> Semantic Router
     -> Ollama / Qwen
     -> llama.cpp / Phi-3

Control Plane
  -> Diagnostic Agent
  -> Autonomy Supervisor
  -> Action Engine
  -> Change Planner / Candidate Builder
  -> Policy, Approval, Deployment and Rollback

Observability
  -> Prometheus -> Grafana
  -> Loki, Tempo, OpenTelemetry Collector, Alloy
  -> node-exporter, GPU exporter, Docker exporter, Falco
```

## Private access

Services are intended for a private tailnet. Tailscale Serve terminates HTTPS:

| Service | Address |
| --- | --- |
| Grafana monitoring | `https://llm-server.tail7732db.ts.net:8443/` |
| Control Panel | `https://llm-server.tail7732db.ts.net:8444/` |
| Open WebUI | Tailscale Serve root route |

Do not commit passwords, API keys, Tailscale auth keys, or backup credentials.

## Runtime behavior

- The semantic router selects the local model automatically and reports the
  selected model with responses.
- A response-language guard prevents unsupported CJK output from reaching Open
  WebUI when the requested response language does not allow it.
- The Autonomy Supervisor is in `auto` mode only for explicit, bounded Action
  Engine primitives. It has no arbitrary-shell capability.
- The Action Engine allowlists service targets and actions, enforces timeouts,
  and writes audit records.

## Controlled change lifecycle

```text
observe -> propose -> candidate -> policy/security checks -> approval
        -> deploy -> verify -> success | rollback
```

The planner is proposal-only. Deployment remains approval-gated. Candidate
building performs syntax checks, policy/risk evaluation, Gitleaks, and Trivy
scans before a candidate can be approved.

## Observability

Prometheus scrapes every 5 seconds. Grafana refreshes the control-plane
dashboard every 5 seconds and tracks:

- 12 core services, including the control-plane, GPU, and Docker exporters;
- 8 Observability containers;
- Open WebUI container availability;
- CPU, memory, disk, GPU/VRAM, and container CPU;
- proposal and deployment evidence.

Loki retains logs for 14 days. Prometheus retains time series for 30 days or
24 GB, whichever limit is reached first.

## Useful operational checks

```bash
systemctl is-active observability.service
curl http://127.0.0.1:9090/-/ready
curl http://127.0.0.1:3100/api/health
docker compose -f deploy/observability.compose.yaml ps
```

## Backup and secrets

Local release snapshots are created by the deployment pipeline. Restic, SOPS,
and age configuration are present, but offsite backup requires a separately
configured repository and credentials. Keep encrypted secrets outside Git and
use `config/secrets/README.md` as the local setup guide.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/` | Router, agent, action engine, and Control Panel application code |
| `services/` | Supervisor and read-only Prometheus exporters |
| `deploy/` | Docker Compose definitions and image-update assets |
| `config/` | Systemd, Observability, security, backup, and policy configuration |
| `scripts/` | Candidate, release, verification, backup, and security workflows |
| `docs/` | Operational and architecture documentation |

## Remaining external setup

- Configure a Restic offsite repository (S3, B2, NAS, or SSH target).
- Configure Grafana notification contact points for alerts.
- Apply least-privilege Tailscale grants in the Tailscale admin console.
- Review Git changes and run a secret scan before every push.
