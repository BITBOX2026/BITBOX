# 서버 환경변수와 설정값을 관리하는 파일입니다.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    서버 실행에 필요한 설정값을 관리하는 클래스입니다.

    기능:
        - .env 파일 또는 OS 환경변수에서 값을 읽습니다.
        - Mock 모드에서는 외부 API 키 없이도 서버 실행이 가능하게 합니다.
        - 실제 API 모드에서는 필수 환경변수가 없으면 서버 실행을 중단합니다.
    """

    APP_ENV: str = "local"
    USE_MOCK_EXTERNALS: bool = True

    OPENAI_API_KEY: str | None = None
    ODSAY_API_KEY: str | None = None
    KAKAO_REST_API_KEY: str | None = None

    ORIGIN_X: str | None = None
    ORIGIN_Y: str | None = None

    STT_MODEL: str = "gpt-4o-mini-transcribe"
    LLM_MODEL: str = "gpt-4o-mini"

    MAX_AUDIO_SIZE_MB: int = 25
    PIPELINE_TIMEOUT_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()


def validate_required_settings() -> None:
    """
    서버 실행 전 필수 설정값을 검증하는 함수입니다.

    기능:
        - USE_MOCK_EXTERNALS=true이면 외부 API 키 검사를 건너뜁니다.
        - USE_MOCK_EXTERNALS=false이면 실제 API 호출에 필요한 값을 검사합니다.
        - 출발지 좌표 ORIGIN_X, ORIGIN_Y는 ODsay 경로 조회에 필요하므로 함께 검사합니다.

    실제 API 모드에서 필요한 값:
        - OPENAI_API_KEY
        - ODSAY_API_KEY
        - KAKAO_REST_API_KEY
        - ORIGIN_X
        - ORIGIN_Y
    """

    if settings.USE_MOCK_EXTERNALS:
        return

    missing = []

    if not settings.OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")

    if not settings.ODSAY_API_KEY:
        missing.append("ODSAY_API_KEY")

    if not settings.KAKAO_REST_API_KEY:
        missing.append("KAKAO_REST_API_KEY")

    if not settings.ORIGIN_X:
        missing.append("ORIGIN_X")

    if not settings.ORIGIN_Y:
        missing.append("ORIGIN_Y")

    if missing:
        raise RuntimeError(f"필수 환경변수가 없습니다: {', '.join(missing)}")

    _validate_coordinate_number(
        name="ORIGIN_X",
        value=settings.ORIGIN_X,
    )

    _validate_coordinate_number(
        name="ORIGIN_Y",
        value=settings.ORIGIN_Y,
    )


def _validate_coordinate_number(name: str, value: str | None) -> None:
    """
    좌표 환경변수가 숫자로 변환 가능한지 검증하는 함수입니다.

    기능:
        - ORIGIN_X, ORIGIN_Y가 숫자가 아니면 서버 실행을 중단합니다.
        - 실제 대한민국 범위 검증은 transport_service.py에서 한 번 더 수행합니다.

    입력:
        name:
            - 환경변수 이름입니다.
            - 예: "ORIGIN_X"

        value:
            - 환경변수 값입니다.
            - 예: "126.970626"

    반환:
        None:
            - 정상 값이면 아무것도 반환하지 않습니다.
    """

    try:
        float(value)

    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name}는 숫자 형태여야 합니다. 입력값: {value}") from exc