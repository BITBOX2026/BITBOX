# FastAPI 실행 + CORS 설정 + Health Check

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.gateway import router

app = FastAPI(
    title="Voice Bus Assistant API",
    version="1.0.0"
)

# CORS (개발용: 전체 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(router, prefix="/api")


# 서버 상태 확인용
@app.get("/health")
async def health_check():
    return {"status": "ok"}