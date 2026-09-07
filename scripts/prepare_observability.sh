#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/llm-server
DATA="$BASE/data/observability"
SECRET_DIR="$BASE/config/observability/secrets"

install -d -m 0750 "$DATA"/{prometheus,loki,alloy,tempo} "$BASE/data/falco" "$SECRET_DIR"
