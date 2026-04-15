# 환경 변수(API 키) 관리 + Fail-Fast 적용

import os


def get_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"{var_name} 환경 변수가 설정되지 않았습니다.")
    return value


# 필수 키 (없으면 서버 실행 실패)
OPENAI_API_KEY = get_env("OPENAI_API_KEY")
ODSAY_API_KEY = get_env("ODSAY_API_KEY")

# 선택 키 (없어도 실행 가능)
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")