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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logger import get_logger
from app.core.runtime_metrics import record_safety_decision
from app.services.ai.llm_service import parse_transit_intent
from app.services.ai.stt_service import transcribe_audio
from app.services.ai.tts_service import generate_tts_audio
from app.services.core.exceptions import (
    CoordinateResolveError,
    LLMParsingError,
    STTProcessingError,
    TransportAPIError,
)
from app.services.core.korean_text import normalize_typed_destination
from app.services.core.service_types import ParsedIntent, RouteSegment, TransportMode
from app.services.core.settings_helper import is_mock_mode
from app.services.response_builder import build_user_message
from app.services.transit.kakao_service import resolve_place_candidate
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
    started_at = time.monotonic()
    result = await _run_pipeline_core(audio_bytes, filename, request_id)

    # TTS는 파이프라인 핵심 로직과 분리 — 실패해도 텍스트 응답은 반환
    result["audio_base64"] = await _generate_tts_audio_safely(
        result.get("message", ""),
        request_id=request_id,
        budget_seconds=_remaining_tts_budget(started_at),
    )
    result["request_id"] = request_id
    return result


# 바깥 REQUEST_TIMEOUT_SECONDS 봉투가 TTS 도중에 발동하면 asyncio.CancelledError 가
# 되어 _generate_tts_audio_safely 의 except Exception 으로도 잡히지 않습니다. 그러면
# 오디오뿐 아니라 이미 완성해 둔 텍스트 안내까지 통째로 사라져, "TTS가 실패해도
# 텍스트는 반환한다"는 설계가 무너집니다. 남은 시간을 직접 계산해 텍스트를 지킵니다.
_TTS_ENVELOPE_MARGIN_SECONDS = 1.0


def _remaining_tts_budget(started_at: float) -> float:
    """Seconds TTS may use without letting the outer envelope discard the answer."""
    elapsed = time.monotonic() - started_at
    remaining = settings.REQUEST_TIMEOUT_SECONDS - elapsed - _TTS_ENVELOPE_MARGIN_SECONDS
    return min(float(settings.TTS_TIMEOUT_SECONDS), remaining)


async def run_text_route(
    destination: str,
    destination_x: float | None = None,
    destination_y: float | None = None,
    origin: str | None = None,
    transport_mode: TransportMode = "bus",
    request_id: str = "",
) -> dict:
    """Run the transport pipeline for a typed destination without STT or LLM."""
    raw_destination = destination.strip()
    # 자동완성에서 선택한 좌표가 있으면 사용자가 고른 표시 이름을 그대로 보존합니다.
    # 좌표 없이 직접 입력한 경우에만 `강남역에`, `서울역까지`처럼 명확한 역 조사와
    # 이동 명령을 보수적으로 제거해 엉뚱한 상호가 검색어와 강하게 일치하는 일을 막습니다.
    normalized_destination = (
        normalize_typed_destination(raw_destination)
        if destination_x is None and destination_y is None
        else raw_destination
    )
    parsed = ParsedIntent(
        intent="route",
        origin_text=origin,
        destination_text=normalized_destination,
        destination_x=destination_x,
        destination_y=destination_y,
        transport_mode=transport_mode,
        confidence=1.0,
    )

    try:
        result = await _run_parsed_pipeline(
            parsed,
            raw_destination,
            request_id,
            require_place_confirmation=destination_x is None,
        )
    except (CoordinateResolveError, TransportAPIError) as exc:
        logger.warning("[%s] text route lookup failed: error_type=%s", request_id, type(exc).__name__)
        result = _error_response_from_exception(exc, parsed, transcript=raw_destination)
    except Exception as exc:
        # 예상치 못한 시스템 오류 — 상세 메시지를 로그에만 남기고 범용 안내 반환
        # (음성 파이프라인의 _run_pipeline_core와 동일한 방어 수준을 유지)
        logger.exception("[%s] 텍스트 경로 조회 중 예상치 못한 오류: error_type=%s", request_id, type(exc).__name__)
        result = _error_response_from_parsed(
            "요청을 처리하지 못했습니다. 다시 시도해 주세요.",
            parsed,
            transcript=raw_destination,
            http_status=500,
            error_kind="internal",
        )

    # 텍스트 검색은 브라우저 음성 합성을 사용해 응답 지연과 TTS 비용을 줄입니다.
    result["audio_base64"] = None
    result["request_id"] = request_id
    return result


async def _generate_tts_audio_safely(
    text: str,
    request_id: str,
    budget_seconds: float | None = None,
) -> str | None:
    """TTS가 느리거나 실패해도 텍스트 응답은 그대로 반환합니다."""
    if not text or not text.strip():
        return None

    timeout = float(settings.TTS_TIMEOUT_SECONDS) if budget_seconds is None else budget_seconds
    if timeout <= 0:
        # 앞 단계가 예산을 다 썼습니다. 여기서 TTS를 시작하면 봉투가 먼저 터져
        # 텍스트 안내까지 함께 버려집니다. 오디오를 포기하고 텍스트를 지킵니다.
        logger.warning("[%s] 남은 시간이 없어 TTS를 건너뜁니다 (텍스트 안내는 정상)", request_id)
        return None

    started_at = time.monotonic()
    try:
        return await asyncio.wait_for(
            generate_tts_audio(text),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("[%s] TTS 타임아웃", request_id)
        return None
    except Exception:
        # TTS는 부가 기능 — 어떤 이유로든 실패해도 텍스트 응답은 그대로 반환합니다.
        logger.exception("[%s] TTS 생성 실패", request_id)
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
        # 단계 상한이 없으면 느리기만 한(실패도 아닌) 호출 하나가 전체 봉투를 다 써,
        # 이용자는 무엇이 잘못됐는지 알 수 없는 일반 타임아웃만 받습니다.
        t0 = time.monotonic()
        try:
            transcript = await asyncio.wait_for(
                transcribe_audio(audio_bytes=audio_bytes, filename=filename, request_id=request_id),
                timeout=settings.STT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise STTProcessingError(
                f"STT stage exceeded {settings.STT_TIMEOUT_SECONDS}s"
            ) from None
        logger.info("[%s] STT %.2fs", request_id, time.monotonic() - t0)

        # 2단계: LLM — 텍스트를 intent/출발지/목적지/버스번호 등으로 구조화
        t1 = time.monotonic()
        try:
            parsed = await asyncio.wait_for(
                parse_transit_intent(transcript, request_id=request_id),
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise LLMParsingError(
                f"LLM stage exceeded {settings.LLM_TIMEOUT_SECONDS}s"
            ) from None
        logger.info(
            "[%s] LLM %.2fs — intent=%s confidence=%.2f",
            request_id, time.monotonic() - t1, parsed.intent, parsed.confidence,
        )

        return await _run_parsed_pipeline(
            parsed, transcript, request_id, require_place_confirmation=True
        )

    except CoordinateResolveError as exc:
        # 장소명 → 좌표 변환 실패 — 사용자가 더 정확한 이름을 말해야 함
        logger.warning("[%s] 장소 좌표 변환 오류: error_type=%s", request_id, type(exc).__name__)
        return _error_response_from_exception(exc, parsed, transcript=transcript)

    except (STTProcessingError, LLMParsingError, TransportAPIError) as exc:
        # 외부 API 오류 — 기술적 메시지 대신 user_message 반환
        logger.exception("[%s] 외부 서비스 오류: error_type=%s", request_id, type(exc).__name__)
        return _error_response_from_exception(exc, parsed, transcript=transcript)

    except Exception as exc:
        # 예상치 못한 시스템 오류 — 상세 메시지를 로그에만 남기고 범용 안내 반환
        logger.exception("[%s] 예상치 못한 오류: error_type=%s", request_id, type(exc).__name__)
        return _error_response_from_parsed(
            "요청을 처리하지 못했습니다. 다시 말씀해 주세요.",
            parsed,
            transcript=transcript,
            http_status=500,
            error_kind="internal",
        )


async def _run_parsed_pipeline(
    parsed: ParsedIntent,
    transcript: str,
    request_id: str,
    require_place_confirmation: bool = False,
) -> dict:
    """Validate one intent and build the shared transport response."""
    validation = validate_parsed_intent(parsed)
    if not validation.is_valid:
        return _error_response_from_parsed(validation.message, parsed, transcript=transcript)

    if (
        require_place_confirmation
        and not is_mock_mode()
        and parsed.intent == "route"
        and parsed.destination_text
        and parsed.destination_x is None
    ):
        resolution = await resolve_place_candidate(parsed.destination_text, "목적지")
        if resolution.needs_confirmation:
            return _place_confirmation_response(parsed, transcript, resolution)

    started_at = time.monotonic()
    transport_result = await search_transport_info(parsed, request_id=request_id)
    logger.info(
        "[%s] Transport %.2fs — source=%s",
        request_id,
        time.monotonic() - started_at,
        transport_result.source,
    )

    safety_decision = _verified_safety_decision(parsed, transport_result.source)
    record_safety_decision(
        safety_decision["level"],
        transport_result.source,
        parsed.intent,
    )
    data = ResponseData(
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
        transfer_count=transport_result.transfer_count,
        path_type=transport_result.path_type,
        route_segments=transport_result.route_segments,
        confidence=parsed.confidence,
        source=transport_result.source,
        needs_confirmation=False,
        safety_decision=safety_decision,
    )
    message = build_user_message(parsed=parsed, transport_result=transport_result)
    return {"status": "success", "message": message, "data": data.to_dict()}


def build_timeout_error_response() -> dict:
    """asyncio.TimeoutError 발생 시 gateway에서 반환할 일관된 오류 응답입니다."""
    result = _error_response_from_parsed(
        "처리 시간이 초과되었습니다. 다시 시도해 주세요.",
        parsed=None,
        transcript=None,
        http_status=504,
        error_kind="timeout",
    )
    result["audio_base64"] = None
    return result


# ---------------------------------------------------------------------------
# 응답 조립 헬퍼
# ---------------------------------------------------------------------------

@dataclass
class ResponseData:
    """성공/오류 응답이 공유하는 `data` 필드 스키마.

    라즈베리파이 클라이언트가 status만 보고 분기하면 되도록
    성공/오류 응답 모두 동일한 스키마를 유지합니다.
    """

    transcript: str | None = None
    intent: str | None = None
    origin: str | None = None
    origin_x: float | None = None
    origin_y: float | None = None
    destination: str | None = None
    destination_x: float | None = None
    destination_y: float | None = None
    stop_text: str | None = None
    stop_name: str | None = None
    transport_mode: str | None = None
    bus_number: str | None = None
    arrival_time: str | None = None
    arrival_time_2: str | None = None
    first_bus_time: str | None = None
    total_time_min: int | None = None
    payment: int | None = None
    bus_transit_count: int | None = None
    transfer_count: int | None = None
    path_type: int | None = None
    route_segments: list[RouteSegment] | None = None
    confidence: float = 0.0
    source: str = "none"
    needs_confirmation: bool = False
    confirmation: dict | None = None
    safety_decision: dict | None = None

    def to_dict(self) -> dict:
        # dataclasses.asdict는 route_segments 안의 RouteSegment(dataclass)도
        # 재귀적으로 dict로 변환해 JSON 직렬화 가능한 형태를 만듭니다.
        return asdict(self)


def _error_response_from_parsed(
    message: str,
    parsed: ParsedIntent | None,
    transcript: str | None,
    *,
    http_status: int = 200,
    error_kind: str = "request",
) -> dict:
    """ParsedIntent(있으면)로부터 오류 응답의 공통 필드를 채웁니다."""
    safety_decision = _retry_safety_decision(parsed)
    record_safety_decision(
        safety_decision["level"],
        "none",
        parsed.intent if parsed else "unknown",
    )
    if parsed is None:
        data = ResponseData(
            transcript=transcript,
            needs_confirmation=True,
            safety_decision=safety_decision,
        )
    else:
        data = ResponseData(
            transcript=transcript,
            intent=parsed.intent,
            origin=parsed.origin_text,
            destination=parsed.destination_text,
            stop_text=parsed.stop_text,
            transport_mode=parsed.transport_mode,
            bus_number=parsed.bus_number,
            confidence=parsed.confidence,
            needs_confirmation=True,
            safety_decision=safety_decision,
        )
    return {
        "status": "error",
        "message": message,
        "data": data.to_dict(),
        "error_kind": error_kind,
        "_http_status": http_status,
    }


def _error_response_from_exception(
    exc: Exception,
    parsed: ParsedIntent | None,
    transcript: str | None,
) -> dict:
    """Convert a typed pipeline exception into an observable API error."""
    message = str(getattr(exc, "user_message", "")) or "요청을 처리하지 못했습니다. 다시 시도해 주세요."
    return _error_response_from_parsed(
        message,
        parsed,
        transcript,
        http_status=int(getattr(exc, "http_status", 200)),
        error_kind=str(getattr(exc, "error_kind", "request")),
    )


def _place_confirmation_response(parsed, transcript: str, resolution) -> dict:
    """경로 API 호출 전 사용자가 좌표 후보를 확정할 수 있는 응답입니다."""
    selected = resolution.selected
    safety_decision = {
        "level": "confirm",
        "title": "장소 검증이 필요합니다",
        "reasons": [
            "이름과 카테고리가 가장 적합한 후보를 우선했습니다.",
            "후보가 여러 개이므로 좌표를 확정하기 전에 질문합니다.",
        ],
        "auto_corrected": False,
        "checked_at": None,
    }
    record_safety_decision(safety_decision["level"], "kakao", parsed.intent)
    data = ResponseData(
        transcript=transcript,
        intent=parsed.intent,
        origin=parsed.origin_text,
        destination=selected.get("name"),
        destination_x=_safe_float(selected.get("x")),
        destination_y=_safe_float(selected.get("y")),
        transport_mode=parsed.transport_mode,
        confidence=parsed.confidence,
        needs_confirmation=True,
        confirmation={
            "kind": "place",
            "prompt": resolution.prompt,
            "candidate": selected,
            "alternatives": resolution.alternatives[:4],
        },
        safety_decision=safety_decision,
    )
    return {"status": "success", "message": resolution.prompt, "data": data.to_dict()}


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _verified_safety_decision(parsed: ParsedIntent, source: str) -> dict:
    reasons: list[str] = []
    if parsed.intent == "arrival" and parsed.bus_number:
        if source == "public_data":
            reasons.append("인식한 버스 번호를 운행 노선과 정확히 일치시켜 확인했습니다.")
        else:
            reasons.append("버스 번호 요청 형식이 검증을 통과했습니다.")
        reasons.append("비슷한 번호로 자동 변경하지 않았습니다.")
    elif parsed.intent == "route":
        if source == "odsay":
            reasons.append("확정된 목적지 좌표를 기준으로 버스 경로를 조회했습니다.")
        else:
            reasons.append("버스 전용 경로 요청 조건이 검증을 통과했습니다.")
    if source in {"odsay", "public_data"}:
        reasons.append("외부 교통 데이터 조회가 정상 완료되었습니다.")
    return {
        "level": "verified",
        "title": "검증 절차 완료",
        "reasons": reasons,
        "auto_corrected": False,
        "checked_at": datetime.now(UTC).isoformat() if source in {"odsay", "public_data"} else None,
    }


def _retry_safety_decision(parsed: ParsedIntent | None) -> dict:
    reasons = ["확인되지 않은 정보를 임의로 안내하지 않습니다."]
    if parsed and parsed.intent == "arrival" and parsed.bus_number:
        reasons.insert(0, "현재 정류장에서 해당 번호를 확인하지 못했습니다.")
        reasons.append("가장 가까운 번호로 자동 변경하지 않았습니다.")
    return {
        "level": "retry",
        "title": "다시 확인해 주세요",
        "reasons": reasons,
        "auto_corrected": False,
        "checked_at": None,
    }
