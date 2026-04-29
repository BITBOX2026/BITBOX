# 서버 전체에서 사용할 logger를 생성하는 파일입니다.

import logging


def get_logger(name: str) -> logging.Logger:
    """
    모듈별 logger를 생성하는 함수입니다.

    기능:
        - 같은 이름의 logger가 이미 있으면 기존 logger를 반환합니다.
        - 중복 handler 생성을 방지합니다.
        - 로그 형식을 통일합니다.

    입력:
        name:
            - 보통 __name__ 값을 전달합니다.

    반환:
        logging.Logger:
            - 설정된 logger 객체입니다.
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger