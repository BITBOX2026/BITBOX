#!/usr/bin/env bash
set -euo pipefail

health_state_file=/run/bitbox-healthcheck.health.failures
ready_state_file=/run/bitbox-healthcheck.ready.failures

send_alert() {
  local message="$1"
  local strict="${2:-false}"
  if [[ -z "${BITBOX_ALERT_WEBHOOK_URL:-}" ]]; then
    # 알림 채널이 없으면 조용히 넘어가지 않고 저널에 남깁니다. 무인 키오스크에서
    # "아무도 모르는 장애"를 만들지 않기 위한 최소한의 흔적입니다.
    #   확인: journalctl -t bitbox-healthcheck --since '-1d'
    logger -t bitbox-healthcheck "ALERT (no webhook configured): $message" || true
    [[ "$strict" == "true" ]] && return 1
    return 0
  fi
  local payload http_code webhook_url
  # 시크릿에 섞여 들어온 공백·개행은 URL 경로를 망가뜨려 Discord가 400으로
  # 거절합니다. 웹후크 URL에 공백이 들어갈 일은 없으므로 전부 떼어냅니다.
  webhook_url="${BITBOX_ALERT_WEBHOOK_URL//[[:space:]]/}"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  message="${message//$'\n'/\\n}"
  # discord.com·discordapp.com·canary/ptb 서브도메인을 모두 Discord로 봅니다.
  # 여기서 빗나가면 Slack 형식 {"text":...}을 보내고 Discord는 400으로 거절합니다.
  if [[ "$webhook_url" == *discord*.com/api/webhooks/* && "$webhook_url" != */slack* ]]; then
    payload="{\"content\":\"$message\"}"
    [[ "$webhook_url" == *\?* ]] && webhook_url="${webhook_url}&wait=true" || webhook_url="${webhook_url}?wait=true"
  else
    payload="{\"text\":\"$message\"}"
  fi
  # --fail 은 상태 코드를 삼켜버립니다. 코드를 직접 받아 남겨야 400(페이로드 형식)과
  # 401·404(URL·토큰 문제)를 나중에 구분할 수 있습니다.
  http_code="$(curl --silent --show-error --max-time 5 \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    --output /dev/null --write-out '%{http_code}' \
    "$webhook_url" || true)"
  if [[ "$http_code" != 2?? ]]; then
    echo "[bitbox-healthcheck] alert delivery failed (HTTP ${http_code:-000})" >&2
    logger -t bitbox-healthcheck "alert delivery failed (HTTP ${http_code:-000})" || true
    [[ "$strict" == "true" ]] && return 1
  fi
  return 0
}

if [[ "${1:-}" == "--test-alert" ]]; then
  monitoring_env_file="${BITBOX_MONITORING_ENV_FILE:-/etc/bitbox/monitoring.env}"
  if [[ -z "${BITBOX_ALERT_WEBHOOK_URL:-}" && -r "$monitoring_env_file" ]]; then
    webhook_line="$(grep -m1 '^BITBOX_ALERT_WEBHOOK_URL=' "$monitoring_env_file" || true)"
    BITBOX_ALERT_WEBHOOK_URL="${webhook_line#BITBOX_ALERT_WEBHOOK_URL=}"
  fi
  send_alert "${2:-BITBOX monitoring test alert.}" true
  echo "[bitbox-healthcheck] test alert delivered"
  exit 0
fi

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
