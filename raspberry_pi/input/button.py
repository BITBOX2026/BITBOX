"""
버튼 입력 모듈

라즈베리파이 GPIO 핀에 연결된 물리 버튼 입력을 처리합니다.
GPIO 초기화는 모듈 임포트 시 1회만 수행하고, 프로그램 종료 시 atexit으로 정리합니다.
버튼을 반복해서 누를 때마다 매번 재초기화하는 것을 방지합니다.

하드웨어 연결:
- 버튼 한쪽 → GPIO 18번 핀 (BCM)
- 버튼 다른 쪽 → 3.3V 전원 핀
"""

import atexit
import time

import RPi.GPIO as GPIO

BUTTON_PIN = 18  # BCM 핀 번호


def _setup() -> None:
    """GPIO 핀을 풀다운 입력 모드로 초기화합니다."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


def _cleanup() -> None:
    """프로그램 종료 시 GPIO 핀을 정리합니다."""
    GPIO.cleanup(BUTTON_PIN)


# 모듈 임포트 시 1회 초기화
_setup()

# 프로그램 종료 시 자동 정리 등록
atexit.register(_cleanup)


def wait_for_button() -> None:
    """버튼이 눌릴 때까지 블로킹 대기합니다."""
    GPIO.wait_for_edge(BUTTON_PIN, GPIO.RISING)
    time.sleep(0.2)  # 채터링(버튼 잔진동) 방지를 위한 디바운싱
