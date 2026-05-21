import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.services.pipeline import run_pipeline  # noqa: E402
from app.services.settings_helper import clear_settings_cache  # noqa: E402


ROUTE_CASES = [
    "서울역에서 강남역 가는 버스 알려줘",
    "강남역에서 서울역 가는 버스 알려줘",
    "잠실역에서 홍대입구역 가는 버스 알려줘",
    "서울역에서 강남역 가는 대중교통 알려줘",
    "서울역에서 강남역 가는 지하철 알려줘",
    "강남역 가는 버스 알려줘",
    "서울역에서 가는 버스 알려줘",
]


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="BITBOX route regression test without real STT."
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Actually call OpenAI/Kakao/ODsay. Omitted by default.",
    )
    args = parser.parse_args()

    os.environ["USE_MOCK_EXTERNALS"] = "false" if args.real else "true"
    clear_settings_cache()

    print("mode:", "real" if args.real else "mock")

    for transcript in ROUTE_CASES:
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

    print("\n--- route case ---")
    print("input:", transcript)
    print("status:", result.get("status"))
    print("message:", result.get("message"))
    print("origin:", data.get("origin"))
    print("destination:", data.get("destination"))
    print("transport_mode:", data.get("transport_mode"))
    print("bus_number:", data.get("bus_number"))
    print("total_time_min:", data.get("total_time_min"))
    print("payment:", data.get("payment"))
    print("source:", data.get("source"))
    print("error:", is_error)


if __name__ == "__main__":
    asyncio.run(main())
