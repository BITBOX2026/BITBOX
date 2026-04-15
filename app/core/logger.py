# 서버 로그 출력 설정 (디버깅 및 에러 추적용)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("app")