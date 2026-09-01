"""Concurrency and single-instance daily limits for paid provider requests."""

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.core.config import settings


@dataclass
class _UsageState:
    day: date
    active: int = 0
    used: int = 0


_states: dict[str, _UsageState] = {}
_lock = asyncio.Lock()
_SERVICE_TIMEZONE = ZoneInfo("Asia/Seoul")


class _DailyLimitReached(Exception):
    pass


def _service_now() -> datetime:
    """Return the clock used by Korean provider daily allowances."""
    return datetime.now(_SERVICE_TIMEZONE)


def _daily_retry_after_seconds(now: datetime | None = None) -> int:
    """Seconds until the next Korean calendar day, never less than one."""
    current = now or _service_now()
    next_midnight = datetime.combine(
        current.date() + timedelta(days=1),
        time.min,
        tzinfo=_SERVICE_TIMEZONE,
    )
    return max(1, int((next_midnight - current).total_seconds()))


def _reserve_persistent_usage(name: str, day: date, daily_limit: int) -> int:
    """Atomically reserve one daily slot in SQLite and return the new count."""
    if not settings.USAGE_DB_PATH:
        raise RuntimeError("persistent usage storage is not configured")

    try:
        with sqlite3.connect(settings.USAGE_DB_PATH, timeout=5.0) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_usage (
                    name TEXT PRIMARY KEY,
                    day TEXT NOT NULL,
                    used INTEGER NOT NULL CHECK (used >= 0)
                )
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT day, used FROM daily_usage WHERE name = ?",
                (name,),
            ).fetchone()
            used = int(row[1]) if row and row[0] == day.isoformat() else 0
            if used >= daily_limit:
                raise _DailyLimitReached
            used += 1
            connection.execute(
                """
                INSERT INTO daily_usage(name, day, used) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET day = excluded.day, used = excluded.used
                """,
                (name, day.isoformat(), used),
            )
            return used
    except _DailyLimitReached:
        raise
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="사용량 보호 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": "30"},
        ) from exc


@asynccontextmanager
async def usage_slot(
    name: str,
    *,
    max_concurrent: int,
    daily_limit: int,
) -> AsyncIterator[None]:
    """Reserve one bounded provider slot and release its active count afterward."""
    today = _service_now().date()
    async with _lock:
        state = _states.setdefault(name, _UsageState(day=today))
        if state.day != today:
            state.day = today
            state.used = 0
        if state.used >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail="오늘의 서비스 요청 한도에 도달했습니다. 잠시 후 다시 이용해 주세요.",
                headers={"Retry-After": str(_daily_retry_after_seconds())},
            )
        if state.active >= max_concurrent:
            raise HTTPException(
                status_code=429,
                detail="현재 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
                headers={"Retry-After": "5"},
            )
        if settings.USAGE_DB_PATH:
            try:
                state.used = _reserve_persistent_usage(name, today, daily_limit)
            except _DailyLimitReached as exc:
                raise HTTPException(
                    status_code=429,
                    detail="오늘의 서비스 요청 한도에 도달했습니다. 잠시 후 다시 이용해 주세요.",
                    headers={"Retry-After": str(_daily_retry_after_seconds())},
                ) from exc
        else:
            state.used += 1
        state.active += 1

    try:
        yield
    finally:
        async with _lock:
            state.active = max(0, state.active - 1)


@asynccontextmanager
async def concurrency_slot(name: str, *, max_concurrent: int) -> AsyncIterator[None]:
    """Bound in-flight work without consuming a paid-provider daily call."""
    today = _service_now().date()
    async with _lock:
        state = _states.setdefault(name, _UsageState(day=today))
        if state.day != today:
            state.day = today
            state.used = 0
        if state.active >= max_concurrent:
            raise HTTPException(
                status_code=429,
                detail="현재 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
                headers={"Retry-After": "5"},
            )
        state.active += 1

    try:
        yield
    finally:
        async with _lock:
            state.active = max(0, state.active - 1)


def usage_snapshot() -> dict[str, dict[str, int | str]]:
    """Return a privacy-safe snapshot for the local operations endpoint."""
    snapshot = {
        name: {
            "day": state.day.isoformat(),
            "active": state.active,
            "used": state.used,
        }
        for name, state in _states.items()
    }
    database_path = settings.USAGE_DB_PATH
    if not database_path or not Path(database_path).is_file():
        return snapshot

    try:
        with sqlite3.connect(database_path, timeout=1.0) as connection:
            rows = connection.execute(
                "SELECT name, day, used FROM daily_usage"
            ).fetchall()
    except sqlite3.Error:
        return snapshot

    for name, day, used in rows:
        current = snapshot.setdefault(
            str(name),
            {"day": str(day), "active": 0, "used": int(used)},
        )
        if str(day) >= str(current["day"]):
            current["day"] = str(day)
            current["used"] = int(used)
    return snapshot
