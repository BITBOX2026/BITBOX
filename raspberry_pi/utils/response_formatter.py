"""
서버 응답 → 화면 표시 문구 변환

서버가 반환한 JSON 응답에서 사용자에게 보여줄 텍스트를 생성합니다.
message 필드가 있으면 그대로 사용하고,
없으면 data 필드의 개별 항목을 조합해 표시합니다.
"""


def safe_text(value: object, default: str = "정보 없음") -> str:
    """None 또는 빈 문자열이면 default를 반환합니다."""
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return str(value)


def build_display_text(response: dict) -> str:
    """
    서버 응답에서 화면 출력 문구를 만듭니다.

    message 필드가 있으면 우선 사용합니다 (일반적으로 항상 존재).
    없을 경우 data 필드에서 개별 항목을 조합합니다 (폴백용).
    """
    message = response.get("message")
    if message:
        return str(message)

    # message가 없는 경우 data에서 직접 조합 (구버전 서버 호환)
    data = response.get("data", {})
    return (
        f"출발지: {safe_text(data.get('origin'))}\n"
        f"목적지: {safe_text(data.get('destination'))}\n"
        f"버스 번호: {safe_text(data.get('bus_number'))}\n"
        f"도착 시간: {safe_text(data.get('arrival_time'))}\n"
        f"소요 시간: {safe_text(data.get('total_time_min'))}\n"
        f"요금: {safe_text(data.get('payment'))}"
    )
