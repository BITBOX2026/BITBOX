from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.gateway import router as gateway_router
from app.core.config import validate_required_settings

validate_required_settings()

app = FastAPI(
    title="BITBOX Voice Transit Assistant Backend",
    description="음성 기반 버스/교통 안내 시스템 백엔드 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(gateway_router, prefix="/api", tags=["Gateway"])


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "message": "server is running"}
