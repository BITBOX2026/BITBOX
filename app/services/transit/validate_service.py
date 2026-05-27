"""
파이프라인 입력 검증

LLM이 분석한 ParsedIntent가 실제 교통 API를 호출하기에 충분한지 확인합니다.
confidence가 낮거나 필수 필드가 없으면 사용자에게 재입력을 요청합니다.
"""

from app.services.core.constants import MIN_CONFIDENCE
from app.services.core.service_types import ParsedIntent, ValidationResult
from app.services.core.settings_helper import get_setting


def validate_parsed_intent(parsed: ParsedIntent) -> ValidationResult:
    """LLM 분석 결과가 실제 조회 가능한 요청인지 검증합니다."""

    # 발화 의미를 전혀 파악하지 못한 경우
    if parsed.intent == "unknown":
        return ValidationResult(
            is_valid=False,
            message="요청 내용을 정확히 이해하지 못했습니다. 목적지나 버스 번호를 다시 말씀해 주세요.",
        )

    # LLM 신뢰도가 기준값(0.5) 미만이면 결과를 신뢰할 수 없음
    if parsed.confidence < MIN_CONFIDENCE:
        return ValidationResult(
            is_valid=False,
            message="음성 인식 결과가 불확실합니다. 다시 한 번 말씀해 주세요.",
        )

    if parsed.intent == "route":
        if not parsed.destination_text:
            return ValidationResult(is_valid=False, message="목적지를 말씀해 주세요.")

        # 출발지도 없고 기기 기본 출발지도 미설정인 경우
        if not parsed.origin_text and not _has_default_origin():
            return ValidationResult(is_valid=False, message="출발지를 말씀해 주세요.")

    if parsed.intent == "arrival":
        if not parsed.bus_number:
            return ValidationResult(is_valid=False, message="버스 번호를 말씀해 주세요.")
        if not parsed.stop_text:
            return ValidationResult(is_valid=False, message="어느 정류장 기준인지 말씀해 주세요.")

    return ValidationResult(is_valid=True, message="검증 성공")


def _has_default_origin() -> bool:
    """기기에 기본 출발지(설치 위치)가 설정되어 있는지 확인합니다."""
    if get_setting("DEFAULT_ORIGIN_NAME"):
        return True
    has_x = bool(get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X"))
    has_y = bool(get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y"))
    return has_x and has_y
