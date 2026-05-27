import os
import threading

from raspberry_pi.audio.player import play_tts_audio
from raspberry_pi.audio.record import record_audio
from raspberry_pi.display.screen import show_text
from raspberry_pi.services.server_client import send_audio_to_server
from raspberry_pi.utils.response_formatter import build_display_text


RUN_MODE_ONCE = "once"
RUN_MODE_BUTTON = "button"


def _spinner(stop_event: threading.Event, base_message: str) -> None:
    """서버 처리 중 점이 늘어나는 텍스트로 대기 중임을 알립니다."""

    dots = ""
    while not stop_event.is_set():
        show_text(f"{base_message}{dots}")
        dots = "." if len(dots) >= 3 else dots + "."
        stop_event.wait(0.6)


def run_once() -> None:
    try:
        show_text("녹음 중...")
        audio_path = record_audio()

        stop_event = threading.Event()
        spinner_thread = threading.Thread(
            target=_spinner,
            args=(stop_event, "처리 중"),
            daemon=True,
        )
        spinner_thread.start()

        try:
            response = send_audio_to_server(audio_path)
        finally:
            stop_event.set()
            spinner_thread.join()

        display_text = build_display_text(response)
        show_text(display_text)

        audio_base64 = response.get("audio_base64")
        if audio_base64:
            play_tts_audio(audio_base64)

    except Exception as exc:
        error_msg = str(exc) if str(exc) else "처리 중 오류가 발생했습니다."
        print(f"[ERROR] {error_msg}")
        # 터미널 벨: 오류 발생 시 청각 피드백
        print("\a", end="", flush=True)
        show_text(error_msg)


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
