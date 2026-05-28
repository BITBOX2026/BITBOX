"""
IP 기반 요청 속도 제한 (Rate Limiter)

slowapi + starlette를 사용합니다.

사용 예시 (gateway.py):
    @limiter.limit("10/minute")
    async def process_audio(request: Request, ...):
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.core.settings_helper import get_bool_setting

# 클라이언트 IP를 키로 삼아 분당 요청 수를 제한합니다.
# SlowAPI는 기본적으로 현재 작업 디렉터리의 .env를 Starlette Config로 읽는데,
# Windows cp949 환경에서 UTF-8 한글 주석이 깨질 수 있어 비어 있는 별도 설정 파일명을
# 지정합니다. 실제 제한값은 코드의 @limiter.limit 데코레이터에서 관리합니다.
limiter = Limiter(
    key_func=get_remote_address,
    config_filename="slowapi.cfg",
    enabled=get_bool_setting("RATE_LIMIT_ENABLED", True),
)
