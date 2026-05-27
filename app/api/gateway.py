import asyncio
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.services.pipeline import build_timeout_error_response, run_pipeline

router = APIRouter()
logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/mp4",
}


@router.post("/process")
@limiter.limit("10/minute")
async def process_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """음성 파일을 받아 전체 백엔드 파이프라인을 실행합니다."""

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 오디오 형식입니다: {file.content_type}",
        )

    audio_bytes = await file.read()

    max_size = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"오디오 파일 크기는 {settings.MAX_AUDIO_SIZE_MB}MB 이하여야 합니다.",
        )

    request_id = uuid.uuid4().hex[:8]
    logger.info("[%s] Request started: file=%s size=%d", request_id, file.filename, len(audio_bytes))

    try:
        result = await asyncio.wait_for(
            run_pipeline(
                audio_bytes=audio_bytes,
                filename=file.filename or "audio.wav",
                request_id=request_id,
            ),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        logger.info("[%s] Request completed: status=%s", request_id, result.get("status"))
        return result

    except asyncio.TimeoutError:
        logger.exception("[%s] Pipeline timeout", request_id)
        result = build_timeout_error_response()
        result["request_id"] = request_id
        return result
