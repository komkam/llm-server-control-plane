#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/llm-server
ID=${1:?staging id required}
WORK="${BASE}/staging/${ID}/workspace"
ARTIFACTS="${BASE}/staging/${ID}/artifacts"
test -d "${WORK}"
install -d -m 0750 "${ARTIFACTS}"
diff -ruN --exclude='__pycache__' --exclude='.venv' "${BASE}/apps" "${WORK}/apps" > "${ARTIFACTS}/diff.patch" || test $? -eq 1
grep '^diff -ruN ' "${ARTIFACTS}/diff.patch" | awk '{print $NF}' | sed "s|${WORK}/||" | sort -u > "${ARTIFACTS}/changed-paths.txt" || true
python3 "${BASE}/scripts/policy_engine.py" < "${ARTIFACTS}/changed-paths.txt" > "${ARTIFACTS}/policy.json"
find "${WORK}" -name '*.py' -print0 | xargs -0 -r python3 -m py_compile
find "${WORK}" -name '*.sh' -print0 | xargs -0 -r bash -n
printf '{"syntax":"passed","builder":"candidate_builder"}\n' > "${ARTIFACTS}/validation.json"
"${BASE}/scripts/release.sh" candidate "${ID}"
