"""
라즈베리파이 클라이언트 진입점

실행 모드:
- BITBOX_RUN_MODE=once   : 1회 녹음 → 전송 → 결과 표시 후 종료 (기본값, 개발/테스트용)
- BITBOX_RUN_MODE=button : 버튼을 누를 때마다 반복 실행 (실제 설치 환경)

처리 흐름:
1. 버튼 입력 대기 (button 모드)
2. 마이크 녹음
3. 서버 /api/process 전송
4. 결과 화면 표시 + TTS 음성 재생
"""

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
    """서버 처리 중 점이 늘어나는 애니메이션으로 대기 상태를 표시합니다."""
    dots = ""
    while not stop_event.is_set():
        show_text(f"{base_message}{dots}")
        dots = "." if len(dots) >= 3 else dots + "."
        stop_event.wait(0.6)


def run_once() -> None:
    """1회 녹음 → 서버 전송 → 결과 표시 흐름을 실행합니다."""
    try:
        show_text("녹음 중...")
        audio_path = record_audio()

        # 서버 처리 중 스피너 표시 (별도 스레드)
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

        # 화면에 안내 문구 표시
        show_text(build_display_text(response))

        # TTS 음성 재생 (audio_base64가 있을 때만)
        audio_base64 = response.get("audio_base64")
        if audio_base64:
            play_tts_audio(audio_base64)

    except Exception as exc:
        # 사용자에게 기술적 메시지 대신 범용 안내를 표시
        # 상세 오류는 콘솔 로그로만 출력
        print(f"[ERROR] {exc}")
        show_text("오류가 발생했습니다. 다시 시도해 주세요.")


def run_button_loop() -> None:
    """버튼을 누를 때마다 run_once()를 반복 실행합니다."""
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
