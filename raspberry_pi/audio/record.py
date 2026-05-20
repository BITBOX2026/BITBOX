import os
from pathlib import Path

import sounddevice as sd
from dotenv import load_dotenv
from scipy.io.wavfile import write

load_dotenv()

DEFAULT_SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
DEFAULT_DURATION_SECONDS = int(os.getenv("RECORD_SECONDS", "5"))
DEFAULT_CHANNELS = 1

AUDIO_OUTPUT_PATH = os.getenv("AUDIO_OUTPUT_PATH", "recorded_audio.wav")


def record_audio(
    output_path: str = AUDIO_OUTPUT_PATH,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> str:
    """마이크 입력을 받아 WAV 파일로 저장합니다."""

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
