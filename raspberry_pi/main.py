# 라즈베리파이의 전체 실행 흐름을 관리하는 메인 파일입니다.

from raspberry_pi.audio.record import record_audio
from raspberry_pi.display.screen import show_text
from raspberry_pi.services.server_client import send_audio_to_server
from raspberry_pi.utils.response_formatter import build_display_text


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