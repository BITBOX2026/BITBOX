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
    ODSAY_API_KEY: str | None = None         # 대중교통 경로 조회
    PUBLIC_DATA_SERVICE_KEY: str | None = None  # 실시간 버스 도착 정보

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

    # -------------------------------------------------------------------------
    # AI 모델 설정
    # -------------------------------------------------------------------------
    STT_MODEL: str = "gpt-4o-mini-transcribe"
    LLM_MODEL: str = "gpt-4o-mini"
    TTS_MODEL: str = "tts-1-hd"
    TTS_VOICE: str = "nova"
    # 파일 경로를 지정하면 내장 프롬프트 대신 해당 파일을 사용합니다.
    LLM_SYSTEM_PROMPT_FILE: str | None = None

    # -------------------------------------------------------------------------
    # 서버 동작 설정
    # -------------------------------------------------------------------------
    MAX_AUDIO_SIZE_MB: int = 10       # 업로드 허용 최대 오디오 파일 크기 (MB)
    REQUEST_TIMEOUT_SECONDS: int = 30  # 파이프라인 전체 타임아웃 (초)
    CORS_ALLOWED_ORIGINS: str = "*"    # 허용 출처 (* = 전체)

    # -------------------------------------------------------------------------
    # 라즈베리파이 클라이언트 설정
    # -------------------------------------------------------------------------
    API_URL: str = "http://127.0.0.1:8000/api/process"
    AUDIO_OUTPUT_PATH: str = "recorded_audio.wav"
    RECORD_SECONDS: int = 5
    SAMPLE_RATE: int = 16000

    model_config = SettingsConfigDict(
        env_file=".env",
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
    if not settings.PUBLIC_DATA_SERVICE_KEY:
        missing.append("PUBLIC_DATA_SERVICE_KEY")

    if missing:
        raise RuntimeError(
            f"USE_MOCK_EXTERNALS=false 일 때 다음 환경변수가 필요합니다: {', '.join(missing)}"
        )

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
