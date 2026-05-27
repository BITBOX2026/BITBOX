"""
공통 로거 팩토리

모든 모듈은 이 함수로 로거를 얻습니다.
중복 핸들러 등록을 방지하고, propagate=False로 루트 로거와 분리합니다.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    # 이미 핸들러가 등록된 로거는 그대로 반환 — 중복 출력 방지
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    )
    logger.addHandler(handler)

    # 루트 로거로 전파하지 않음 — 같은 메시지가 두 번 출력되는 현상 방지
    logger.propagate = False

    return logger
