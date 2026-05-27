from app.services.constants import MIN_CONFIDENCE
from app.services.service_types import ParsedIntent, ValidationResult
from app.services.settings_helper import get_setting


def validate_parsed_intent(parsed: ParsedIntent) -> ValidationResult:
    """LLM 분석 결과가 실제 조회 가능한 요청인지 검증합니다."""

    if parsed.intent == "unknown":
        return ValidationResult(
            is_valid=False,
            message="요청 내용을 정확히 이해하지 못했습니다. 목적지나 버스 번호를 다시 말씀해 주세요.",
        )

    if parsed.confidence < MIN_CONFIDENCE:
        return ValidationResult(
            is_valid=False,
            message="음성 인식 결과가 불확실합니다. 다시 한 번 말씀해 주세요.",
        )

    if parsed.intent == "route" and not parsed.destination_text:
        return ValidationResult(
            is_valid=False,
            message="목적지를 말씀해 주세요.",
        )

    if parsed.intent == "route" and not parsed.origin_text and not _has_default_origin():
        return ValidationResult(
            is_valid=False,
            message="출발지를 말씀해 주세요.",
        )

    if parsed.intent == "arrival" and not parsed.bus_number:
        return ValidationResult(
            is_valid=False,
            message="버스 번호를 말씀해 주세요.",
        )

    if parsed.intent == "arrival" and not parsed.stop_text:
        return ValidationResult(
            is_valid=False,
            message="어느 정류장 기준인지 말씀해 주세요.",
        )

    return ValidationResult(
        is_valid=True,
        message="검증 성공",
    )


def _has_default_origin() -> bool:
    """기기에 기본 출발지(설치 위치)가 설정되어 있는지 확인합니다."""

    if get_setting("DEFAULT_ORIGIN_NAME"):
        return True

    has_x = bool(get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X"))
    has_y = bool(get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y"))
    return has_x and has_y
