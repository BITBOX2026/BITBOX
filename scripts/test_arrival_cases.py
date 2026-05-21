import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.services import pipeline as pipeline_module  # noqa: E402
from app.services.pipeline import run_pipeline  # noqa: E402
from app.services.settings_helper import clear_settings_cache  # noqa: E402


ARRIVAL_CASES = [
    "402번 언제 와?",
    "서울역에서 402번 언제 와?",
    "강남역에서 146번 언제 와?",
    "서울역 정류장에 421번 언제 도착해?",
]


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="BITBOX arrival test without real STT."
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Actually call OpenAI/Public Data API. Omitted by default.",
    )
    args = parser.parse_args()

    os.environ["USE_MOCK_EXTERNALS"] = "false" if args.real else "true"
    clear_settings_cache()
    pipeline_module.logger.disabled = True

    print("mode:", "real" if args.real else "mock")

    for transcript in ARRIVAL_CASES:
        result = await _run_text_pipeline(transcript)
        _print_case(transcript, result)


async def _run_text_pipeline(transcript: str) -> dict:
    async def fake_transcribe_audio(*args, **kwargs) -> str:
        return transcript

    with patch("app.services.pipeline.transcribe_audio", fake_transcribe_audio):
        return await run_pipeline(
            audio_bytes=b"transcript-only-test",
            filename="transcript.txt",
        )


def _print_case(transcript: str, result: dict) -> None:
    data = result.get("data") or {}
    is_error = result.get("status") != "success"

    print("\n--- arrival case ---")
    print("input:", transcript)
    print("status:", result.get("status"))
    print("message:", result.get("message"))
    print("stop_text:", data.get("stop_text"))
    print("bus_number:", data.get("bus_number"))
    print("arrival_time:", data.get("arrival_time"))
    print("source:", data.get("source"))
    print("error:", is_error)


if __name__ == "__main__":
    asyncio.run(main())
