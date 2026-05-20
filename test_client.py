import argparse
import json
import tempfile
import wave
from pathlib import Path

from raspberry_pi.services.server_client import send_audio_to_server


DEFAULT_AUDIO_PATH = Path("recorded_audio.wav")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send an audio file to the BITBOX backend /api/process endpoint."
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        help="Audio file path. If omitted, recorded_audio.wav is used when present.",
    )
    args = parser.parse_args()

    if args.audio_path:
        audio_path = Path(args.audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        _send_and_print(audio_path)
        return

    if DEFAULT_AUDIO_PATH.exists():
        _send_and_print(DEFAULT_AUDIO_PATH)
        return

    print("recorded_audio.wav not found. Sending a temporary mock WAV file.")
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_audio_path = Path(temp_dir) / "mock_audio.wav"
        _create_mock_wav(mock_audio_path)
        _send_and_print(mock_audio_path)


def _send_and_print(audio_path: Path) -> None:
    response = send_audio_to_server(str(audio_path))

    print("Server response:")
    print(json.dumps(response, ensure_ascii=False, indent=2))


def _create_mock_wav(path: Path) -> None:
    sample_rate = 16_000
    duration_seconds = 1
    silence_frame = b"\x00\x00"

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence_frame * sample_rate * duration_seconds)


if __name__ == "__main__":
    main()
