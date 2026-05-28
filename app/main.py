"""
BITBOX 백엔드 진입점

FastAPI 애플리케이션을 초기화하고 미들웨어·라우터를 등록합니다.
서버 시작 시 환경변수 유효성을 검사하고, 기본 출발지 누락 경고를 출력합니다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.schemas import HealthResponse
from app.api.gateway import router as gateway_router
from app.core.config import settings, validate_required_settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.services.core.http_client import close_http_client
from app.services.core.openai_client import close_openai_client
from app.services.core.settings_helper import is_mock_mode

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await close_http_client()
        await close_openai_client()

# ---------------------------------------------------------------------------
# 시작 시 필수 환경변수 검증
# mock 모드: API 키 없이 실행 가능 / real 모드: 4개 API 키 필수
# ---------------------------------------------------------------------------
validate_required_settings()

# 기본 출발지가 전혀 설정되지 않은 경우 경고 — 사용자가 항상 출발지를 말해야 함
if not settings.DEFAULT_ORIGIN_NAME and not settings.DEFAULT_ORIGIN_X and not settings.ORIGIN_X:
    _logger.warning(
        "기본 출발지가 설정되지 않았습니다. "
        "사용자가 매번 출발지를 말해야 합니다. "
        ".env에 DEFAULT_ORIGIN_NAME 또는 DEFAULT_ORIGIN_X/Y를 설정하면 자동 출발지를 사용할 수 있습니다."
    )

# ---------------------------------------------------------------------------
# CORS 허용 출처 파싱
# CORS_ALLOWED_ORIGINS=* 이면 모든 출처 허용 (개발용)
# 특정 도메인만 허용하려면 쉼표로 구분: "https://a.com,https://b.com"
# ---------------------------------------------------------------------------
_cors_origins = (
    [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",")]
    if settings.CORS_ALLOWED_ORIGINS != "*"
    else ["*"]
)

# ---------------------------------------------------------------------------
# FastAPI 앱 생성
# ---------------------------------------------------------------------------
app = FastAPI(
    title="BITBOX Voice Transit Assistant Backend",
    description="음성 기반 버스/교통 안내 시스템 백엔드 API",
    version="1.0.0",
    lifespan=lifespan,
)

# IP 기반 Rate Limiting (slowapi) — 분당 최대 요청 수를 gateway에서 제한
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 미들웨어 — 라즈베리파이 클라이언트 및 브라우저 테스트 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# API 라우터 등록 — /api/process 엔드포인트
app.include_router(gateway_router, prefix="/api", tags=["Gateway"])


# ---------------------------------------------------------------------------
# 헬스체크 엔드포인트
# 서버 상태와 API 키 설정 여부를 반환합니다.
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    body = {
        "status": "ok",
        "env": settings.APP_ENV,
        "mock_mode": is_mock_mode(),
        "api_keys_configured": None,
    }

    if settings.APP_ENV != "prod":
        body["api_keys_configured"] = {
            "openai": bool(settings.OPENAI_API_KEY),
            "kakao": bool(settings.KAKAO_REST_API_KEY),
            "odsay": bool(settings.ODSAY_API_KEY),
            "public_data": bool(settings.PUBLIC_DATA_SERVICE_KEY),
        }

    return HealthResponse(**body)
