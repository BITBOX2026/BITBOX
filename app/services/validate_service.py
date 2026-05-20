from app.services.constants import MIN_CONFIDENCE
from app.services.service_types import ParsedIntent, ValidationResult


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

    # 현재는 이동 중 사용을 전제로 음성 출발지를 필수로 받습니다.
    # DEFAULT_ORIGIN_X/Y fallback은 transport_service.py에 남겨 확장 가능하게 둡니다.
    if parsed.intent == "route" and not parsed.origin_text:
        return ValidationResult(
            is_valid=False,
            message="출발지를 말씀해 주세요.",
        )

    if parsed.intent == "arrival" and not parsed.bus_number:
        return ValidationResult(
            is_valid=False,
            message="버스 번호를 찾지 못했습니다. 버스 번호를 다시 말씀해 주세요.",
        )

    return ValidationResult(
        is_valid=True,
        message="검증 성공",
    )
