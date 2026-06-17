"""
공통 로거 팩토리

모든 모듈은 이 함수로 로거를 얻습니다.
중복 핸들러 등록을 방지하고, propagate=False로 루트 로거와 분리합니다.
"""

import io
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Windows CP949 환경에서 한글 로그가 깨지지 않도록 UTF-8 스트림 사용
    stream = _utf8_stderr()
    handler = logging.StreamHandler(stream=stream)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    )
    logger.addHandler(handler)

    logger.propagate = False

    return logger


def _utf8_stderr() -> io.TextIOWrapper:
    """sys.stderr의 바이너리 버퍼를 UTF-8로 감싼 스트림을 반환합니다."""
    stderr = sys.stderr
    if hasattr(stderr, "buffer"):
        return io.TextIOWrapper(stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    return stderr
