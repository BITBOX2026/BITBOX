"""Small dependency-free runtime counters for local operational inspection."""

import threading
import time
from collections import Counter

_started_at = time.time()
_lock = threading.Lock()
_requests = 0
_server_errors = 0
_duration_ms = 0
_statuses: Counter[int] = Counter()
_safety_levels: Counter[str] = Counter()
_pipeline_sources: Counter[str] = Counter()
_pipeline_intents: Counter[str] = Counter()
_business_errors: Counter[str] = Counter()


def record_request(status_code: int, duration_ms: int) -> None:
    global _requests, _server_errors, _duration_ms
    with _lock:
        _requests += 1
        _duration_ms += max(duration_ms, 0)
        _statuses[status_code] += 1
        if status_code >= 500:
            _server_errors += 1


def record_business_error(error_kind: str) -> None:
    """Count a request that answered HTTP 200 while reporting a failed outcome.

    검색 결과 없음처럼 사용자가 다시 말해야 하는 응답은 HTTP 200으로 나가므로
    상태코드 카운터에서는 성공과 구분되지 않습니다. 운영자가 "성공률"을 볼 때
    이런 응답이 성공으로 묻히지 않도록 따로 셉니다.
    """
    with _lock:
        _business_errors[error_kind or "unknown"] += 1


def record_safety_decision(level: str, source: str, intent: str) -> None:
    """Count privacy-safe pipeline decisions without storing user input."""
    with _lock:
        _safety_levels[level or "unknown"] += 1
        _pipeline_sources[source or "none"] += 1
        _pipeline_intents[intent or "unknown"] += 1


def runtime_snapshot() -> dict[str, object]:
    with _lock:
        average_ms = round(_duration_ms / _requests, 2) if _requests else 0.0
        return {
            "uptime_seconds": round(time.time() - _started_at),
            "requests": _requests,
            "server_errors": _server_errors,
            "average_duration_ms": average_ms,
            "statuses": {str(code): count for code, count in sorted(_statuses.items())},
            "business_errors": dict(sorted(_business_errors.items())),
            "safety_decisions": dict(sorted(_safety_levels.items())),
            "pipeline_sources": dict(sorted(_pipeline_sources.items())),
            "pipeline_intents": dict(sorted(_pipeline_intents.items())),
        }
