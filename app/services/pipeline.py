"""
메인 파이프라인 오케스트레이터

음성 bytes를 최종 JSON 응답으로 변환하는 전체 흐름을 조율합니다.

처리 순서:
1. STT  — 음성 → 텍스트 (OpenAI Whisper)
2. LLM  — 텍스트 → 구조화된 intent JSON (OpenAI GPT)
3. 검증  — intent가 실제 조회 가능한 요청인지 확인
4. 교통 API — ODsay 경로 또는 서울버스 실시간 도착 정보 조회
5. 응답  — 사용자 안내 문장 생성
6. TTS  — 안내 문장 → 음성 base64 (OpenAI TTS)

예외는 각 단계에서 발생하는 PipelineError 하위 클래스로 구분하며,
pipeline.py 에서 모두 잡아 사용자 친화적 메시지로 변환합니다.
"""

import asyncio
import time
from dataclasses import asdict

from app.core.config import settings
from app.core.logger import get_logger
from app.services.ai.llm_service import parse_transit_intent
from app.services.ai.stt_service import transcribe_audio
from app.services.ai.tts_service import generate_tts_audio
from app.services.core.exceptions import (
    CoordinateResolveError,
    LLMParsingError,
    STTProcessingError,
    TransportAPIError,
)
from app.services.core.service_types import ParsedIntent, RouteSegment, TransportMode
from app.services.response_builder import build_user_message
from app.services.transit.transport_service import search_transport_info
from app.services.transit.validate_service import validate_parsed_intent

logger = get_logger(__name__)


async def run_pipeline(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    request_id: str = "",
) -> dict:
    """
    음성 파일을 최종 안내 응답으로 변환하는 전체 파이프라인입니다.
    내부 처리 후 TTS 오디오와 request_id를 결과에 추가해 반환합니다.
    """
    result = await _run_pipeline_core(audio_bytes, filename, request_id)

    # TTS는 파이프라인 핵심 로직과 분리 — 실패해도 텍스트 응답은 반환
    result["audio_base64"] = await _generate_tts_audio_safely(
        result.get("message", ""),
        request_id=request_id,
    )
    result["request_id"] = request_id
    return result


async def run_text_route(
    destination: str,
    origin: str | None = None,
    transport_mode: TransportMode = "bus",
    request_id: str = "",
) -> dict:
    """Run the transport pipeline for a typed destination without STT or LLM."""
    parsed = ParsedIntent(
        intent="route",
        origin_text=origin,
        destination_text=destination,
        transport_mode=transport_mode,
        confidence=1.0,
    )

    try:
        result = await _run_parsed_pipeline(parsed, destination, request_id)
    except (CoordinateResolveError, TransportAPIError) as exc:
        logger.warning("[%s] text route lookup failed: %s", request_id, exc)
        result = _error_response(
            message=exc.user_message,
            transcript=destination,
            stop_name=None,
            needs_confirmation=True,
            **_parsed_fields(parsed),
        )

    result["audio_base64"] = await _generate_tts_audio_safely(
        result.get("message", ""),
        request_id=request_id,
    )
    result["request_id"] = request_id
    return result


async def _generate_tts_audio_safely(text: str, request_id: str) -> str | None:
    """TTS가 느리거나 실패해도 텍스트 응답은 그대로 반환합니다."""
    if not text or not text.strip():
        return None

    started_at = time.monotonic()
    try:
        return await asyncio.wait_for(
            generate_tts_audio(text),
            timeout=settings.TTS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("[%s] TTS 타임아웃", request_id)
        return None
    finally:
        logger.info("[%s] TTS %.2fs", request_id, time.monotonic() - started_at)


async def _run_pipeline_core(
    audio_bytes: bytes,
    filename: str,
    request_id: str,
) -> dict:
    """STT → LLM → 검증 → 교통 API → 응답 생성 핵심 흐름입니다."""

    transcript: str | None = None
    parsed: ParsedIntent | None = None

    try:
        # 1단계: STT — 음성 파일을 한국어 텍스트로 변환
        t0 = time.monotonic()
        transcript = await transcribe_audio(audio_bytes=audio_bytes, filename=filename, request_id=request_id)
        logger.info("[%s] STT %.2fs", request_id, time.monotonic() - t0)

        # 2단계: LLM — 텍스트를 intent/출발지/목적지/버스번호 등으로 구조화
        t1 = time.monotonic()
        parsed = await parse_transit_intent(transcript, request_id=request_id)
        logger.info(
            "[%s] LLM %.2fs — intent=%s confidence=%.2f",
            request_id, time.monotonic() - t1, parsed.intent, parsed.confidence,
        )

        return await _run_parsed_pipeline(parsed, transcript, request_id)

    except CoordinateResolveError as exc:
        # 장소명 → 좌표 변환 실패 — 사용자가 더 정확한 이름을 말해야 함
        logger.warning("장소 좌표 변환 오류: %s", exc)
        return _error_response(
            message=exc.user_message,
            transcript=transcript,
            stop_name=None,
            needs_confirmation=True,
            **_parsed_fields(parsed),
        )

    except (STTProcessingError, LLMParsingError, TransportAPIError) as exc:
        # 외부 API 오류 — 기술적 메시지 대신 user_message 반환
        logger.exception("외부 서비스 오류: %s", exc)
        return _error_response(
            message=exc.user_message,
            transcript=transcript,
            stop_name=None,
            needs_confirmation=True,
            **_parsed_fields(parsed),
        )

    except Exception as exc:
        # 예상치 못한 시스템 오류 — 상세 메시지를 로그에만 남기고 범용 안내 반환
        logger.exception("예상치 못한 오류: %s", exc)
        return _error_response(
            message="요청을 처리하지 못했습니다. 다시 말씀해 주세요.",
            transcript=transcript,
            stop_name=None,
            needs_confirmation=True,
            **_parsed_fields(parsed),
        )


async def _run_parsed_pipeline(
    parsed: ParsedIntent,
    transcript: str,
    request_id: str,
) -> dict:
    """Validate one intent and build the shared transport response."""
    validation = validate_parsed_intent(parsed)
    if not validation.is_valid:
        return _error_response(
            message=validation.message,
            transcript=transcript,
            intent=parsed.intent,
            origin=parsed.origin_text,
            destination=parsed.destination_text,
            stop_text=parsed.stop_text,
            stop_name=None,
            transport_mode=parsed.transport_mode,
            bus_number=parsed.bus_number,
            confidence=parsed.confidence,
            needs_confirmation=True,
        )

    started_at = time.monotonic()
    transport_result = await search_transport_info(parsed, request_id=request_id)
    logger.info(
        "[%s] Transport %.2fs — source=%s",
        request_id,
        time.monotonic() - started_at,
        transport_result.source,
    )

    return _success_response(
        message=build_user_message(parsed=parsed, transport_result=transport_result),
        transcript=transcript,
        intent=parsed.intent,
        origin=transport_result.origin,
        origin_x=transport_result.origin_x,
        origin_y=transport_result.origin_y,
        destination=(
            transport_result.stop_name
            if parsed.intent == "arrival"
            else transport_result.destination
        ),
        destination_x=transport_result.destination_x,
        destination_y=transport_result.destination_y,
        stop_text=parsed.stop_text,
        stop_name=transport_result.stop_name,
        transport_mode=transport_result.transport_mode,
        bus_number=transport_result.bus_number,
        arrival_time=transport_result.arrival_time,
        arrival_time_2=transport_result.arrival_time_2,
        first_bus_time=transport_result.first_bus_time,
        total_time_min=transport_result.total_time_min,
        payment=transport_result.payment,
        bus_transit_count=transport_result.bus_transit_count,
        subway_transit_count=transport_result.subway_transit_count,
        transfer_count=transport_result.transfer_count,
        path_type=transport_result.path_type,
        route_segments=transport_result.route_segments,
        confidence=parsed.confidence,
        source=transport_result.source,
        needs_confirmation=False,
    )


def build_timeout_error_response() -> dict:
    """asyncio.TimeoutError 발생 시 gateway에서 반환할 일관된 오류 응답입니다."""
    result = _error_response(
        message="처리 시간이 초과되었습니다. 다시 시도해 주세요.",
        transcript=None,
        intent=None,
        origin=None,
        destination=None,
        stop_text=None,
        stop_name=None,
        transport_mode=None,
        bus_number=None,
        confidence=0.0,
        needs_confirmation=True,
    )
    result["audio_base64"] = None
    return result


# ---------------------------------------------------------------------------
# 응답 조립 헬퍼
# ---------------------------------------------------------------------------

def _success_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    origin_x: float | None,
    origin_y: float | None,
    destination: str | None,
    destination_x: float | None,
    destination_y: float | None,
    stop_text: str | None,
    stop_name: str | None,
    transport_mode: str | None,
    bus_number: str | None,
    arrival_time: str | None,
    arrival_time_2: str | None,
    first_bus_time: str | None,
    total_time_min: int | None,
    payment: int | None,
    bus_transit_count: int | None,
    subway_transit_count: int | None,
    transfer_count: int | None,
    path_type: int | None,
    route_segments: list[RouteSegment] | None,
    confidence: float,
    source: str,
    needs_confirmation: bool,
) -> dict:
    return {
        "status": "success",
        "message": message,
        "data": _build_response_data(
            transcript=transcript, intent=intent,
            origin=origin, origin_x=origin_x, origin_y=origin_y,
            destination=destination, destination_x=destination_x, destination_y=destination_y,
            stop_text=stop_text, stop_name=stop_name,
            transport_mode=transport_mode, bus_number=bus_number,
            arrival_time=arrival_time, arrival_time_2=arrival_time_2,
            first_bus_time=first_bus_time,
            total_time_min=total_time_min,
            payment=payment, bus_transit_count=bus_transit_count,
            subway_transit_count=subway_transit_count, transfer_count=transfer_count,
            path_type=path_type, route_segments=route_segments,
            confidence=confidence, source=source, needs_confirmation=needs_confirmation,
        ),
    }


def _error_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    destination: str | None,
    stop_text: str | None,
    stop_name: str | None,
    transport_mode: str | None,
    bus_number: str | None,
    confidence: float,
    needs_confirmation: bool,
) -> dict:
    # 오류 응답도 성공 응답과 동일한 data 스키마를 유지합니다.
    # 라즈베리파이 클라이언트가 status만 보고 분기하면 되도록 구조를 일관되게 유지합니다.
    return {
        "status": "error",
        "message": message,
        "data": _build_response_data(
            transcript=transcript, intent=intent,
            origin=origin, destination=destination,
            stop_text=stop_text, stop_name=stop_name,
            transport_mode=transport_mode, bus_number=bus_number,
            arrival_time=None, total_time_min=None, payment=None,
            bus_transit_count=None, subway_transit_count=None,
            transfer_count=None, path_type=None, route_segments=None,
            confidence=confidence, source="none", needs_confirmation=needs_confirmation,
        ),
    }


def _build_response_data(
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    origin_x: float | None = None,
    origin_y: float | None = None,
    destination: str | None = None,
    destination_x: float | None = None,
    destination_y: float | None = None,
    stop_text: str | None = None,
    stop_name: str | None = None,
    transport_mode: str | None = None,
    bus_number: str | None = None,
    arrival_time: str | None = None,
    arrival_time_2: str | None = None,
    first_bus_time: str | None = None,
    total_time_min: int | None = None,
    payment: int | None = None,
    bus_transit_count: int | None = None,
    subway_transit_count: int | None = None,
    transfer_count: int | None = None,
    path_type: int | None = None,
    route_segments: list[RouteSegment] | None = None,
    confidence: float = 0.0,
    source: str = "none",
    needs_confirmation: bool = False,
) -> dict:
    """성공/오류 응답 모두 사용하는 공통 data 스키마를 반환합니다."""
    return {
        "transcript": transcript,
        "intent": intent,
        "origin": origin,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "destination": destination,
        "destination_x": destination_x,
        "destination_y": destination_y,
        "stop_text": stop_text,
        "stop_name": stop_name,
        "transport_mode": transport_mode,
        "bus_number": bus_number,
        "arrival_time": arrival_time,
        "arrival_time_2": arrival_time_2,
        "first_bus_time": first_bus_time,
        "total_time_min": total_time_min,
        "payment": payment,
        "bus_transit_count": bus_transit_count,
        "subway_transit_count": subway_transit_count,
        "transfer_count": transfer_count,
        "path_type": path_type,
        # RouteSegment dataclass를 dict로 변환 — JSON 직렬화 가능하도록
        "route_segments": [asdict(seg) for seg in route_segments] if route_segments else None,
        "confidence": confidence,
        "source": source,
        "needs_confirmation": needs_confirmation,
    }


def _parsed_fields(parsed: ParsedIntent | None) -> dict:
    """예외 핸들러에서 ParsedIntent로부터 공통 오류 필드를 안전하게 추출합니다."""
    if parsed is None:
        return {
            "intent": None, "origin": None, "destination": None,
            "stop_text": None, "transport_mode": None,
            "bus_number": None, "confidence": 0.0,
        }
    return {
        "intent": parsed.intent,
        "origin": parsed.origin_text,
        "destination": parsed.destination_text,
        "stop_text": parsed.stop_text,
        "transport_mode": parsed.transport_mode,
        "bus_number": parsed.bus_number,
        "confidence": parsed.confidence,
    }
