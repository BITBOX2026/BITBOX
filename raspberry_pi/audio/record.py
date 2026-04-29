# 마이크 입력을 받아 음성 파일로 저장하는 녹음 파일입니다.

import os
from pathlib import Path

import sounddevice as sd
from dotenv import load_dotenv
from scipy.io.wavfile import write

load_dotenv()

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_DURATION_SECONDS = 5
DEFAULT_CHANNELS = 1

AUDIO_OUTPUT_PATH = os.getenv("AUDIO_OUTPUT_PATH", "recorded_audio.wav")


def record_audio(
    output_path: str = AUDIO_OUTPUT_PATH,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> str:
    """
    마이크 입력을 받아 wav 파일로 저장하는 함수입니다.

    기능:
        - 지정된 시간 동안 오디오를 녹음합니다.
        - 저장 경로의 상위 폴더가 없으면 자동으로 생성합니다.
        - 저장된 파일 경로를 문자열로 반환합니다.
        - Windows, Linux, Raspberry Pi에서 상대 경로 기반으로 사용할 수 있습니다.

    입력:
        output_path:
            - 저장할 wav 파일 경로입니다.
            - 기본값은 .env의 AUDIO_OUTPUT_PATH입니다.

        duration_seconds:
            - 녹음 시간입니다.

        sample_rate:
            - 샘플링 레이트입니다.

    반환:
        str:
            - 저장된 오디오 파일 경로입니다.
    """

    path = Path(output_path)

    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        audio_data = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=DEFAULT_CHANNELS,
            dtype="int16",
        )
        sd.wait()

        write(path, sample_rate, audio_data)

    except Exception as exc:
        raise RuntimeError(f"오디오 녹음 중 오류가 발생했습니다: {exc}") from exc

    return str(path)