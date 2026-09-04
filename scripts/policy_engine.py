#!/usr/bin/env python3
"""Deterministic policy classification for staged LLM-server changes."""
import json
import sys

HIGH = ("sudoers", "action-engine", "config/systemd", "scripts/release.sh", "scripts/backup.sh", "scripts/verify.sh")
MEDIUM = ("apps/", "services/", "deploy/")
ALLOWED = ("apps/", "services/", "config/", "deploy/", "scripts/", "docs/")

paths = [line.strip() for line in sys.stdin if line.strip()]
unknown = [path for path in paths if not path.startswith(ALLOWED)]
if unknown:
    print(json.dumps({"decision": "REJECT", "risk": "HIGH", "unknown_paths": unknown}))
    raise SystemExit(2)
risk = "LOW"
if any(any(marker in path for marker in HIGH) for path in paths):
    risk = "HIGH"
elif any(path.startswith(MEDIUM) for path in paths):
    risk = "MEDIUM"
print(json.dumps({"decision": "ALLOW", "risk": risk, "paths": paths}))
