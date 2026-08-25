"""
IP 기반 요청 속도 제한 (Rate Limiter)

slowapi + starlette를 사용합니다.

사용 예시 (gateway.py):
    @limiter.limit("10/minute")
    async def process_audio(request: Request, ...):
        ...
"""

from slowapi import Limiter
from starlette.requests import Request

from app.services.core.settings_helper import get_bool_setting


def _client_address(request: Request) -> str:
    """Trust forwarding headers only from the local reverse proxy.

    보안 전제: 이 로직은 loopback(127.0.0.1/::1)에 바인딩된 프로세스가
    nginx 리버스 프록시뿐이라는 배포 토폴로지를 전제로 합니다.
    컨테이너화 등으로 여러 프로세스가 네트워크 네임스페이스를 공유하게 되면
    다른 프로세스가 X-Forwarded-For를 위조해 rate limit을 우회할 수 있으므로,
    배포 구조를 바꿀 때는 반드시 이 가정을 재검토해야 합니다.
    """
    direct = request.client.host if request.client else "unknown"
    if direct in {"127.0.0.1", "::1"}:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return direct

# 클라이언트 IP를 키로 삼아 분당 요청 수를 제한합니다.
# SlowAPI는 기본적으로 현재 작업 디렉터리의 .env를 Starlette Config로 읽는데,
# Windows cp949 환경에서 UTF-8 한글 주석이 깨질 수 있어 비어 있는 별도 설정 파일명을
# 지정합니다. 실제 제한값은 코드의 @limiter.limit 데코레이터에서 관리합니다.
limiter = Limiter(
    key_func=_client_address,
    config_filename="slowapi.cfg",
    enabled=get_bool_setting("RATE_LIMIT_ENABLED", True),
)
