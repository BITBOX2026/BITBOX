"""
화면 출력 모듈

현재는 콘솔(터미널)에 텍스트를 출력합니다.
LCD 디스플레이를 연결하는 경우 이 파일만 수정하면 됩니다.

예시 (16x2 LCD, I2C):
    from RPLCD.i2c import CharLCD
    lcd = CharLCD('PCF8574', 0x27)

    def show_text(text: str) -> None:
        lcd.clear()
        lcd.write_string(text[:32])  # 최대 2줄 32자
"""


def show_text(text: str) -> None:
    """텍스트를 화면에 출력합니다."""
    print(text)
