# app.core.config의 설정값과 환경변수를 안전하게 읽기 위한 보조 파일입니다.

import os
from functools import lru_cache
from typing import Any

from app.core.config import settings


def get_setting(name: str, default: Any = None) -> Any:
    """
    설정값을 안전하게 가져오는 함수입니다.

    기능:
        - OS 환경변수에 값이 있으면 우선 사용합니다.
        - 환경변수에 값이 없으면 app.core.config.settings 값을 사용합니다.
        - 둘 다 없으면 default 값을 반환합니다.

    이유:
        - 유닛 테스트에서 os.environ 값을 바꿔가며 테스트하기 쉽습니다.
        - .env 또는 배포 환경변수로 설정을 덮어쓸 수 있습니다.

    사용 예:
        api_key = get_setting("OPENAI_API_KEY")
        timeout = get_setting("API_TIMEOUT", 10)
    """

    env_value = os.getenv(name)

    if env_value is not None:
        return env_value

    value = getattr(settings, name, None)

    if value is not None:
        return value

    return default


@lru_cache(maxsize=1)
def is_mock_mode() -> bool:
    """
    외부 API를 실제 호출할지, mock 데이터를 사용할지 판단하는 함수입니다.

    기능:
        - USE_MOCK_EXTERNALS=true이면 OpenAI, ODsay, Kakao API를 실제 호출하지 않습니다.
        - USE_MOCK_EXTERNALS=false이면 실제 외부 API 호출을 시도합니다.

    주의:
        - lru_cache를 사용하므로 서버 실행 중 설정값을 바꿔도 바로 반영되지 않습니다.
        - 설정을 바꿨다면 서버를 재시작해야 합니다.
        - 유닛 테스트에서 환경변수를 바꿔가며 테스트할 때는 clear_settings_cache()를 호출하세요.
    """

    value = get_setting("USE_MOCK_EXTERNALS", True)

    if isinstance(value, bool):
        return value

    return str(value).lower() in {"true", "1", "yes", "y"}


def clear_settings_cache() -> None:
    """
    설정 관련 캐시를 초기화하는 함수입니다.

    기능:
        - 유닛 테스트에서 환경변수 값을 바꾼 뒤 캐시를 비울 때 사용합니다.
        - 실제 운영 코드에서는 일반적으로 사용할 필요가 없습니다.

    사용 예:
        clear_settings_cache()
    """

    is_mock_mode.cache_clear()