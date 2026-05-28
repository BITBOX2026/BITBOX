"""
설정값 조회 헬퍼

OS 환경변수 → pydantic settings → default 순으로 값을 탐색합니다.
테스트 중 환경변수를 바꿀 때는 clear_settings_cache()를 호출해야
is_mock_mode()가 새 값을 반영합니다.
"""

import os
from functools import lru_cache
from typing import Any

from app.core.config import settings


def get_setting(name: str, default: Any = None) -> Any:
    """
    설정값을 우선순위에 따라 반환합니다.

    우선순위: os.environ > pydantic Settings > default
    """
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    value = getattr(settings, name, None)
    if value is not None:
        return value

    return default


def get_bool_setting(name: str, default: bool = False) -> bool:
    """환경변수/설정값을 bool로 안전하게 해석합니다."""
    value = get_setting(name, default)

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


@lru_cache(maxsize=1)
def is_mock_mode() -> bool:
    """
    외부 API 호출 없이 mock 데이터를 사용할지 여부를 반환합니다.

    결과를 캐싱하므로 테스트 도중 USE_MOCK_EXTERNALS를 바꾸면
    clear_settings_cache()를 먼저 호출해야 합니다.
    """
    return get_bool_setting("USE_MOCK_EXTERNALS", True)


def clear_settings_cache() -> None:
    """is_mock_mode() 캐시를 초기화합니다. 테스트 코드에서만 사용합니다."""
    is_mock_mode.cache_clear()
