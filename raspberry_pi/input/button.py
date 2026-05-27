import time

import RPi.GPIO as GPIO

PIN = 18


def wait_for_button() -> None:
    """버튼이 눌릴 때까지 블로킹 대기합니다."""

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    try:
        GPIO.wait_for_edge(PIN, GPIO.RISING)
        time.sleep(0.2)
    finally:
        GPIO.cleanup(PIN)