import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.logger import get_logger
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
async def process_audio(file: UploadFile = File(...)) -> dict:
    """음성 파일을 받아 전체 백엔드 파이프라인을 실행합니다."""

    if file.content_type not in ALLOWED_CONTENT_TYPES:
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

    try:
        result = await asyncio.wait_for(
            run_pipeline(
                audio_bytes=audio_bytes,
                filename=file.filename or "audio.wav",
            ),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        return result

    except asyncio.TimeoutError:
        logger.exception("Pipeline timeout")
        return build_timeout_error_response()
