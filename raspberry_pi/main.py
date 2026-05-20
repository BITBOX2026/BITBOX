import os

from raspberry_pi.audio.record import record_audio
from raspberry_pi.display.screen import show_text
from raspberry_pi.services.server_client import send_audio_to_server
from raspberry_pi.utils.response_formatter import build_display_text


RUN_MODE_ONCE = "once"
RUN_MODE_BUTTON = "button"


def run_once() -> None:
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


def run_button_loop() -> None:
    from raspberry_pi.input.button import wait_for_button

    while True:
        show_text("버튼을 누르세요.")
        wait_for_button()
        run_once()


def main() -> None:
    run_mode = os.getenv("BITBOX_RUN_MODE", RUN_MODE_ONCE).strip().lower()

    show_text("BITBOX 준비 완료")

    if run_mode == RUN_MODE_BUTTON:
        try:
            run_button_loop()
        except KeyboardInterrupt:
            show_text("BITBOX 종료")
        return

    run_once()


if __name__ == "__main__":
    main()
