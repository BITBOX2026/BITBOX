# 음성 재생 모듈
# 역할:
# - 서버에서 받은 mp3 다운로드 후 재생

import requests
import subprocess

PATH = "/tmp/tts.mp3"


def play_audio(url):
    with open(PATH, "wb") as f:
        f.write(requests.get(url).content)

    subprocess.run(["mpg321", PATH])