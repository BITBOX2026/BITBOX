#!/usr/bin/env bash
# Restore the previously deployed BITBOX release on this EC2 host.
#
# 배포 검증이 실패하면 deploy.yml이 이 스크립트를 호출합니다. 운영자가 직접
# 실행할 수도 있습니다:
#
#   sudo BITBOX_ROLLBACK_TO_SHA=<40자리 SHA> bash deploy/rollback.sh
#
# 되돌리는 대상은 두 가지입니다.
#   1) 정적 프론트엔드  — /var/www/bitbox-current 심볼릭 링크
#   2) 백엔드 코드      — 작업 트리를 이전 커밋으로 체크아웃 후 서비스 재시작
#
# 어느 한쪽만 성공해도 나머지는 계속 시도합니다. 롤백 도중 실패해도 현재 상태를
# 더 망가뜨리지 않도록 각 단계를 개별적으로 방어합니다.
set -uo pipefail

REPO_DIR="${BITBOX_REPO_DIR:-/home/ubuntu/BITBOX}"
ENV_FILE="${BITBOX_ENV_FILE:-/etc/bitbox/bitbox.env}"
CURRENT_LINK="${BITBOX_CURRENT_LINK:-/var/www/bitbox-current}"
target_sha="${BITBOX_ROLLBACK_TO_SHA:-}"
target_release="${BITBOX_ROLLBACK_TO_RELEASE:-}"

log() { echo "[bitbox-rollback] $*" >&2; }

send_alert() {
  if [[ -z "${BITBOX_ALERT_WEBHOOK_URL:-}" ]]; then
    # 알림 채널이 없어도 조용히 넘어가지 않습니다. 무인 키오스크에서 "아무도 모르는
    # 장애"를 만들지 않기 위해 최소한 시스템 저널에 흔적을 남깁니다.
    #   확인: journalctl -t bitbox-rollback --since '-7d'
    log "ALERT (no webhook configured): $1"
    command -v logger >/dev/null 2>&1 && logger -t bitbox-rollback "$1"
    return 0
  fi
  local message="$1" payload webhook_url="$BITBOX_ALERT_WEBHOOK_URL"
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
    log "failed to deliver rollback alert"
    command -v logger >/dev/null 2>&1 && logger -t bitbox-rollback "alert delivery failed"
  fi
}

if [[ -z "$target_sha" && -f /etc/bitbox/previous_release_sha ]]; then
  target_sha="$(cat /etc/bitbox/previous_release_sha 2>/dev/null || true)"
fi

if [[ -n "$target_sha" && ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  log "ignoring malformed rollback SHA"
  target_sha=""
  malformed_sha=1
else
  malformed_sha=0
fi

rollback_failures=$malformed_sha

# --- 1) 정적 프론트엔드 -----------------------------------------------------
restore_frontend() {
  local target="$1"
  local staging="${CURRENT_LINK}.rollback"

  # 정상 경로: 새 심볼릭 링크를 만들고 원자적으로 교체합니다.
  rm -rf -- "$staging" 2>/dev/null
  if ln -sfn "$target" "$staging" 2>/dev/null \
    && mv -Tf "$staging" "$CURRENT_LINK" 2>/dev/null; then
    return 0
  fi
  rm -rf -- "$staging" 2>/dev/null

  # `mv -T` 는 대상이 비어 있지 않은 "실제 디렉터리"면 실패합니다. 운영자가 링크를
  # 디렉터리로 바꿔 놓은 호스트에서도 롤백이 멈추지 않도록 한 번 더 복구합니다.
  # 이 경로는 /var/www/bitbox-releases 에서 언제든 다시 만들 수 있는 배포 산출물만
  # 지우므로 안전하지만, 빈 값이나 루트로는 절대 동작하지 않게 막습니다.
  if [[ -n "$CURRENT_LINK" && "$CURRENT_LINK" != "/" && -d "$CURRENT_LINK" && ! -L "$CURRENT_LINK" ]]; then
    log "current release path is a real directory, not a symlink; replacing it"
    rm -rf -- "$CURRENT_LINK" && ln -sfn "$target" "$CURRENT_LINK" && return 0
  fi
  return 1
}

if [[ -n "$target_release" && -d "$target_release" ]]; then
  if restore_frontend "$target_release"; then
    log "frontend restored to $target_release"
  else
    log "failed to restore the frontend release pointer"
    rollback_failures=$((rollback_failures + 1))
  fi
else
  log "no previous frontend release directory to restore"
  rollback_failures=$((rollback_failures + 1))
fi

# --- 2) 백엔드 코드 ---------------------------------------------------------
if [[ -n "$target_sha" ]] && [[ -d "$REPO_DIR/.git" ]]; then
  if git -C "$REPO_DIR" cat-file -e "${target_sha}^{commit}" 2>/dev/null; then
    if git -C "$REPO_DIR" checkout --quiet --force --detach "$target_sha"; then
      log "backend checked out at $target_sha"
      "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements-backend.txt" -q \
        || { log "dependency reinstall reported an error"; rollback_failures=$((rollback_failures + 1)); }
      if [[ -f "$ENV_FILE" ]]; then
        # /health 와 /ready 가 실제로 서비스 중인 커밋을 보고하도록 맞춥니다.
        sed -i "s/^RELEASE_SHA=.*/RELEASE_SHA=${target_sha}/" "$ENV_FILE" \
          || { log "failed to rewrite RELEASE_SHA"; rollback_failures=$((rollback_failures + 1)); }
      fi
    else
      log "git checkout of the previous commit failed"
      rollback_failures=$((rollback_failures + 1))
    fi
  else
    log "previous commit $target_sha is not present locally"
    rollback_failures=$((rollback_failures + 1))
  fi
else
  log "no previous backend commit to restore"
  rollback_failures=$((rollback_failures + 1))
fi

# --- 3) 서비스 재기동 -------------------------------------------------------
systemctl restart bitbox-backend.service || rollback_failures=$((rollback_failures + 1))
systemctl reload-or-restart nginx || rollback_failures=$((rollback_failures + 1))

restored=0
for _ in $(seq 1 20); do
  if [[ -n "$target_sha" ]] && curl --fail --silent --max-time 5 http://127.0.0.1:8001/health \
    | grep -q "\"release_sha\":\"$target_sha\""; then
    restored=1
    break
  fi
  sleep 1
done

if [[ "$restored" == 1 && "$rollback_failures" == 0 ]]; then
  log "rollback complete and backend is healthy"
  send_alert "BITBOX deployment failed; rolled back to ${target_sha:-previous release} and the backend is healthy."
  exit 0
fi

log "rollback finished with problems (healthy=$restored failures=$rollback_failures)"
send_alert "BITBOX deployment failed AND rollback did not fully succeed. Manual intervention required."
exit 1
