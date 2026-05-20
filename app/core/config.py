from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """BITBOX 서버와 라즈베리파이 클라이언트가 공유하는 환경변수 설정입니다."""

    APP_ENV: str = "local"
    USE_MOCK_EXTERNALS: bool = True

    OPENAI_API_KEY: str | None = None
    KAKAO_REST_API_KEY: str | None = None
    ODSAY_API_KEY: str | None = None
    PUBLIC_DATA_SERVICE_KEY: str | None = None

    # 새 변수명입니다. 현재 route 요청은 음성 출발지를 우선 사용합니다.
    DEFAULT_ORIGIN_X: str | None = None
    DEFAULT_ORIGIN_Y: str | None = None

    # 기존 .env와의 호환을 위해 남겨둔 구 변수명입니다.
    ORIGIN_X: str | None = None
    ORIGIN_Y: str | None = None

    STT_MODEL: str = "gpt-4o-mini-transcribe"
    LLM_MODEL: str = "gpt-4o-mini"

    MAX_AUDIO_SIZE_MB: int = 10
    REQUEST_TIMEOUT_SECONDS: int = 30

    # 기존 코드/환경변수 호환용입니다. 새 코드는 REQUEST_TIMEOUT_SECONDS를 사용합니다.
    PIPELINE_TIMEOUT_SECONDS: int | None = None

    API_URL: str = "http://127.0.0.1:8000/api/process"
    AUDIO_OUTPUT_PATH: str = "recorded_audio.wav"
    RECORD_SECONDS: int = 5
    SAMPLE_RATE: int = 16000

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()


def validate_required_settings() -> None:
    """
    실행 모드에 따라 필수 환경변수를 검증합니다.

    mock mode에서는 API 키가 비어 있어도 서버가 실행되어야 합니다.
    real mode에서는 현재 구현된 STT/LLM, Kakao, ODsay 호출에 필요한 키만 필수로 봅니다.
    """

    if settings.USE_MOCK_EXTERNALS:
        return

    missing_messages = []

    if not settings.OPENAI_API_KEY:
        missing_messages.append("OPENAI_API_KEY is required when USE_MOCK_EXTERNALS=false")

    if not settings.KAKAO_REST_API_KEY:
        missing_messages.append(
            "KAKAO_REST_API_KEY is required when USE_MOCK_EXTERNALS=false"
        )

    if not settings.ODSAY_API_KEY:
        missing_messages.append("ODSAY_API_KEY is required when USE_MOCK_EXTERNALS=false")

    if missing_messages:
        raise RuntimeError("; ".join(missing_messages))

    _validate_optional_coordinate("DEFAULT_ORIGIN_X", settings.DEFAULT_ORIGIN_X)
    _validate_optional_coordinate("DEFAULT_ORIGIN_Y", settings.DEFAULT_ORIGIN_Y)
    _validate_optional_coordinate("ORIGIN_X", settings.ORIGIN_X)
    _validate_optional_coordinate("ORIGIN_Y", settings.ORIGIN_Y)


def _validate_optional_coordinate(name: str, value: str | None) -> None:
    """빈 좌표는 허용하고, 값이 있을 때만 숫자 형식인지 확인합니다."""

    if not value:
        return

    try:
        float(value)

    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a number. value={value}") from exc
