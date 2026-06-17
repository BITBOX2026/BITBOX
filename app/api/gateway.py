"""
API Gateway — 음성 파일 수신 및 파이프라인 실행

클라이언트(라즈베리파이)가 녹음한 오디오를 받아 파이프라인을 실행하고
구조화된 JSON 응답(교통 안내 + TTS 오디오)을 반환합니다.

엔드포인트: POST /api/process
"""

import asyncio
import secrets
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.api.schemas import ProcessResponse, UploadCompatResponse
from app.core.config import settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.services.core.settings_helper import get_setting
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


@router.post("/process", response_model=ProcessResponse)
@limiter.limit("10/minute")  # IP당 분당 최대 10회 요청 허용
async def process_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """
    음성 파일을 받아 전체 백엔드 파이프라인을 실행합니다.

    처리 흐름:
    1. 파일 형식 / 크기 검증
    2. STT → LLM → 검증 → 교통 API → TTS (pipeline.py)
    3. 구조화된 JSON 응답 반환
    """

    _verify_api_token(request)

    # MIME 타입 확인 (세미콜론 이후 파라미터 제거 후 비교)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 오디오 형식입니다: {file.content_type}",
        )

    # 파일 크기 확인 (기본 10MB)
    max_size = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    audio_bytes = await file.read(max_size + 1)
    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"오디오 파일 크기는 {settings.MAX_AUDIO_SIZE_MB}MB 이하여야 합니다.",
        )

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="오디오 파일이 비어 있습니다.")

    if not _looks_like_supported_audio(content_type, audio_bytes):
        raise HTTPException(
            status_code=400,
            detail="오디오 파일 형식을 확인하지 못했습니다.",
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


@router.post("/upload", response_model=UploadCompatResponse)
async def upload_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """Compatibility alias for the existing React frontend."""
    result = await process_audio(request, file)
    return _build_upload_compat_response(result)


def _build_upload_compat_response(result: dict) -> dict:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    destination = data.get("destination_text") or data.get("destination")
    message = str(result.get("message") or destination or "요청을 처리했습니다.")

    return {
        "success": result.get("status") == "success",
        "text": data.get("transcript"),
        "intent": data.get("intent"),
        "destination": destination,
        "destination_text": destination,
        "bus_number": data.get("bus_number"),
        "message": message,
        "buses": result.get("buses") if isinstance(result.get("buses"), list) else [],
        "audio_base64": result.get("audio_base64"),
        "request_id": result.get("request_id"),
    }


def _verify_api_token(request: Request) -> None:
    """API_AUTH_TOKEN이 설정된 경우 요청 헤더의 토큰을 검증합니다."""
    expected = get_setting("API_AUTH_TOKEN")
    expected_token = str(expected or "").strip()
    if not expected_token:
        return

    provided = (request.headers.get("x-bitbox-token") or "").strip()
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()

    if not provided or not secrets.compare_digest(expected_token, provided):
        raise HTTPException(status_code=401, detail="인증 토큰이 올바르지 않습니다.")


def _looks_like_supported_audio(content_type: str, audio_bytes: bytes) -> bool:
    """MIME 타입과 실제 파일 헤더가 크게 어긋나지 않는지 확인합니다."""
    if content_type in {"audio/wav", "audio/x-wav"}:
        return (
            len(audio_bytes) >= 12
            and audio_bytes[:4] == b"RIFF"
            and audio_bytes[8:12] == b"WAVE"
        )

    if content_type in {"audio/mpeg", "audio/mp3"}:
        return audio_bytes.startswith(b"ID3") or (
            len(audio_bytes) >= 2
            and audio_bytes[0] == 0xFF
            and (audio_bytes[1] & 0xE0) == 0xE0
        )

    if content_type == "audio/webm":
        return audio_bytes.startswith(b"\x1a\x45\xdf\xa3")

    if content_type == "audio/mp4":
        return len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp"

    return False
