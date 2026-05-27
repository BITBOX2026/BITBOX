"""
공통 HTTP 재시도 데코레이터

네트워크 오류나 서버 오류(5xx)가 발생하면 최대 3회까지 자동 재시도합니다.
Kakao / ODsay / 서울버스 API 클라이언트에서 공통으로 사용합니다.

재시도 정책:
- 대상: TransportError(네트워크 끊김 등), HTTPStatusError(5xx)
- 횟수: 최대 3회
- 대기: 0.5초 → 1초 → 2초 (지수 백오프, 최대 4초)
"""

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def is_retryable(exc: BaseException) -> bool:
    """재시도할 수 있는 예외인지 판별합니다."""
    if isinstance(exc, httpx.TransportError):
        # 네트워크 연결 오류, 타임아웃 등
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 서버 오류(500~599)만 재시도, 클라이언트 오류(4xx)는 재시도하지 않음
        return exc.response.status_code >= 500
    return False


http_retry = retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,  # 최종 실패 시 원래 예외를 그대로 다시 발생
)
