"""Generate repeatable Korean QA audio and run it through the real voice pipeline."""

import asyncio
import base64
import json

from app.services.ai.tts_service import generate_tts_audio
from app.services.pipeline import _run_pipeline_core


PHRASES = [
    "올림픽공원역에서 삼사일이 번 버스 언제 도착해요",
    "올림픽공원역에서 삼삼이삼 번 버스 언제 와요",
    "올림픽공원역에서 삼천사백이십삼 번 버스 언제 와요",
    "올림픽공원역에서 삼사일삼 번 버스 언제 와요",
    "강남역 가는 버스 알려줘",
]


async def main() -> None:
    output = []
    for index, phrase in enumerate(PHRASES):
        encoded_audio = await generate_tts_audio(phrase)
        if not encoded_audio:
            output.append({"spoken": phrase, "status": "tts_error"})
            continue
        result = await _run_pipeline_core(
            base64.b64decode(encoded_audio),
            "sample.wav",
            f"voice-qa-{index}",
        )
        data = result.get("data", {})
        output.append(
            {
                "spoken": phrase,
                "status": result.get("status"),
                "transcript": data.get("transcript"),
                "bus_number": data.get("bus_number"),
                "message": result.get("message"),
                "needs_confirmation": data.get("needs_confirmation"),
                "confirmation": data.get("confirmation"),
            }
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
