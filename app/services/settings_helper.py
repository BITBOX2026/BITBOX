import os
from functools import lru_cache
from typing import Any

from app.core.config import settings


def get_setting(name: str, default: Any = None) -> Any:
    """OS 환경변수 → settings → default 순으로 설정값을 반환합니다."""

    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    value = getattr(settings, name, None)
    if value is not None:
        return value

    return default


@lru_cache(maxsize=1)
def is_mock_mode() -> bool:
    """USE_MOCK_EXTERNALS 설정값을 반환합니다.

    lru_cache를 사용하므로 테스트 중 환경변수를 바꿨다면 clear_settings_cache()를 호출하세요.
    """

    value = get_setting("USE_MOCK_EXTERNALS", True)

    if isinstance(value, bool):
        return value

    return str(value).lower() in {"true", "1", "yes", "y"}


def clear_settings_cache() -> None:
    is_mock_mode.cache_clear()
