#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/llm-server
ID=${1:?staging id required}
WORK="${BASE}/staging/${ID}/workspace"
ARTIFACTS="${BASE}/staging/${ID}/artifacts"
if ! test -d "${WORK}"; then
  "${BASE}/scripts/release.sh" stage "${ID}" >/dev/null
fi
install -d -m 0750 "${ARTIFACTS}"
> "${ARTIFACTS}/diff.patch"
for component in apps services config deploy scripts docs; do
  diff -ruN --exclude='__pycache__' --exclude='.venv' --exclude='data' --exclude='logs' "${BASE}/${component}" "${WORK}/${component}" >> "${ARTIFACTS}/diff.patch" || test $? -eq 1
done
grep '^diff -ruN ' "${ARTIFACTS}/diff.patch" | awk '{print $NF}' | sed "s|${WORK}/||" | sort -u > "${ARTIFACTS}/changed-paths.txt" || true
python3 "${BASE}/scripts/policy_engine.py" < "${ARTIFACTS}/changed-paths.txt" > "${ARTIFACTS}/policy.json"
find "${WORK}" -type f -name '*.py' -not -path '*/.venv/*' -not -path '*/__pycache__/*' -print0 | xargs -0 -r python3 -m py_compile
find "${WORK}" -type f -name '*.sh' -not -path '*/.venv/*' -print0 | xargs -0 -r bash -n
printf '{"syntax":"passed","builder":"candidate_builder","workspace":"%s"}\n' "${WORK}" > "${ARTIFACTS}/validation.json"
"${BASE}/scripts/release.sh" candidate "${ID}"
