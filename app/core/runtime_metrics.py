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


def record_request(status_code: int, duration_ms: int) -> None:
    global _requests, _server_errors, _duration_ms
    with _lock:
        _requests += 1
        _duration_ms += max(duration_ms, 0)
        _statuses[status_code] += 1
        if status_code >= 500:
            _server_errors += 1


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
            "safety_decisions": dict(sorted(_safety_levels.items())),
            "pipeline_sources": dict(sorted(_pipeline_sources.items())),
            "pipeline_intents": dict(sorted(_pipeline_intents.items())),
        }
