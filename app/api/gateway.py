"""
API Gateway — 음성 파일 수신 및 파이프라인 실행

클라이언트(라즈베리파이)가 녹음한 오디오를 받아 파이프라인을 실행하고
구조화된 JSON 응답(교통 안내 + TTS 오디오)을 반환합니다.

엔드포인트: POST /api/process
"""

import asyncio
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.services.pipeline import build_timeout_error_response, run_pipeline

router = APIRouter()
logger = get_logger(__name__)

# 허용할 오디오 MIME 타입 목록
ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/mp4",
}


@router.post("/process")
@limiter.limit("10/minute")  # IP당 분당 최대 10회 요청 허용
async def process_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """
    음성 파일을 받아 전체 백엔드 파이프라인을 실행합니다.

    처리 흐름:
    1. 파일 형식 / 크기 검증
    2. STT → LLM → 검증 → 교통 API → TTS (pipeline.py)
    3. 구조화된 JSON 응답 반환
    """

    # MIME 타입 확인 (세미콜론 이후 파라미터 제거 후 비교)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 오디오 형식입니다: {file.content_type}",
        )

    audio_bytes = await file.read()

    # 파일 크기 확인 (기본 10MB)
    max_size = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"오디오 파일 크기는 {settings.MAX_AUDIO_SIZE_MB}MB 이하여야 합니다.",
        )

    # 요청별 고유 ID 생성 — 로그 추적에 사용
    request_id = uuid.uuid4().hex[:8]
    logger.info(
        "[%s] 요청 시작: file=%s size=%d bytes",
        request_id, file.filename, len(audio_bytes),
    )

    try:
        # 전체 파이프라인에 타임아웃 적용 (기본 30초)
        result = await asyncio.wait_for(
            run_pipeline(
                audio_bytes=audio_bytes,
                filename=file.filename or "audio.wav",
                request_id=request_id,
            ),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        logger.info("[%s] 요청 완료: status=%s", request_id, result.get("status"))
        return result

    except asyncio.TimeoutError:
        logger.exception("[%s] 파이프라인 타임아웃", request_id)
        result = build_timeout_error_response()
        result["request_id"] = request_id
        return result
