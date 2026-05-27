"""
마이크 녹음 모듈

sounddevice로 마이크 입력을 받아 WAV 파일로 저장합니다.
녹음 시간, 샘플레이트, 저장 경로는 환경변수로 설정할 수 있습니다.

환경변수:
- RECORD_SECONDS     : 녹음 시간 (초, 기본값: 5)
- SAMPLE_RATE        : 샘플레이트 (Hz, 기본값: 16000)
- AUDIO_OUTPUT_PATH  : 저장 파일 경로 (기본값: recorded_audio.wav)
"""

import os
from pathlib import Path

import sounddevice as sd
from dotenv import load_dotenv
from scipy.io.wavfile import write

load_dotenv()

DEFAULT_SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
DEFAULT_DURATION_SECONDS = int(os.getenv("RECORD_SECONDS", "5"))
DEFAULT_CHANNELS = 1  # 모노 녹음 (OpenAI STT는 모노를 권장)

AUDIO_OUTPUT_PATH = os.getenv("AUDIO_OUTPUT_PATH", "recorded_audio.wav")


def record_audio(
    output_path: str = AUDIO_OUTPUT_PATH,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> str:
    """마이크 입력을 받아 WAV 파일로 저장하고 파일 경로를 반환합니다."""

    path = Path(output_path)

    # 저장 디렉토리가 없으면 생성
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        audio_data = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=DEFAULT_CHANNELS,
            dtype="int16",
        )
        sd.wait()  # 녹음이 끝날 때까지 블로킹 대기

        write(path, sample_rate, audio_data)

    except Exception as exc:
        raise RuntimeError(f"오디오 녹음 중 오류가 발생했습니다: {exc}") from exc

    return str(path)
