# 음성 녹음 모듈
# 역할:
# - 마이크 입력을 WAV 파일로 저장
# - 장치 index 지정 가능 (환경 대응)

# DEVICE_INDEX는 직접 확인해서 넣어야 한다 → 코드로 자동 해결 불가

import sounddevice as sd
import scipy.io.wavfile as wav

FS = 16000
DURATION = 5
PATH = "/tmp/record.wav"

DEVICE = None  # 필요 시 숫자 지정


def record_audio():
    audio = sd.rec(
        int(FS * DURATION),
        samplerate=FS,
        channels=1,
        device=DEVICE
    )
    sd.wait()
    wav.write(PATH, FS, audio)
    return PATH