#!/usr/bin/env bash
set -euo pipefail

health_state_file=/run/bitbox-healthcheck.health.failures
ready_state_file=/run/bitbox-healthcheck.ready.failures

send_alert() {
  local message="$1"
  if [[ -z "${BITBOX_ALERT_WEBHOOK_URL:-}" ]]; then
    # 알림 채널이 없으면 조용히 넘어가지 않고 저널에 남깁니다. 무인 키오스크에서
    # "아무도 모르는 장애"를 만들지 않기 위한 최소한의 흔적입니다.
    #   확인: journalctl -t bitbox-healthcheck --since '-1d'
    logger -t bitbox-healthcheck "ALERT (no webhook configured): $message" || true
    return 0
  fi
  local payload webhook_url="$BITBOX_ALERT_WEBHOOK_URL"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  message="${message//$'\n'/\\n}"
  if [[ "$webhook_url" == *"discord.com/api/webhooks/"* && "$webhook_url" != */slack* ]]; then
    payload="{\"content\":\"$message\"}"
    [[ "$webhook_url" == *\?* ]] && webhook_url="${webhook_url}&wait=true" || webhook_url="${webhook_url}?wait=true"
  else
    payload="{\"text\":\"$message\"}"
  fi
  if ! curl --fail --silent --show-error --max-time 5 \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    "$webhook_url" >/dev/null; then
    echo "[bitbox-healthcheck] alert delivery failed" >&2
    logger -t bitbox-healthcheck "alert delivery failed" || true
  fi
}

if ! curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8001/health >/dev/null; then
  health_failures=0
  if [[ -f "$health_state_file" ]]; then
    read -r health_failures < "$health_state_file" || health_failures=0
  fi
  health_failures=$((health_failures + 1))
  printf '%d\n' "$health_failures" > "$health_state_file"
  if (( health_failures >= 3 )); then
    logger -t bitbox-healthcheck "liveness failed three times; restarting backend"
    send_alert "BITBOX liveness failed three times; backend restart requested."
    systemctl restart bitbox-backend.service
    printf '0\n' > "$health_state_file"
  fi
  exit 1
fi

printf '0\n' > "$health_state_file"

if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8001/ready >/dev/null; then
  printf '0\n' > "$ready_state_file"
  exit 0
fi

ready_failures=0
if [[ -f "$ready_state_file" ]]; then
  read -r ready_failures < "$ready_state_file" || ready_failures=0
fi
ready_failures=$((ready_failures + 1))
printf '%d\n' "$ready_failures" > "$ready_state_file"

if (( ready_failures >= 3 )); then
  logger -t bitbox-healthcheck "readiness degraded by an external dependency"
  send_alert "BITBOX readiness is degraded; backend remains live and was not restarted."
  printf '0\n' > "$ready_state_file"
fi

exit 1
