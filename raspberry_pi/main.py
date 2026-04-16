# 메인 컨트롤러
# 역할:
# - 전체 흐름 제어 (버튼 → 녹음 → 서버 → 출력)
# - 예외 발생 시에도 시스템 유지

import time

from input.button import wait_for_button
from audio.record import record_audio
from services.server_client import send_audio
from display.screen import show_text
from audio.player import play_audio


def main():
    while True:
        try:
            wait_for_button()

            show_text("녹음 중...")
            path = record_audio()

            show_text("처리 중...")
            response = send_audio(path)

            if not response:
                show_text("서버 오류")
                continue

            message = response.get("message", "결과 없음")
            show_text(message)

            data = response.get("data", {})

            if data.get("destination"):
                show_text(f"{data['destination']} → {data['bus_number']}")

            if response.get("audio_url"):
                play_audio(response["audio_url"])

        except Exception as e:
            print(f"[ERROR] {e}")
            show_text("시스템 오류")
            time.sleep(1)


if __name__ == "__main__":
    main()