import starlette.config as _starlette_config
from dotenv import dotenv_values as _dotenv_values


def _read_file_utf8(self, file: str) -> dict:
    """cp949 오류 방지를 위한 UTF-8 전용 .env 파서."""
    try:
        return {k: v for k, v in _dotenv_values(file, encoding="utf-8").items() if v is not None}
    except FileNotFoundError:
        return {}


_starlette_config.Config._read_file = _read_file_utf8  # type: ignore[method-assign]

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
