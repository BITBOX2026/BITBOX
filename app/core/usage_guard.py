"""In-process safety limits for requests that consume paid provider quotas."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fastapi import HTTPException


@dataclass
class _UsageState:
    day: date
    active: int = 0
    used: int = 0


_states: dict[str, _UsageState] = {}
_lock = asyncio.Lock()


@asynccontextmanager
async def usage_slot(
    name: str,
    *,
    max_concurrent: int,
    daily_limit: int,
) -> AsyncIterator[None]:
    """Reserve one bounded provider slot and release its active count afterward."""
    today = datetime.now(UTC).date()
    async with _lock:
        state = _states.setdefault(name, _UsageState(day=today))
        if state.day != today:
            state.day = today
            state.used = 0
        if state.used >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail="오늘의 서비스 요청 한도에 도달했습니다. 잠시 후 다시 이용해 주세요.",
                headers={"Retry-After": "3600"},
            )
        if state.active >= max_concurrent:
            raise HTTPException(
                status_code=429,
                detail="현재 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
                headers={"Retry-After": "5"},
            )
        state.active += 1
        state.used += 1

    try:
        yield
    finally:
        async with _lock:
            state.active = max(0, state.active - 1)


def usage_snapshot() -> dict[str, dict[str, int | str]]:
    """Return a privacy-safe snapshot for the local operations endpoint."""
    return {
        name: {
            "day": state.day.isoformat(),
            "active": state.active,
            "used": state.used,
        }
        for name, state in _states.items()
    }
