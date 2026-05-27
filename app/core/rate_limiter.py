"""
IP 기반 요청 속도 제한 (Rate Limiter)

slowapi + starlette를 사용하며, starlette가 .env를 읽을 때
Windows의 기본 인코딩(cp949)으로 인한 한글 깨짐을 방지하기 위해
Config._read_file을 UTF-8 전용으로 monkey-patch합니다.

사용 예시 (gateway.py):
    @limiter.limit("10/minute")
    async def process_audio(request: Request, ...):
        ...
"""

import starlette.config as _starlette_config
from dotenv import dotenv_values as _dotenv_values


def _read_file_utf8(self, file: str) -> dict:
    """UTF-8로 .env 파일을 읽습니다. 파일이 없으면 빈 dict를 반환합니다."""
    try:
        return {
            k: v
            for k, v in _dotenv_values(file, encoding="utf-8").items()
            if v is not None
        }
    except FileNotFoundError:
        return {}


# starlette의 기본 파일 읽기를 UTF-8 버전으로 교체
_starlette_config.Config._read_file = _read_file_utf8  # type: ignore[method-assign]

from slowapi import Limiter
from slowapi.util import get_remote_address

# 클라이언트 IP를 키로 삼아 분당 요청 수를 제한합니다.
limiter = Limiter(key_func=get_remote_address)
