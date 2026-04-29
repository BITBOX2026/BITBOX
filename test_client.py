# 라즈베리파이 서버 전송 함수를 PC에서 먼저 테스트하는 파일입니다.

from raspberry_pi.services.server_client import send_audio_to_server


def main():
    """
    test_audio.mp3 파일을 백엔드 서버로 전송하고 응답을 출력합니다.
    """

    response = send_audio_to_server("test_audio.mp3")

    print("서버 응답:")
    print(response)


if __name__ == "__main__":
    main()