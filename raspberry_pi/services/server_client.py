# 서버 통신 모듈
# 역할:
# - 음성 파일 서버 전송
# - JSON 응답 반환
# - timeout으로 무한 대기 방지

import requests

URL = "http://YOUR_SERVER_IP:8000/api/process"


def send_audio(path):
    try:
        with open(path, "rb") as f:
            res = requests.post(
                URL,
                files={"file": f},
                timeout=10
            )

        return res.json() if res.status_code == 200 else None

    except requests.exceptions.RequestException:
        return None