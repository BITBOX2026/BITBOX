# FastAPI 애플리케이션 실행 및 API 라우터 등록

from fastapi import FastAPI
from app.api.gateway import router

app = FastAPI(
    title="Voice Bus Assistant API",
    version="1.0.0"
)

app.include_router(router, prefix="/api")