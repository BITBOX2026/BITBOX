#!/usr/bin/env bash
# deploy/rollback.sh 검증 하네스.
#
# 롤백은 배포가 실패했을 때만 실행되는 코드라, 두어 두면 영영 실행되지 않다가
# 정작 필요한 순간에 처음 돌게 됩니다. 그래서 EC2 없이도 전체 동작을 확인할 수
# 있도록 systemctl / curl / pip 를 가짜로 대체하고 임시 저장소와 릴리스
# 디렉터리를 만들어 스크립트를 실제로 실행합니다.
#
# 직접 실행:  bash deploy/rollback_test.sh
# CI 실행:    python -m pytest tests/test_rollback_script.py
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rollback.sh"
ROOT="$(mktemp -d)"
PASS=0
FAIL=0

note() { printf '%s\n' "$*"; }
check() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS=$((PASS + 1)); note "    [OK]   $label"
  else
    FAIL=$((FAIL + 1)); note "    [FAIL] $label — 기대='$expected' 실제='$actual'"
  fi
}

make_stub_bin() {
  local bin="$1" health_ok="$2"
  mkdir -p "$bin"
  cat > "$bin/systemctl" <<EOF
#!/usr/bin/env bash
echo "systemctl \$*" >> "$bin/../systemctl.log"
exit 0
EOF
  cat > "$bin/curl" <<EOF
#!/usr/bin/env bash
echo "curl \$*" >> "$bin/../curl.log"
prev=""
for arg in "\$@"; do
  case "\$arg" in
    *"/health")
      if [[ "$health_ok" == yes ]]; then
        release_sha="\$(sed -n 's/^RELEASE_SHA=//p' "\$BITBOX_ENV_FILE")"
        printf '{"status":"ok","release_sha":"%s"}\n' "\$release_sha"
        exit 0
      fi
      exit 7
      ;;
  esac
  if [ "\$prev" = "--data" ]; then echo "\$arg" >> "$bin/../alert.log"; fi
  case "\$arg" in http*|https*) echo "URL \$arg" >> "$bin/../alert.log" ;; esac
  prev="\$arg"
done
exit 0
EOF
  cat > "$bin/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$bin/systemctl" "$bin/curl" "$bin/sleep"
}

setup_case() {
  local name="$1" health_ok="$2"
  local case_dir="$ROOT/$name"
  mkdir -p "$case_dir/bin" "$case_dir/www/releases/old" "$case_dir/www/releases/new" "$case_dir/etc"
  make_stub_bin "$case_dir/bin" "$health_ok"

  # 저장소: 커밋 두 개 (old -> new)
  local repo="$case_dir/repo"
  mkdir -p "$repo"
  git -C "$repo" init --quiet -b main
  git -C "$repo" config user.email t@example.test
  git -C "$repo" config user.name Tester
  git -C "$repo" config core.safecrlf false
  git -C "$repo" config core.autocrlf false
  echo "old backend" > "$repo/app.py"
  printf 'httpx\n' > "$repo/requirements-backend.txt"
  git -C "$repo" add -A && git -C "$repo" commit --quiet -m old
  OLD_SHA="$(git -C "$repo" rev-parse HEAD)"
  echo "new backend (broken)" > "$repo/app.py"
  git -C "$repo" add -A && git -C "$repo" commit --quiet -m new
  NEW_SHA="$(git -C "$repo" rev-parse HEAD)"

  mkdir -p "$repo/.venv/bin"
  cat > "$repo/.venv/bin/pip" <<EOF
#!/usr/bin/env bash
echo "pip \$*" >> "$case_dir/pip.log"
exit 0
EOF
  chmod +x "$repo/.venv/bin/pip"

  echo "old frontend" > "$case_dir/www/releases/old/index.html"
  echo "new frontend" > "$case_dir/www/releases/new/index.html"
  printf 'APP_ENV=prod\nRELEASE_SHA=%s\nOPENAI_API_KEY=secret\n' "$NEW_SHA" > "$case_dir/etc/bitbox.env"
  # 현재는 새 릴리스를 가리키는 상태
  ln -sfn "$case_dir/www/releases/new" "$case_dir/www/current" 2>/dev/null \
    || cp -r "$case_dir/www/releases/new" "$case_dir/www/current"
  CASE_DIR="$case_dir"
}

run_rollback() {
  PATH="$CASE_DIR/bin:$PATH" \
  BITBOX_REPO_DIR="$CASE_DIR/repo" \
  BITBOX_ENV_FILE="$CASE_DIR/etc/bitbox.env" \
  BITBOX_CURRENT_LINK="$CASE_DIR/www/current" \
  BITBOX_ROLLBACK_TO_SHA="${1-$OLD_SHA}" \
  BITBOX_ROLLBACK_TO_RELEASE="${2-$CASE_DIR/www/releases/old}" \
  BITBOX_ALERT_WEBHOOK_URL="${3-https://hooks.example.test/abc}" \
    bash "$SCRIPT" > "$CASE_DIR/stdout.log" 2> "$CASE_DIR/stderr.log"
  echo $?
}

# --------------------------------------------------------------------------
note "=== 시나리오 1: 정상 롤백 (백엔드 기동 성공) ==="
setup_case happy yes
RC="$(run_rollback)"
check "종료코드 0" "0" "$RC"
check "프론트엔드가 직전 릴리스로 복구" "old frontend" "$(cat "$CASE_DIR/www/current/index.html" 2>/dev/null)"
check "백엔드 코드가 직전 커밋으로 복구" "old backend" "$(cat "$CASE_DIR/repo/app.py")"
check "체크아웃된 커밋" "$OLD_SHA" "$(git -C "$CASE_DIR/repo" rev-parse HEAD)"
check "RELEASE_SHA 재기록" "RELEASE_SHA=$OLD_SHA" "$(grep '^RELEASE_SHA=' "$CASE_DIR/etc/bitbox.env")"
check "다른 환경변수 보존" "OPENAI_API_KEY=secret" "$(grep '^OPENAI_API_KEY=' "$CASE_DIR/etc/bitbox.env")"
check "백엔드 재시작 호출" "yes" "$(grep -q 'restart bitbox-backend' "$CASE_DIR/systemctl.log" && echo yes || echo no)"
check "nginx 재적용 호출" "yes" "$(grep -q 'reload-or-restart nginx' "$CASE_DIR/systemctl.log" && echo yes || echo no)"
check "알림 발송" "yes" "$(grep -q 'hooks.example.test' "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"
check "성공 로그" "yes" "$(grep -q 'rollback complete and backend is healthy' "$CASE_DIR/stderr.log" && echo yes || echo no)"
check "성공 알림 본문" "yes" "$(grep -q 'rolled back to' "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"

note ""
note "=== 시나리오 2: 롤백했지만 백엔드가 살아나지 않음 ==="
setup_case unhealthy no
RC="$(run_rollback)"
check "종료코드 1 (운영자 개입 필요)" "1" "$RC"
check "그래도 프론트엔드는 복구" "old frontend" "$(cat "$CASE_DIR/www/current/index.html" 2>/dev/null)"
check "수동 개입 알림 본문" "yes" "$(grep -q 'Manual intervention required' "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"
check "실패 로그 남김" "yes" "$(grep -q 'rollback finished with problems' "$CASE_DIR/stderr.log" && echo yes || echo no)"

note ""
note "=== 시나리오 3: 잘못된 SHA 가 주어짐 ==="
setup_case badsha yes
RC="$(run_rollback "not-a-sha" )"
check "종료코드 1 (백엔드 미복구)" "1" "$RC"
check "잘못된 SHA 무시 로그" "yes" "$(grep -q 'malformed rollback SHA' "$CASE_DIR/stderr.log" && echo yes || echo no)"
check "저장소는 건드리지 않음" "new backend (broken)" "$(cat "$CASE_DIR/repo/app.py")"
check "프론트엔드는 복구됨" "old frontend" "$(cat "$CASE_DIR/www/current/index.html" 2>/dev/null)"

note ""
note "=== 시나리오 4: 직전 릴리스 디렉터리가 없음 ==="
setup_case norelease yes
RC="$(run_rollback "$OLD_SHA" "$CASE_DIR/www/releases/does-not-exist")"
check "종료코드 1 (프론트엔드 미복구)" "1" "$RC"
check "없는 릴리스 로그" "yes" "$(grep -q 'no previous frontend release directory' "$CASE_DIR/stderr.log" && echo yes || echo no)"
check "백엔드는 그래도 롤백" "old backend" "$(cat "$CASE_DIR/repo/app.py")"

note ""
note "=== 시나리오 5: 알림 URL 미설정 (현재 운영 상태) ==="
setup_case noalert yes
RC="$(run_rollback "$OLD_SHA" "$CASE_DIR/www/releases/old" "")"
check "종료코드 0" "0" "$RC"
check "알림 없이도 롤백 성공" "old backend" "$(cat "$CASE_DIR/repo/app.py")"
check "알림 시도 없음" "no" "$(test -s "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"

note ""
note "=== 시나리오 6: 표준 Discord 웹훅 형식 ==="
setup_case discord yes
RC="$(run_rollback "$OLD_SHA" "$CASE_DIR/www/releases/old" "https://discord.com/api/webhooks/123/token")"
check "종료코드 0" "0" "$RC"
check "Discord content 필드" "yes" "$(grep -q '\"content\"' "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"
check "Discord 전송 확인 대기" "yes" "$(grep -q 'wait=true' "$CASE_DIR/alert.log" 2>/dev/null && echo yes || echo no)"

note ""
note "==================================================="
note "통과 $PASS / 실패 $FAIL"
rm -rf "$ROOT"
[[ "$FAIL" == 0 ]]
