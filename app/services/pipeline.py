from app.core.logger import get_logger
from app.services.exceptions import (
    CoordinateResolveError,
    LLMParsingError,
    PipelineError,
    STTProcessingError,
    TransportAPIError,
)
from app.services.llm_service import parse_transit_intent
from app.services.response_builder import build_user_message
from app.services.service_types import ParsedIntent
from app.services.stt_service import transcribe_audio
from app.services.transport_service import search_transport_info
from app.services.validate_service import validate_parsed_intent

logger = get_logger(__name__)


async def run_pipeline(
    audio_bytes: bytes,
    filename: str = "audio.wav",
) -> dict:
    """
    음성 파일을 최종 안내 응답으로 변환하는 전체 백엔드 파이프라인입니다.

    처리 순서:
    STT -> LLM JSON 분석 -> 검증 -> 교통 API 조회 -> 정형 응답 생성
    """

    transcript: str | None = None
    parsed: ParsedIntent | None = None

    try:
        transcript = await transcribe_audio(
            audio_bytes=audio_bytes,
            filename=filename,
        )

        parsed = await parse_transit_intent(transcript)

        validation = validate_parsed_intent(parsed)
        if not validation.is_valid:
            return _error_response(
                message=validation.message,
                transcript=transcript,
                intent=parsed.intent,
                origin=parsed.origin_text,
                destination=parsed.destination_text,
                transport_mode=parsed.transport_mode,
                bus_number=parsed.bus_number,
                confidence=parsed.confidence,
                needs_confirmation=True,
            )

        transport_result = await search_transport_info(parsed)

        message = build_user_message(
            parsed=parsed,
            transport_result=transport_result,
        )

        return _success_response(
            message=message,
            transcript=transcript,
            intent=parsed.intent,
            origin=transport_result.origin,
            destination=transport_result.destination,
            transport_mode=transport_result.transport_mode,
            bus_number=transport_result.bus_number,
            arrival_time=transport_result.arrival_time,
            total_time_min=transport_result.total_time_min,
            payment=transport_result.payment,
            bus_transit_count=transport_result.bus_transit_count,
            subway_transit_count=transport_result.subway_transit_count,
            transfer_count=transport_result.transfer_count,
            path_type=transport_result.path_type,
            confidence=parsed.confidence,
            source=transport_result.source,
            needs_confirmation=False,
        )

    except CoordinateResolveError as exc:
        logger.warning("User-correctable location error: %s", exc)

        return _error_response(
            message=str(exc) or exc.user_message,
            transcript=transcript,
            intent=_get_intent(parsed),
            origin=_get_origin(parsed),
            destination=_get_destination(parsed),
            transport_mode=_get_transport_mode(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )

    except (STTProcessingError, LLMParsingError, TransportAPIError) as exc:
        logger.exception("External service or processing error: %s", exc)

        return _error_response(
            message=str(exc) or exc.user_message,
            transcript=transcript,
            intent=_get_intent(parsed),
            origin=_get_origin(parsed),
            destination=_get_destination(parsed),
            transport_mode=_get_transport_mode(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )

    except PipelineError as exc:
        logger.warning("Pipeline logic error: %s", exc)

        return _error_response(
            message=exc.user_message,
            transcript=transcript,
            intent=_get_intent(parsed),
            origin=_get_origin(parsed),
            destination=_get_destination(parsed),
            transport_mode=_get_transport_mode(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )

    except Exception as exc:
        logger.exception("Unexpected system-level pipeline error: %s", exc)

        return _error_response(
            message="요청을 처리하지 못했습니다. 다시 말씀해 주세요.",
            transcript=transcript,
            intent=_get_intent(parsed),
            origin=_get_origin(parsed),
            destination=_get_destination(parsed),
            transport_mode=_get_transport_mode(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )


def _success_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    destination: str | None,
    transport_mode: str | None,
    bus_number: str | None,
    arrival_time: str | None,
    total_time_min: int | None,
    payment: int | None,
    bus_transit_count: int | None,
    subway_transit_count: int | None,
    transfer_count: int | None,
    path_type: int | None,
    confidence: float,
    source: str,
    needs_confirmation: bool,
) -> dict:
    """성공 응답 JSON을 라즈베리파이가 쓰기 쉬운 고정 구조로 만듭니다."""

    return {
        "status": "success",
        "message": message,
        "data": _build_response_data(
            transcript=transcript,
            intent=intent,
            origin=origin,
            destination=destination,
            transport_mode=transport_mode,
            bus_number=bus_number,
            arrival_time=arrival_time,
            total_time_min=total_time_min,
            payment=payment,
            bus_transit_count=bus_transit_count,
            subway_transit_count=subway_transit_count,
            transfer_count=transfer_count,
            path_type=path_type,
            confidence=confidence,
            source=source,
            needs_confirmation=needs_confirmation,
        ),
    }


def _error_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    destination: str | None,
    transport_mode: str | None,
    bus_number: str | None,
    confidence: float,
    needs_confirmation: bool,
) -> dict:
    """실패 응답도 성공 응답과 같은 data schema를 유지합니다."""

    return {
        "status": "error",
        "message": message,
        "data": _build_response_data(
            transcript=transcript,
            intent=intent,
            origin=origin,
            destination=destination,
            transport_mode=transport_mode,
            bus_number=bus_number,
            arrival_time=None,
            total_time_min=None,
            payment=None,
            bus_transit_count=None,
            subway_transit_count=None,
            transfer_count=None,
            path_type=None,
            confidence=confidence,
            source="none",
            needs_confirmation=needs_confirmation,
        ),
    }


def _build_response_data(
    transcript: str | None,
    intent: str | None,
    origin: str | None,
    destination: str | None,
    transport_mode: str | None,
    bus_number: str | None,
    arrival_time: str | None,
    total_time_min: int | None,
    payment: int | None,
    bus_transit_count: int | None,
    subway_transit_count: int | None,
    transfer_count: int | None,
    path_type: int | None,
    confidence: float,
    source: str,
    needs_confirmation: bool,
) -> dict:
    """모든 응답에서 유지할 공통 data schema입니다."""

    return {
        "transcript": transcript,
        "intent": intent,
        "origin": origin,
        "destination": destination,
        "transport_mode": transport_mode,
        "bus_number": bus_number,
        "arrival_time": arrival_time,
        "total_time_min": total_time_min,
        "payment": payment,
        "bus_transit_count": bus_transit_count,
        "subway_transit_count": subway_transit_count,
        "transfer_count": transfer_count,
        "path_type": path_type,
        "confidence": confidence,
        "source": source,
        "needs_confirmation": needs_confirmation,
    }


def _get_intent(parsed: ParsedIntent | None) -> str | None:
    if parsed is None:
        return None

    return parsed.intent


def _get_origin(parsed: ParsedIntent | None) -> str | None:
    if parsed is None:
        return None

    return parsed.origin_text


def _get_destination(parsed: ParsedIntent | None) -> str | None:
    if parsed is None:
        return None

    return parsed.destination_text


def _get_transport_mode(parsed: ParsedIntent | None) -> str | None:
    if parsed is None:
        return None

    return parsed.transport_mode


def _get_bus_number(parsed: ParsedIntent | None) -> str | None:
    if parsed is None:
        return None

    return parsed.bus_number


def _get_confidence(parsed: ParsedIntent | None) -> float:
    if parsed is None:
        return 0.0

    return parsed.confidence
