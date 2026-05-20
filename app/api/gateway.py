# 라즈베리파이에서 전송한 음성 파일을 받고 파이프라인을 호출하는 API 라우터입니다.

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.logger import get_logger
from app.services.pipeline import run_pipeline

router = APIRouter()
logger = get_logger(__name__)

# 서버에서 허용할 오디오 MIME 타입입니다.
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
    """
    음성 파일을 받아 전체 백엔드 파이프라인을 실행하는 API입니다.

    기능:
        - 라즈베리파이에서 업로드한 음성 파일을 받습니다.
        - 파일 형식과 크기를 검증합니다.
        - run_pipeline()을 호출합니다.
        - 파이프라인 결과 JSON을 그대로 반환합니다.

    요청 형식:
        multipart/form-data
        file: audio file

    반환:
        dict:
            - status, message, data 구조의 JSON 응답입니다.
    """

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

        return {
            "status": "error",
            "message": "처리 시간이 초과되었습니다. 다시 시도해 주세요.",
            "data": {
                "transcript": None,
                "intent": None,
                "origin": None,
                "destination": None,
                "transport_mode": None,
                "bus_number": None,
                "arrival_time": None,
                "total_time_min": None,
                "payment": None,
                "bus_transit_count": None,
                "subway_transit_count": None,
                "transfer_count": None,
                "path_type": None,
                "confidence": 0.0,
                "source": "none",
                "needs_confirmation": True,
            },
        }
