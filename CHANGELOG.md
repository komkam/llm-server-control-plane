# Changelog

## v1.2.0 — 2026-09-08

- Retired Phi-3/llama-server from production routing and disabled its systemd service.
- Normal `auto` chat now routes directly to Qwen; model files remain on disk for rollback only.
- Updated diagnostics, monitoring, action policy, deployment verification and documentation for the Qwen-only runtime.

## v1.1.0 — 2026-09-08

- Added proposal-only Electrical Engineering Agent, isolated on loopback port 5301.
- Added explicit Router route, monitored service health and Action Engine restart allowlist.
- Added safety policy, engineering review boundary and curated knowledge-base placeholder.

## v1.0.0 — 2026-09-08

First deployable release of the LLM Server Control Plane.

### Included

- Automatic local-model routing with response-model attribution and language guard.
- Approval-gated change planning, candidate building, policy checks, deployment,
  verification, rollback, and audit trail.
- Restricted Action Engine and Auto-safe Autonomy Supervisor; neither has
  arbitrary-shell authority.
- Grafana, Prometheus, Loki, Tempo, Alloy, Falco, OpenTelemetry and dedicated
  host/GPU/Docker/control-plane exporters.
- Portable installation package with local-only runtime configuration and no
  embedded Tailnet hostname, machine IP, token, password, or private key.

### Deployment boundary

This release installs definitions only. Review `/etc/llm-server/runtime.env`,
required Python environments, Docker, local model services and reverse-proxy or
Tailscale configuration before enabling individual units. Services are not
started automatically by `install.sh`.

### Verification performed

- Shell syntax checks for installer and operational scripts.
- Python compilation for supervisor, action engine and exporters.
- Systemd unit validation.
- Docker Compose configuration validation.
- Archive-from-Git portability check, including a scan for retired host values.
