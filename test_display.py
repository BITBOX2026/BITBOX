# 서버 응답을 라즈베리파이 화면 출력 문구로 변환하는 로직을 테스트하는 파일입니다.

from raspberry_pi.utils.response_formatter import build_display_text


def main():
    """
    bus_number, arrival_time이 None이어도 화면에 'None'이 표시되지 않는지 확인합니다.
    """

    response = {
        "status": "success",
        "message": "",
        "data": {
            "destination": "강남역",
            "bus_number": None,
            "arrival_time": None,
        },
    }

    display_text = build_display_text(response)

    print("화면 출력 테스트 결과:")
    print(display_text)


if __name__ == "__main__":
    main()