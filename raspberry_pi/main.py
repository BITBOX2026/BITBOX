# 라즈베리파이의 전체 실행 흐름을 관리하는 메인 파일입니다.

from raspberry_pi.audio.record import record_audio
from raspberry_pi.display.screen import show_text
from raspberry_pi.services.server_client import send_audio_to_server


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

    destination = safe_text(data.get("destination"))
    bus_number = safe_text(data.get("bus_number"))
    arrival_time = safe_text(data.get("arrival_time"))

    return (
        f"목적지: {destination}\n"
        f"버스 번호: {bus_number}\n"
        f"도착 시간: {arrival_time}"
    )


def run_once() -> None:
    """
    한 번의 음성 안내 흐름을 실행하는 함수입니다.

    처리 순서:
        1. 음성 녹음
        2. 서버로 음성 파일 전송
        3. 서버 응답 수신
        4. LCD 또는 콘솔에 안내 문구 출력
    """

    try:
        show_text("녹음 중...")
        audio_path = record_audio()

        show_text("처리 중...")
        response = send_audio_to_server(audio_path)

        display_text = build_display_text(response)
        show_text(display_text)

    except Exception as exc:
        print(f"[ERROR] {exc}")
        show_text("처리 중 오류가 발생했습니다.")


def main() -> None:
    """
    라즈베리파이 프로그램 시작 함수입니다.

    기능:
        - 현재는 테스트를 위해 run_once()를 한 번 실행합니다.
        - 버튼 입력 방식으로 바꾸려면 이 함수 안에서 버튼 이벤트를 기다리면 됩니다.
    """

    show_text("BITBOX 준비 완료")
    run_once()


if __name__ == "__main__":
    main()