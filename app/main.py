# FastAPI 앱을 생성하고 API 라우터, CORS, Health Check를 등록하는 파일입니다.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.gateway import router as gateway_router
from app.core.config import validate_required_settings

# 서버 시작 시 환경변수 검증을 수행합니다.
# Mock 모드에서는 API 키가 없어도 통과합니다.
# 실제 API 모드에서는 필수 키가 없으면 서버 실행을 중단합니다.
validate_required_settings()

app = FastAPI(
    title="BITBOX Voice Transit Assistant Backend",
    description="음성 기반 버스/교통 안내 시스템 백엔드 API",
    version="1.0.0",
)

# 개발 단계에서는 전체 허용합니다.
# 실제 배포 단계에서는 allow_origins를 특정 도메인 또는 라즈베리파이 주소로 제한하는 것이 좋습니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/process 라우터 등록
app.include_router(gateway_router, prefix="/api", tags=["Gateway"])


@app.get("/health")
def health_check() -> dict:
    """
    서버 상태를 확인하는 Health Check API입니다.

    기능:
        - 서버가 정상 실행 중인지 확인합니다.
        - 라즈베리파이 또는 운영자가 서버 연결 상태를 점검할 때 사용합니다.

    반환:
        dict:
            - 서버 상태 메시지입니다.
    """

    return {
        "status": "ok",
        "message": "server is running",
    }