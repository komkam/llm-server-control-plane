# LLM Server Control Plane

A portable local LLM platform with controlled operations, observability, and an
approval-gated deployment workflow. Network exposure is configured locally;
this repository contains no device- or tailnet-specific address.

## Current architecture

```text
Open WebUI
  -> Semantic Router
     -> Ollama / Qwen
     -> Ollama / Qwen

Control Plane
  -> Diagnostic Agent
  -> Electrical Engineering Agent (proposal-only)
  -> Mechanical Engineering Agent (proposal-only)
  -> Autonomy Supervisor
  -> Action Engine
  -> Change Planner / Candidate Builder
  -> Policy, Approval, Deployment and Rollback

Observability
  -> Prometheus -> Grafana
  -> Loki, Tempo, OpenTelemetry Collector, Alloy
  -> node-exporter, GPU exporter, Docker exporter, Falco
```

## Install and private access

Install from a checked-out repository as root:

```bash
sudo ./install.sh
docker compose up -d
sudoedit /etc/llm-server/runtime.env
```

The installer copies service definitions and creates the local runtime file. It
does not start services or configure public exposure. Set the hostname, access
policy, and TLS/Tailscale Serve rules on the machine where it is installed.

Only the ports are fixed by the bundled configuration:

| Service | Private listener / HTTPS port |
| --- | --- |
| Open WebUI | `3000` / `443` |
| Grafana monitoring | `3100` / `8443` |
| Control Panel | `7000` / `8444` |
| Prometheus | `9090` |

For a private Tailscale installation, point Serve at the loopback listeners;
the external tailnet hostname is deliberately not stored in this project.

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
use `config/secrets/README.md` as the local setup guide. Copy `config/runtime.env.example` to a machine-local runtime file; it is deliberately ignored by Git.

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
