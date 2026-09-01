"""Generate fixed, non-personal Korean audio used by the submission demo."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "submission-audio"
SPEECH_URL = "http://127.0.0.1:8000/api/speech"

SEGMENTS = {
    "intro": "안녕하세요. 실시간 버스 정보와 음성 길찾기를 제공하는 비트박스 시연을 시작하겠습니다.",
    "live": "현재 백엔드와 프론트엔드가 실제 운영 모드로 실행 중이며, 장소 검색은 카카오, 버스 경로는 오디세이 실데이터를 사용합니다.",
    "gangnam_search": "첫 번째 목적지는 강남역입니다. 자동 완성에서 강남역 이호선을 선택해 잘못된 장소 검색을 방지합니다.",
    "gangnam_result": "올림픽공원역에서 강남역까지 삼사일이번 버스 경로가 조회되었습니다. 예상 소요 시간과 도보, 승차 구간을 함께 안내합니다.",
    "seoul_search": "두 번째 목적지는 서울역입니다. 서로 다른 거리의 목적지에서도 실제 버스 전용 경로를 다시 조회합니다.",
    "seoul_result": "서울역까지 삼이일사번 경로가 조회되었습니다. 환승과 도보를 포함한 일곱 개 이동 구간이 순서대로 표시됩니다.",
    "jamsil_search": "세 번째 목적지는 잠실역입니다. 가까운 목적지에서도 같은 방식으로 장소 좌표와 경로를 새로 요청합니다.",
    "jamsil_result": "잠실역까지 삼삼이삼번 버스로 약 십칠 분이 걸리는 경로가 조회되었습니다. 세 목적지 모두 안전 검증을 통과했습니다.",
    "voice": "마지막으로 실제 음성 입력을 시연합니다. 음성 처리 안내에 동의한 뒤 잠실역 길찾기를 말합니다.",
    "confirm": "음성 인식 결과가 비슷한 역 이름과 혼동될 수 있을 때는 임의로 안내하지 않고 장소 확인 화면을 제공합니다.",
    "finish": "후보를 선택하면 다시 실시간 경로를 조회합니다. 비트박스는 장소 확인, 실제 교통 데이터, 음성 안내를 하나의 흐름으로 제공합니다. 감사합니다.",
    "voice_input": "잠실역 가는 버스를 알려줘",
}


def synthesize(client: httpx.Client, text: str) -> bytes:
    response = client.post(SPEECH_URL, json={"text": text}, timeout=40)
    response.raise_for_status()
    encoded = response.json().get("audio_base64")
    if not encoded:
        raise RuntimeError("Speech endpoint returned no audio")
    audio = bytearray(base64.b64decode(encoded))
    # OpenAI streams WAV with sentinel RIFF/data sizes (0xffffffff). Chromium's
    # fake microphone expects finalized sizes, so make the otherwise-valid PCM
    # file seekable without transcoding it.
    if len(audio) >= 44 and audio[:4] == b"RIFF" and audio[36:40] == b"data":
        audio[4:8] = struct.pack("<I", len(audio) - 8)
        audio[40:44] = struct.pack("<I", len(audio) - 44)
    return bytes(audio)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, str | int]] = {}
    with httpx.Client() as client:
        for segment_id, text in SEGMENTS.items():
            audio = synthesize(client, text)
            output = OUTPUT_DIR / f"{segment_id}.wav"
            output.write_bytes(audio)
            manifest[segment_id] = {
                "text": text,
                "file": output.name,
                "bytes": len(audio),
            }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"segments": len(manifest), "output": str(OUTPUT_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
