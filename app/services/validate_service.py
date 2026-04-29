# LLM이 추출한 결과를 실제 조회 가능한 요청인지 검증하는 가드레일 서비스 파일입니다.

from app.services.constants import MIN_CONFIDENCE
from app.services.service_types import ParsedIntent, ValidationResult


def validate_parsed_intent(parsed: ParsedIntent) -> ValidationResult:
    """
    LLM 분석 결과가 서비스에서 처리 가능한지 검증하는 함수입니다.

    기능:
        - 의도가 불명확한 요청을 차단합니다.
        - 목적지 없는 경로 요청을 차단합니다.
        - 버스 번호 없는 도착 정보 요청을 차단합니다.
        - confidence가 너무 낮은 요청을 차단합니다.

    입력:
        parsed:
            - LLM 분석 결과입니다.

    반환:
        ValidationResult:
            - 검증 성공 여부와 사용자 안내 메시지입니다.
    """

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
            message="목적지를 찾지 못했습니다. 가고 싶은 장소를 다시 말씀해 주세요.",
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