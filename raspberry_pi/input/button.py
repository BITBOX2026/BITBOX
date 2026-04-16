# 버튼 입력 모듈
# 역할:
# - GPIO 인터럽트 기반 버튼 감지
# - CPU 사용 최소화

import RPi.GPIO as GPIO
import time

PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


def wait_for_button():
    GPIO.wait_for_edge(PIN, GPIO.RISING)
    time.sleep(0.2)