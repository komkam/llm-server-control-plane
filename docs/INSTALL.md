# Installation

This repository is portable: it intentionally contains no device name, Tailnet
hostname, public URL, token, password, or private key.

## Prerequisites

- Linux host with systemd, Docker Compose, Python and the required local LLM
  services installed.
- This repository checked out at `/opt/llm-server` (or update the unit paths
  before installation).
- A Python virtual environment at `venv/`; the diagnostic agent also needs its
  own `apps/agent/.venv/`.
- Optional: Tailscale for private HTTPS exposure. Configure its hostname and
  access policy outside this repository.

The installer creates a random local Grafana password file when it is absent; retrieve it locally with root access if needed.
## Install unit definitions

```bash
cd /opt/llm-server
sudo ./install.sh
docker compose up -d
sudoedit /opt/llm-server/.env
```

The installer copies unit files and runs `systemctl daemon-reload`. It does not
enable or start anything. The copied runtime file is local-only and is ignored
by Git.

## Ports

| Component | Loopback listener | Private HTTPS port when proxied |
| --- | ---: | ---: |
| Open WebUI | 3000 | 443 |
| Grafana | 3100 | 8443 |
| Control Panel | 7000 | 8444 |
| Prometheus | 9090 | — |
| Router API | 5000 | — |
| Diagnostic Agent | 5100 | — |
| Electrical Engineering Agent | `5301` | — |
| Mechanical Engineering Agent | `5302` | — |
| Action Engine | 5200 | — |

Configure your reverse proxy or Tailscale Serve rules with your own host name.
Do not bind monitoring or control-plane ports directly to the public Internet.

## Enable deliberately

Review dependencies and enable only what the host needs, for example:

```bash
sudo systemctl enable --now router.service agent.service dashboard.service
sudo systemctl enable --now action-engine.service autonomy.service
sudo systemctl enable --now control-plane-exporter.service gpu-exporter.service docker-exporter.service
sudo systemctl enable --now observability.service
```

Before enabling `restic-backup.service`, create
those services' credential files locally. They are intentionally not provisioned
by the installer.
