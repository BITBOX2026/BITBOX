"""
BITBOX 백엔드 진입점

FastAPI 애플리케이션을 초기화하고 미들웨어·라우터를 등록합니다.
서버 시작 시 환경변수 유효성을 검사하고, 기본 출발지 누락 경고를 출력합니다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.gateway import router as gateway_router
from app.api.schemas import HealthResponse, ReadinessResponse
from app.core.config import is_local_env, settings, validate_required_settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.core.request_context import request_context_middleware
from app.core.runtime_metrics import runtime_snapshot
from app.core.usage_guard import usage_snapshot
from app.routers.bus import router as bus_router
from app.routers.place import router as place_router
from app.routers.station import router as station_router
from app.services.core.http_client import close_http_client
from app.services.core.http_utils import circuit_snapshot
from app.services.core.openai_client import close_openai_client
from app.services.core.settings_helper import is_mock_mode

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작 시 필수 환경변수 검증 — import 시점이 아닌 서버 기동 시점에 실행
    validate_required_settings()

    if not settings.DEFAULT_ORIGIN_NAME and not settings.DEFAULT_ORIGIN_X and not settings.ORIGIN_X:
        _logger.warning(
            "기본 출발지가 설정되지 않았습니다. "
            "사용자가 매번 출발지를 말해야 합니다. "
            ".env에 DEFAULT_ORIGIN_NAME 또는 DEFAULT_ORIGIN_X/Y를 설정하면 자동 출발지를 사용할 수 있습니다."
        )

    try:
        yield
    finally:
        await close_http_client()
        await close_openai_client()

# ---------------------------------------------------------------------------
# CORS 허용 출처 파싱
# CORS_ALLOWED_ORIGINS=* 이면 모든 출처 허용 (개발용)
# 특정 도메인만 허용하려면 쉼표로 구분: "https://a.com,https://b.com"
# ---------------------------------------------------------------------------
_frontend_dev_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
_cors_origins = (
    ["*"]
    if settings.CORS_ALLOWED_ORIGINS == "*"
    else sorted(
        {
            *[o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
            # 오직 "local" 환경에서만 개발 서버 오리진을 추가합니다.
            # staging 등 알 수 없는 APP_ENV 값은 prod와 동일하게 취급 (fail-closed).
            *(_frontend_dev_origins if is_local_env() else set()),
        }
    )
)

# ---------------------------------------------------------------------------
# FastAPI 앱 생성
# ---------------------------------------------------------------------------
app = FastAPI(
    title="BITBOX Voice Transit Assistant Backend",
    description="음성 기반 버스/교통 안내 시스템 백엔드 API",
    version="1.2.0",
    lifespan=lifespan,
)
app.middleware("http")(request_context_middleware)

# IP 기반 Rate Limiting (slowapi) — 분당 최대 요청 수를 gateway에서 제한
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 미들웨어 — 라즈베리파이 클라이언트 및 브라우저 테스트 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type", "X-BITBOX-Token", "X-Request-ID"],
)

# API 라우터 등록 — /api/process 엔드포인트
app.include_router(gateway_router, prefix="/api", tags=["Gateway"])
app.include_router(bus_router, prefix="/api/bus", tags=["Bus"])
app.include_router(place_router, prefix="/api/places", tags=["Places"])
app.include_router(station_router, prefix="/api/station", tags=["Station"])


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
        "version": app.version,
        "capabilities": [
            "bus_arrivals",
            "bus_only_routes",
            "place_suggestions",
            "voice_processing",
        ],
        "api_keys_configured": None,
    }

    if is_local_env():
        body["api_keys_configured"] = {
            "openai": bool(settings.OPENAI_API_KEY),
            "kakao": bool(settings.KAKAO_REST_API_KEY),
            "odsay": bool(settings.ODSAY_API_KEY),
            # PUBLIC_DATA_SERVICE_KEY와 SEOUL_BUS_API_KEY 둘 중 하나만 있어도 버스 API 동작
            "bus_api": bool(settings.PUBLIC_DATA_SERVICE_KEY or settings.SEOUL_BUS_API_KEY),
        }

    return HealthResponse(**body)


@app.get("/ready", response_model=ReadinessResponse)
def readiness_check() -> ReadinessResponse:
    """Report readiness after startup validation has completed."""
    return ReadinessResponse(status="ready", version=app.version)


@app.get("/internal/status", include_in_schema=False)
async def internal_status(request: Request) -> dict[str, object]:
    """Expose privacy-safe runtime state only to local EC2 operators."""
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "status": "ok",
        "version": app.version,
        "runtime": runtime_snapshot(),
        "usage": usage_snapshot(),
        "circuits": circuit_snapshot(),
    }
