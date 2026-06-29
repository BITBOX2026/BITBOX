"""
API Gateway — 음성 파일 수신 및 파이프라인 실행

클라이언트(라즈베리파이)가 녹음한 오디오를 받아 파이프라인을 실행하고
구조화된 JSON 응답(교통 안내 + TTS 오디오)을 반환합니다.

엔드포인트: POST /api/process 
"""

import asyncio
import re
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

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="오디오 파일이 비어 있습니다.")

    if len(audio_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"오디오 파일 크기는 {settings.MAX_AUDIO_SIZE_MB}MB 이하여야 합니다.",
        )

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
@limiter.limit("10/minute")
async def upload_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """Compatibility alias for the existing React frontend."""
    result = await process_audio(request, file)
    return _build_upload_compat_response(result)


def _build_upload_compat_response(result: dict) -> dict:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    intent = data.get("intent")
    is_success = result.get("status") == "success"

    # arrival 인텐트는 목적지가 없으므로 정류장명을 destination으로 노출
    # 프론트 VoiceResult가 빈 제목으로 표시되는 문제를 방지
    if intent == "arrival":
        destination = data.get("stop_name") or data.get("stop_text")
    else:
        destination = data.get("destination")

    message = str(result.get("message") or destination or "요청을 처리했습니다.")

    return {
        "success": is_success,
        "text": data.get("transcript"),
        "intent": intent,
        "destination": destination,
        "destination_text": destination,
        "bus_number": data.get("bus_number"),
        "arrival_time": data.get("arrival_time"),
        "arrival_time_2": data.get("arrival_time_2"),
        "first_bus_time": data.get("first_bus_time"),
        "message": message,
        "buses": _build_buses_from_result(data, is_success),
        "audio_base64": result.get("audio_base64"),
        "request_id": result.get("request_id"),
    }


def _build_buses_from_result(data: dict, is_success: bool) -> list[dict]:
    """파이프라인 결과에서 프론트 BusOption 형식의 버스 목록을 구성합니다."""
    if not is_success:
        return []
    intent = data.get("intent")
    if intent == "route":
        return _build_buses_from_route(data)
    if intent == "arrival":
        return _build_buses_from_arrival(data)
    return []


def _build_buses_from_route(data: dict) -> list[dict]:
    """ODsay 경로 결과를 프론트 BusOption + totalMin/steps 형식으로 변환합니다."""
    bus_number = data.get("bus_number") or ""
    total_time_min = int(data.get("total_time_min") or 0)
    route_segments = data.get("route_segments") or []

    if not bus_number and not route_segments:
        return []

    n_segs = len(route_segments) or 1
    steps: list[dict] = []
    for seg in route_segments:
        line = seg.get("line", "")
        is_bus = seg.get("vehicle_type") == "버스"
        # 버스 구간은 번호만("146번" → "146"), 지하철 구간은 빈 문자열
        seg_bus_number = line.replace("번", "").strip() if is_bus else ""
        seg_time = seg.get("time_min")
        duration = seg_time if seg_time is not None else round(total_time_min / n_segs)
        steps.append({
            "type": "bus",  # RouteStep은 "walk" | "bus"만 지원
            "durationMin": duration,
            "busNumber": seg_bus_number,
            "fromStop": seg.get("start_name") or "",
            "toStop": seg.get("end_name") or "",
            "description": f"{line} {'탑승' if is_bus else '이용'}",
        })

    # 대표 버스 번호: bus_number 우선, 없으면 노선명에서 추출
    if bus_number:
        display_bus = bus_number
    elif route_segments:
        first_line = route_segments[0].get("line", "")
        display_bus = first_line.replace("번", "").strip()
    else:
        display_bus = ""

    origin_stop = steps[0]["fromStop"] if steps else (data.get("origin") or "")

    arrival_time = data.get("arrival_time") or ""
    m = re.search(r"(\d+)\s*분", arrival_time)
    arrival_min = int(m.group(1)) if m else 0

    return [{
        "id": f"route-{display_bus}-0",
        "busNumber": display_bus,
        "arrivalMin": arrival_min,
        "traTimeSec": max(arrival_min * 60, 60),
        "arrivalMsg": arrival_time or f"{display_bus} 탑승 예정",
        "currentStationName": origin_stop,
        "remainingStops": 0,
        "busType": 0,
        "congetion": 0,     # 프론트 typo 그대로 유지
        "isFullFlag": False,
        "isLastBus": False,
        "plainNo": "",
        "isSecond": False,
        # useRouteSelection이 (bus as any)로 접근하는 추가 필드
        "totalMin": total_time_min,
        "steps": steps,
    }]


# 버스가 운행을 마쳤거나 아직 차고지에서 출발 전인 상태 코드
_TERMINAL_ARRIVAL_STATES = {"운행종료"}
_STANDBY_ARRIVAL_STATES = {"출발대기"}


def _build_buses_from_arrival(data: dict) -> list[dict]:
    """버스 도착 정보 조회 결과를 프론트 BusOption 형식으로 변환합니다."""
    bus_number = data.get("bus_number") or ""
    if not bus_number:
        return []

    arrival_time = data.get("arrival_time") or ""
    arrival_time_2 = data.get("arrival_time_2") or ""
    stop_name = data.get("stop_name") or data.get("stop_text") or ""

    if arrival_time in _TERMINAL_ARRIVAL_STATES:
        return []

    buses = []
    if arrival_time:
        buses.append(_make_arrival_bus_entry(bus_number, arrival_time, stop_name, is_second=False))
    if arrival_time_2 and arrival_time_2 not in _TERMINAL_ARRIVAL_STATES:
        buses.append(_make_arrival_bus_entry(bus_number, arrival_time_2, stop_name, is_second=True))

    return buses


def _make_arrival_bus_entry(
    bus_number: str,
    arrival_time: str,
    stop_name: str,
    is_second: bool,
) -> dict:
    """단일 버스 도착 항목을 프론트 BusOption 형식으로 생성합니다."""
    suffix = "-2" if is_second else ""

    if arrival_time in _STANDBY_ARRIVAL_STATES:
        return {
            "id": f"arrival-{bus_number}{suffix}",
            "busNumber": bus_number,
            "arrivalMin": 0,
            "traTimeSec": 30,
            "arrivalMsg": "출발 대기 중",
            "currentStationName": stop_name,
            "remainingStops": 0,
            "busType": 0,
            "congetion": 0,
            "isFullFlag": False,
            "isLastBus": False,
            "plainNo": "",
            "isSecond": is_second,
            "totalMin": 0,
            "steps": [],
        }

    m = re.search(r"(\d+)\s*분", arrival_time)
    arrival_min = int(m.group(1)) if m else 0

    return {
        "id": f"arrival-{bus_number}{suffix}",
        "busNumber": bus_number,
        "arrivalMin": arrival_min,
        "traTimeSec": max(arrival_min * 60, 30),
        "arrivalMsg": arrival_time or f"{bus_number}번 도착 정보",
        "currentStationName": stop_name,
        "remainingStops": 0,
        "busType": 0,
        "congetion": 0,
        "isFullFlag": False,
        "isLastBus": False,
        "plainNo": "",
        "isSecond": is_second,
        "totalMin": arrival_min,
        "steps": [],
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
