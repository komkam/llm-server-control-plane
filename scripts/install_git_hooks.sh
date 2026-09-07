#!/usr/bin/env bash
set -euo pipefail

git -C /opt/llm-server config core.hooksPath config/git-hooks
chmod 0755 /opt/llm-server/config/git-hooks/pre-commit
