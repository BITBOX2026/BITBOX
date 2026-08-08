"""
전역 환경변수 설정

pydantic-settings의 BaseSettings를 사용합니다.
.env 파일 또는 OS 환경변수에서 값을 자동으로 읽어옵니다.
설정 항목 설명은 .env.example 파일을 참고하세요.
"""

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
    TTS_MODEL: str = "tts-1-hd"
    TTS_VOICE: str = "nova"
    TTS_SPEED: float = 0.85  # 노인 사용자 대상 — 기본보다 약간 느리게 (0.25~4.0)
    # 파일 경로를 지정하면 내장 프롬프트 대신 해당 파일을 사용합니다.
    LLM_SYSTEM_PROMPT_FILE: str | None = None

    # -------------------------------------------------------------------------
    # 서버 동작 설정
    # -------------------------------------------------------------------------
    MAX_AUDIO_SIZE_MB: int = 10       # 업로드 허용 최대 오디오 파일 크기 (MB)
    REQUEST_TIMEOUT_SECONDS: int = 30  # 파이프라인 전체 타임아웃 (초)
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    RATE_LIMIT_ENABLED: bool = True
    API_AUTH_TOKEN: str | None = None   # 설정 시 /api/process 호출에 토큰 필요
    TTS_TIMEOUT_SECONDS: int = 8        # TTS 단독 타임아웃 (초)
    ALLOW_KNOWN_PLACE_FALLBACK: bool | None = None
    VOICE_MAX_CONCURRENT_REQUESTS: int = 4
    VOICE_DAILY_REQUEST_LIMIT: int = 500
    ROUTE_MAX_CONCURRENT_REQUESTS: int = 12
    ROUTE_DAILY_REQUEST_LIMIT: int = 5000
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


def validate_required_settings() -> None:
    """
    실행 모드에 따라 필수 환경변수를 검증합니다.

    mock 모드: API 키 없이 실행 가능
    real 모드: OPENAI / KAKAO / ODSAY / PUBLIC_DATA 키 모두 필요
    """
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

    if settings.APP_ENV == "prod":
        if not settings.API_AUTH_TOKEN:
            raise RuntimeError("APP_ENV=prod에서는 API_AUTH_TOKEN 설정이 필요합니다.")
        if settings.CORS_ALLOWED_ORIGINS.strip() == "*":
            raise RuntimeError("APP_ENV=prod에서는 CORS_ALLOWED_ORIGINS='*'를 사용할 수 없습니다.")

    positive_settings = (
        "VOICE_MAX_CONCURRENT_REQUESTS", "VOICE_DAILY_REQUEST_LIMIT",
        "ROUTE_MAX_CONCURRENT_REQUESTS", "ROUTE_DAILY_REQUEST_LIMIT",
        "PLACE_MAX_CONCURRENT_REQUESTS", "PLACE_DAILY_REQUEST_LIMIT",
        "EXTERNAL_CIRCUIT_FAILURE_THRESHOLD", "EXTERNAL_CIRCUIT_RESET_SECONDS",
    )
    for name in positive_settings:
        if getattr(settings, name) < 1:
            raise RuntimeError(f"{name}은 1 이상이어야 합니다.")

    # 좌표값이 있으면 숫자 형식인지 확인
    for name in ("DEFAULT_ORIGIN_X", "DEFAULT_ORIGIN_Y", "ORIGIN_X", "ORIGIN_Y"):
        _validate_optional_coordinate(name, getattr(settings, name))


def _validate_optional_coordinate(name: str, value: str | None) -> None:
    """값이 있을 때만 유효한 부동소수점 숫자인지 확인합니다."""
    if not value:
        return
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name}은 숫자여야 합니다. 현재 값: {value!r}") from exc
