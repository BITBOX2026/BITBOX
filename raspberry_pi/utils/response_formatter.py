# 서버 응답을 라즈베리파이 화면 출력용 문구로 변환하는 파일입니다.


def safe_text(value: object, default: str = "정보 없음") -> str:
    """
    화면에 표시할 값이 None이거나 빈 문자열이면 기본 문구로 바꾸는 함수입니다.

    기능:
        - bus_number, arrival_time 등이 None일 때 "None"이 그대로 표시되는 문제를 방지합니다.
        - LCD 출력 또는 콘솔 출력에서 사용자에게 보기 좋은 문구를 제공합니다.
    """

    if value is None:
        return default

    if isinstance(value, str) and not value.strip():
        return default

    return str(value)


def build_display_text(response: dict) -> str:
    """
    서버 응답에서 LCD 또는 콘솔에 출력할 문구를 만드는 함수입니다.

    기능:
        - 서버가 생성한 message를 우선 사용합니다.
        - message가 없을 경우 data 필드를 조합합니다.
        - data 안의 값이 None이어도 화면에 "None"이 표시되지 않게 합니다.
    """

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
