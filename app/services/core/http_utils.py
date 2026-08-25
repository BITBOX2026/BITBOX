"""
공통 HTTP 재시도 데코레이터

네트워크 오류나 서버 오류(5xx)가 발생하면 최대 3회까지 자동 재시도합니다.
Kakao / ODsay / 서울버스 API 클라이언트에서 공통으로 사용합니다.

재시도 정책:
- 대상: TransportError(네트워크 끊김 등), HTTPStatusError(5xx)
- 횟수: 최대 3회
- 대기: 0.5초 → 1초 → 2초 (지수 백오프, 최대 4초)
"""

import functools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.core.exceptions import ExternalServiceError


def is_retryable(exc: BaseException) -> bool:
    """재시도할 수 있는 예외인지 판별합니다."""
    if isinstance(exc, httpx.TransportError):
        # 네트워크 연결 오류, 타임아웃 등
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 서버 오류(500~599)만 재시도, 클라이언트 오류(4xx)는 재시도하지 않음
        return exc.response.status_code >= 500
    if isinstance(exc, ExternalServiceError):
        return exc.retryable
    return False


@dataclass
class _CircuitState:
    failures: int = 0
    open_until: float = 0.0


_circuits: dict[str, _CircuitState] = {}
_circuit_lock = threading.Lock()


def _circuit_is_open(name: str) -> bool:
    now = time.monotonic()
    with _circuit_lock:
        state = _circuits.setdefault(name, _CircuitState())
        if state.open_until <= 0:
            return False
        if now >= state.open_until:
            state.open_until = 0.0
            state.failures = 0
            return False
        return True


def _record_circuit_success(name: str) -> None:
    with _circuit_lock:
        state = _circuits.setdefault(name, _CircuitState())
        state.failures = 0
        state.open_until = 0.0


def _record_circuit_failure(name: str, *, force_open: bool = False) -> None:
    with _circuit_lock:
        state = _circuits.setdefault(name, _CircuitState())
        state.failures += 1
        if force_open or state.failures >= settings.EXTERNAL_CIRCUIT_FAILURE_THRESHOLD:
            state.open_until = (
                time.monotonic() + settings.EXTERNAL_CIRCUIT_RESET_SECONDS
            )


def _counts_toward_circuit(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return True


def http_retry(function: Callable[..., Any]) -> Callable[..., Any]:
    """Retry transient failures and temporarily open a per-provider circuit."""
    retried = retry(
        retry=retry_if_exception(is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )(function)
    circuit_name = f"{function.__module__}.{function.__name__}"

    @functools.wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        if _circuit_is_open(circuit_name):
            request = httpx.Request("GET", "https://external-service.invalid")
            raise httpx.ConnectError(
                "external service circuit is open", request=request
            )
        try:
            result = await retried(*args, **kwargs)
        except Exception as exc:
            if _counts_toward_circuit(exc):
                force_open = isinstance(exc, ExternalServiceError) and not exc.retryable
                _record_circuit_failure(circuit_name, force_open=force_open)
            raise
        _record_circuit_success(circuit_name)
        return result

    return wrapped


def circuit_snapshot() -> dict[str, dict[str, int | bool]]:
    now = time.monotonic()
    with _circuit_lock:
        return {
            name: {
                "failures": state.failures,
                "open": state.open_until > now,
                "retry_after_seconds": max(0, round(state.open_until - now)),
            }
            for name, state in _circuits.items()
        }
