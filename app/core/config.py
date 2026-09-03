"""
전역 환경변수 설정

pydantic-settings의 BaseSettings를 사용합니다.
.env 파일 또는 OS 환경변수에서 값을 자동으로 읽어옵니다.
설정 항목 설명은 .env.example 파일을 참고하세요.
"""

import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # -------------------------------------------------------------------------
    # 실행 환경
    # -------------------------------------------------------------------------
    APP_ENV: str = "local"
    # true: 외부 API 호출 없이 mock 데이터로 동작 (개발/테스트용)
    # false: 실제 OpenAI / Kakao / ODsay / 공공데이터 API 호출
    USE_MOCK_EXTERNALS: bool = True

    # -------------------------------------------------------------------------
    # 외부 API 키
    # -------------------------------------------------------------------------
    OPENAI_API_KEY: str | None = None        # STT / LLM / TTS
    KAKAO_REST_API_KEY: str | None = None    # 장소명 → 좌표 변환
    ODSAY_API_KEY: str | None = None         # 버스 전용 경로 조회
    PUBLIC_DATA_SERVICE_KEY: str | None = None  # 실시간 버스 도착 정보
    SEOUL_BUS_API_KEY: str | None = None

    # -------------------------------------------------------------------------
    # 기기 설치 위치 (버스 정류장 고정 설치용)
    # DEFAULT_ORIGIN_NAME 설정 시: Kakao API로 좌표 자동 변환
    # DEFAULT_ORIGIN_X/Y 직접 입력 시: Kakao API 호출 없이 사용
    # 모두 비어 있으면: 사용자가 출발지를 직접 말해야 함
    # -------------------------------------------------------------------------
    DEFAULT_ORIGIN_NAME: str | None = None
    DEFAULT_ORIGIN_X: str | None = None
    DEFAULT_ORIGIN_Y: str | None = None
    ORIGIN_X: str | None = None  # 하위 호환 유지용 구 변수명
    ORIGIN_Y: str | None = None
    DEFAULT_BUS_STOP_NAME: str = "잠실역"
    DEFAULT_BUS_STATION_ID: str | None = None

    # -------------------------------------------------------------------------
    # AI 모델 설정
    # -------------------------------------------------------------------------
    STT_MODEL: str = "gpt-4o-mini-transcribe"
    LLM_MODEL: str = "gpt-4o-mini"
    INTENT_FAST_PATH_ENABLED: bool = True
    # 말투는 `speed` 로 숫자를 깎기보다 `TTS_INSTRUCTIONS` 로 지시합니다. 속도를
    # 0.85 로 낮춘 예전 설정은 또박또박이 아니라 늘어지게 들려, 오히려 기계 같다는
    # 인상을 줬습니다. gpt-4o-mini-tts 는 말투 지시를 받아 억양까지 조절합니다.
    TTS_MODEL: str = "gpt-4o-mini-tts"
    TTS_VOICE: str = "sage"
    TTS_INSTRUCTIONS: str = (
        "정류장 안내 방송처럼 말하세요. 어르신이 편하게 알아들을 수 있도록 또박또박, 천천히, 따뜻하고 차분한 목소리로 읽습니다. 기계적으로 끊지 말고 자연스러운 문장 억양을 유지하고, 숫자와 노선 번호는 특히 분명하게 발음하세요."
    )
    # 아래 속도는 지시를 지원하지 않는 tts-1 계열을 쓸 때만 적용됩니다.
    TTS_SPEED: float = 0.85  # 노인 사용자 대상 — 기본보다 약간 느리게 (0.25~4.0)
    # 파일 경로를 지정하면 내장 프롬프트 대신 해당 파일을 사용합니다.
    LLM_SYSTEM_PROMPT_FILE: str | None = None

    # -------------------------------------------------------------------------
    # 서버 동작 설정
    # -------------------------------------------------------------------------
    MAX_AUDIO_SIZE_MB: int = 10       # 업로드 허용 최대 오디오 파일 크기 (MB)
    REQUEST_TIMEOUT_SECONDS: int = 30  # 파이프라인 전체 타임아웃 (초)
    EXTERNAL_HTTP_TIMEOUT_SECONDS: float = 8.0
    PLACE_REQUEST_TIMEOUT_SECONDS: float = 7.0
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    RATE_LIMIT_ENABLED: bool = True
    API_AUTH_TOKEN: str | None = None   # 설정 시 /api/process 호출에 토큰 필요
    RELEASE_SHA: str | None = None
    USAGE_DB_PATH: str | None = None
    TTS_TIMEOUT_SECONDS: int = 15       # TTS 단독 타임아웃 (초, 콜드 스타트 포함)
    OPENAI_TIMEOUT_SECONDS: float = 20.0
    OPENAI_MAX_RETRIES: int = 0
    # 음성 파이프라인의 단계별 상한입니다. 이 값이 없으면 느린(실패가 아닌) OpenAI
    # 호출 하나가 전체 예산을 다 써, 이용자는 원인을 알 수 없는 일반 타임아웃만
    # 보게 됩니다. 합계는 REQUEST_TIMEOUT_SECONDS 보다 작아야 합니다.
    STT_TIMEOUT_SECONDS: float = 12.0
    LLM_TIMEOUT_SECONDS: float = 10.0
    # LLM 단계는 파싱 실패에 한해 한 번 더 시도합니다. 한 번의 시도가 단계 예산의
    # 절반을 넘으면 그 재시도는 시작만 하고 잘려, 아무 일도 하지 못합니다.
    LLM_ATTEMPT_TIMEOUT_SECONDS: float = 4.0
    LLM_RETRY_WAIT_SECONDS: float = 0.5
    ALLOW_KNOWN_PLACE_FALLBACK: bool | None = None
    VOICE_MAX_CONCURRENT_REQUESTS: int = 4
    VOICE_DAILY_REQUEST_LIMIT: int = 500
    ROUTE_MAX_CONCURRENT_REQUESTS: int = 12
    # 사용자 경로 요청 수가 아니라 실제 ODsay HTTP 시도 횟수를 제한합니다.
    # 재시도도 제공자 호출 1회이므로 _odsay_fetch 내부에서 매번 차감합니다.
    ODSAY_MAX_CONCURRENT_REQUESTS: int = 3
    ODSAY_DAILY_CALL_LIMIT: int = 30
    # 브라우저가 한국어를 말하지 못하는 기기에서만 쓰이는 서버 음성 합성 한도.
    # 같은 문구가 반복되어 캐시 적중률이 높으므로 실제 호출은 이보다 훨씬 적습니다.
    SPEECH_DAILY_REQUEST_LIMIT: int = 2000
    PLACE_MAX_CONCURRENT_REQUESTS: int = 12
    PLACE_DAILY_REQUEST_LIMIT: int = 10000
    EXTERNAL_CIRCUIT_FAILURE_THRESHOLD: int = 5
    EXTERNAL_CIRCUIT_RESET_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에 정의되지 않은 키는 무시
    )


settings = Settings()

# "local"만 신뢰할 수 있는 개발 환경으로 취급합니다.
# staging/prod는 물론, 오타나 미설정으로 알 수 없는 값이 들어와도
# 항상 운영 환경 수준의 보안 검증을 적용합니다 (fail-closed).
_LOCAL_ENV = "local"


def is_local_env() -> bool:
    return settings.APP_ENV == _LOCAL_ENV


def validate_required_settings() -> None:
    """
    실행 모드에 따라 필수 환경변수를 검증합니다.

    mock 모드: API 키 없이 실행 가능 (단, 보안 관련 설정은 항상 검증)
    real 모드: OPENAI / KAKAO / ODSAY / PUBLIC_DATA 키 모두 필요
    """
    # 보안 설정 검증은 mock 모드 여부와 무관하게 항상 수행합니다.
    # (USE_MOCK_EXTERNALS=true 인 채로 실수로 prod에 배포되는 경우를 방지)
    if not is_local_env():
        if not settings.API_AUTH_TOKEN:
            raise RuntimeError(
                f"APP_ENV={settings.APP_ENV!r}에서는 API_AUTH_TOKEN 설정이 필요합니다."
            )
        if settings.CORS_ALLOWED_ORIGINS.strip() == "*":
            raise RuntimeError(
                f"APP_ENV={settings.APP_ENV!r}에서는 CORS_ALLOWED_ORIGINS='*'를 사용할 수 없습니다."
            )

    if settings.APP_ENV == "prod" and not re.fullmatch(
        r"[0-9a-f]{40}", settings.RELEASE_SHA or ""
    ):
        raise RuntimeError("APP_ENV='prod'에서는 유효한 RELEASE_SHA가 필요합니다.")

    # 아래 검증은 mock 모드에서도 그대로 적용합니다. 호출량 상한, 회로 차단,
    # 단계별 시간 예산은 외부 키가 아니라 이 서비스 내부의 동작을 규정하기
    # 때문입니다. mock 게이트 뒤에 두면 키 없이 도는 환경(CI 러너 등)에서
    # 잘못된 설정이 조용히 통과하고, 그 상태로 기동해도 아무도 막지 않습니다.
    positive_settings = (
        "VOICE_MAX_CONCURRENT_REQUESTS", "VOICE_DAILY_REQUEST_LIMIT",
        "ROUTE_MAX_CONCURRENT_REQUESTS",
        "ODSAY_MAX_CONCURRENT_REQUESTS", "ODSAY_DAILY_CALL_LIMIT",
        "PLACE_MAX_CONCURRENT_REQUESTS", "PLACE_DAILY_REQUEST_LIMIT",
        "SPEECH_DAILY_REQUEST_LIMIT",
        "EXTERNAL_CIRCUIT_FAILURE_THRESHOLD", "EXTERNAL_CIRCUIT_RESET_SECONDS",
    )
    for name in positive_settings:
        if getattr(settings, name) < 1:
            raise RuntimeError(f"{name}은 1 이상이어야 합니다.")

    if settings.OPENAI_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("OPENAI_TIMEOUT_SECONDS는 0보다 커야 합니다.")
    if settings.OPENAI_MAX_RETRIES < 0:
        raise RuntimeError("OPENAI_MAX_RETRIES는 0 이상이어야 합니다.")
    if settings.EXTERNAL_HTTP_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("EXTERNAL_HTTP_TIMEOUT_SECONDS는 0보다 커야 합니다.")
    if settings.PLACE_REQUEST_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("PLACE_REQUEST_TIMEOUT_SECONDS는 0보다 커야 합니다.")

    for name in (
        "STT_TIMEOUT_SECONDS",
        "LLM_TIMEOUT_SECONDS",
        "LLM_ATTEMPT_TIMEOUT_SECONDS",
        "LLM_RETRY_WAIT_SECONDS",
    ):
        if getattr(settings, name) <= 0:
            raise RuntimeError(f"{name}은 0보다 커야 합니다.")

    # 두 번의 시도와 그 사이 대기가 LLM 단계 예산 안에 들어가야, 재시도가 실제로
    # 완료될 기회를 얻습니다. 넘치면 재시도는 시작만 하고 잘립니다.
    llm_retry_budget = (
        settings.LLM_ATTEMPT_TIMEOUT_SECONDS * 2 + settings.LLM_RETRY_WAIT_SECONDS
    )
    if llm_retry_budget > settings.LLM_TIMEOUT_SECONDS:
        raise RuntimeError(
            "LLM_TIMEOUT_SECONDS는 두 번의 시도와 재시도 대기를 담을 수 있어야 합니다."
        )

    # STT 와 LLM 만으로 전체 예산을 소진하면, 교통 조회·응답 생성이 시작되기도 전에
    # 파이프라인이 잘려 구체적 오류 대신 일반 타임아웃이 나갑니다.
    if (
        settings.STT_TIMEOUT_SECONDS + settings.LLM_TIMEOUT_SECONDS
        >= settings.REQUEST_TIMEOUT_SECONDS
    ):
        raise RuntimeError(
            "STT_TIMEOUT_SECONDS + LLM_TIMEOUT_SECONDS는 "
            "REQUEST_TIMEOUT_SECONDS보다 작아야 합니다."
        )

    # 좌표값이 있으면 숫자 형식인지 확인
    for name in ("DEFAULT_ORIGIN_X", "DEFAULT_ORIGIN_Y", "ORIGIN_X", "ORIGIN_Y"):
        _validate_optional_coordinate(name, getattr(settings, name))

    if settings.USE_MOCK_EXTERNALS:
        return

    missing = []
    if not settings.OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not settings.KAKAO_REST_API_KEY:
        missing.append("KAKAO_REST_API_KEY")
    if not settings.ODSAY_API_KEY:
        missing.append("ODSAY_API_KEY")
    if not settings.PUBLIC_DATA_SERVICE_KEY and not settings.SEOUL_BUS_API_KEY:
        missing.append("PUBLIC_DATA_SERVICE_KEY or SEOUL_BUS_API_KEY")

    if missing:
        raise RuntimeError(
            f"USE_MOCK_EXTERNALS=false 일 때 다음 환경변수가 필요합니다: {', '.join(missing)}"
        )


def _validate_optional_coordinate(name: str, value: str | None) -> None:
    """값이 있을 때만 유효한 부동소수점 숫자인지 확인합니다."""
    if not value:
        return
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name}은 숫자여야 합니다. 현재 값: {value!r}") from exc
