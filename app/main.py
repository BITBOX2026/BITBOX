import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.gateway import router as gateway_router
from app.core.config import settings, validate_required_settings
from app.core.rate_limiter import limiter
from app.services.settings_helper import is_mock_mode

_logger = logging.getLogger(__name__)

validate_required_settings()

if (
    not settings.DEFAULT_ORIGIN_NAME
    and not settings.DEFAULT_ORIGIN_X
    and not settings.ORIGIN_X
):
    _logger.warning(
        "No default origin configured — users must always specify a departure point. "
        "Set DEFAULT_ORIGIN_NAME or DEFAULT_ORIGIN_X/Y in .env to enable auto-origin."
    )

_cors_origins = (
    [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",")]
    if settings.CORS_ALLOWED_ORIGINS != "*"
    else ["*"]
)

app = FastAPI(
    title="BITBOX Voice Transit Assistant Backend",
    description="음성 기반 버스/교통 안내 시스템 백엔드 API",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(gateway_router, prefix="/api", tags=["Gateway"])


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "mock_mode": is_mock_mode(),
        "api_keys_configured": {
            "openai": bool(settings.OPENAI_API_KEY),
            "kakao": bool(settings.KAKAO_REST_API_KEY),
            "odsay": bool(settings.ODSAY_API_KEY),
            "public_data": bool(settings.PUBLIC_DATA_SERVICE_KEY),
        },
    }
