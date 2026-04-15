# 환경 변수(API 키 등) 관리 (현재는 단순 조회만 수행)

import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
ODSAY_API_KEY = os.getenv("ODSAY_API_KEY")