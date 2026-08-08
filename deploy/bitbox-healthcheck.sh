#!/usr/bin/env bash
set -euo pipefail

state_file=/run/bitbox-healthcheck.failures
if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8001/ready >/dev/null; then
  printf '0\n' > "$state_file"
  exit 0
fi

failures=0
if [[ -f "$state_file" ]]; then
  read -r failures < "$state_file" || failures=0
fi
failures=$((failures + 1))
printf '%d\n' "$failures" > "$state_file"

if (( failures >= 3 )); then
  logger -t bitbox-healthcheck "readiness failed three times; restarting backend"
  systemctl restart bitbox-backend.service
  printf '0\n' > "$state_file"
fi

exit 1
