#!/usr/bin/env bash
set -euo pipefail

source /etc/duckdns/duckdns.env
domain="${DUCKDNS_DOMAIN%.duckdns.org}"
response="$(curl --fail --silent --show-error --max-time 20 --get \
  --data-urlencode "domains=${domain}" \
  --data-urlencode "token=${DUCKDNS_TOKEN}" \
  --data-urlencode 'ip=' \
  https://www.duckdns.org/update)"

if [[ "${response}" != 'OK' ]]; then
  echo "DuckDNS returned an unexpected response" >&2
  exit 1
fi

logger -t duckdns-update "updated ${DUCKDNS_DOMAIN}"
