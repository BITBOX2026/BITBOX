# STT, LLM 분석, 검증, 교통 API 조회, 응답 생성을 순서대로 실행하는 핵심 파이프라인 파일입니다.

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
    백엔드 전체 파이프라인을 실행하는 함수입니다.

    기능:
        - 라즈베리파이에서 받은 음성 파일을 텍스트로 변환합니다.
        - 변환된 텍스트를 LLM으로 구조화합니다.
        - 구조화된 결과를 검증합니다.
        - 교통 API를 조회합니다.
        - 라즈베리파이에 반환할 최종 JSON 응답을 생성합니다.

    처리 순서:
        1. STT:
            음성 bytes -> 텍스트

        2. LLM Parsing:
            텍스트 -> intent, destination_text, bus_number, confidence

        3. Validation:
            LLM 결과가 실제 처리 가능한지 검증

        4. Transport Search:
            ODsay 또는 공공데이터 API 조회

        5. Response Build:
            검증된 데이터 기반 정형 응답 생성

    입력:
        audio_bytes:
            - 업로드된 음성 파일의 bytes입니다.

        filename:
            - 업로드된 파일명입니다.

    반환:
        dict:
            - FastAPI에서 그대로 JSON으로 반환 가능한 응답입니다.
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
                destination=parsed.destination_text,
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
            destination=transport_result.destination,
            bus_number=transport_result.bus_number,
            arrival_time=transport_result.arrival_time,
            total_time_min=transport_result.total_time_min,
            transfer_count=transport_result.transfer_count,
            confidence=parsed.confidence,
            source=transport_result.source,
            needs_confirmation=False,
        )

    except CoordinateResolveError as exc:
        logger.warning("User-correctable location error: %s", exc)

        return _error_response(
            message=exc.user_message,
            transcript=transcript,
            intent=_get_intent(parsed),
            destination=_get_destination(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )

    except (STTProcessingError, LLMParsingError, TransportAPIError) as exc:
        logger.exception("External service or processing error: %s", exc)

        return _error_response(
            message=exc.user_message,
            transcript=transcript,
            intent=_get_intent(parsed),
            destination=_get_destination(parsed),
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
            destination=_get_destination(parsed),
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
            destination=_get_destination(parsed),
            bus_number=_get_bus_number(parsed),
            confidence=_get_confidence(parsed),
            needs_confirmation=True,
        )


def _success_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    destination: str | None,
    bus_number: str | None,
    arrival_time: str | None,
    total_time_min: int | None,
    transfer_count: int | None,
    confidence: float,
    source: str,
    needs_confirmation: bool,
) -> dict:
    """
    성공 응답 JSON을 생성하는 함수입니다.

    기능:
        - 파이프라인 성공 결과를 API 응답 형식으로 통일합니다.
        - 라즈베리파이는 이 응답에서 message와 data만 사용하면 됩니다.

    반환 구조:
        {
            "status": "success",
            "message": "...",
            "data": {...}
        }
    """

    return {
        "status": "success",
        "message": message,
        "data": {
            "transcript": transcript,
            "intent": intent,
            "destination": destination,
            "bus_number": bus_number,
            "arrival_time": arrival_time,
            "total_time_min": total_time_min,
            "transfer_count": transfer_count,
            "confidence": confidence,
            "source": source,
            "needs_confirmation": needs_confirmation,
        },
    }


def _error_response(
    message: str,
    transcript: str | None,
    intent: str | None,
    destination: str | None,
    bus_number: str | None,
    confidence: float,
    needs_confirmation: bool,
) -> dict:
    """
    실패 응답 JSON을 생성하는 함수입니다.

    기능:
        - 실패 상황에서도 응답 구조를 일정하게 유지합니다.
        - 가짜 목적지, 가짜 버스 번호, 가짜 도착 시간을 넣지 않습니다.
        - 알 수 없는 값은 None으로 반환합니다.

    반환 구조:
        {
            "status": "error",
            "message": "...",
            "data": {...}
        }
    """

    return {
        "status": "error",
        "message": message,
        "data": {
            "transcript": transcript,
            "intent": intent,
            "destination": destination,
            "bus_number": bus_number,
            "arrival_time": None,
            "total_time_min": None,
            "transfer_count": None,
            "confidence": confidence,
            "source": "none",
            "needs_confirmation": needs_confirmation,
        },
    }


def _get_intent(parsed: ParsedIntent | None) -> str | None:
    """
    ParsedIntent에서 intent 값을 안전하게 꺼내는 함수입니다.

    기능:
        - parsed가 None이어도 서버가 죽지 않도록 None을 반환합니다.
    """

    if parsed is None:
        return None

    return parsed.intent


def _get_destination(parsed: ParsedIntent | None) -> str | None:
    """
    ParsedIntent에서 destination_text 값을 안전하게 꺼내는 함수입니다.

    기능:
        - parsed가 None이어도 서버가 죽지 않도록 None을 반환합니다.
    """

    if parsed is None:
        return None

    return parsed.destination_text


def _get_bus_number(parsed: ParsedIntent | None) -> str | None:
    """
    ParsedIntent에서 bus_number 값을 안전하게 꺼내는 함수입니다.

    기능:
        - parsed가 None이어도 서버가 죽지 않도록 None을 반환합니다.
    """

    if parsed is None:
        return None

    return parsed.bus_number


def _get_confidence(parsed: ParsedIntent | None) -> float:
    """
    ParsedIntent에서 confidence 값을 안전하게 꺼내는 함수입니다.

    기능:
        - parsed가 None이면 0.0을 반환합니다.
    """

    if parsed is None:
        return 0.0

    return parsed.confidence