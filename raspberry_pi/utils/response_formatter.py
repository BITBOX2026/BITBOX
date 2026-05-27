def safe_text(value: object, default: str = "정보 없음") -> str:
    """None 또는 빈 문자열이면 default를 반환합니다."""

    if value is None:
        return default

    if isinstance(value, str) and not value.strip():
        return default

    return str(value)


def build_display_text(response: dict) -> str:
    """서버 응답에서 화면 출력 문구를 만듭니다. message 필드를 우선 사용합니다."""

    message = response.get("message")
    if message:
        return str(message)

    data = response.get("data", {})

    origin = safe_text(data.get("origin"))
    destination = safe_text(data.get("destination"))
    bus_number = safe_text(data.get("bus_number"))
    arrival_time = safe_text(data.get("arrival_time"))
    total_time_min = safe_text(data.get("total_time_min"))
    payment = safe_text(data.get("payment"))

    return (
        f"출발지: {origin}\n"
        f"목적지: {destination}\n"
        f"버스 번호: {bus_number}\n"
        f"도착 시간: {arrival_time}\n"
        f"소요 시간: {total_time_min}\n"
        f"요금: {payment}"
    )
