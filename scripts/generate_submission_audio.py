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

# 나레이션에는 노선 번호나 소요 시간 같은 조회 시점 값을 넣지 않습니다. 이 음성은
# 녹화 전에 미리 합성되는데 실제 경로는 녹화 때마다 달라지므로, 숫자를 미리 말해 두면
# 화면과 어긋난 순간 영상 전체가 거짓 주장이 됩니다. 값은 화면이 보여 주고, 나레이션은
# 절차만 설명합니다.
SEGMENTS = {
    "intro": "안녕하세요. 실시간 버스 정보와 음성 길찾기를 제공하는 비트박스 시연을 시작하겠습니다.",
    "live": "백엔드와 프론트엔드가 실제 외부 API에 연결된 상태로 실행 중이며, 장소 검색은 카카오, 버스 경로는 오디세이 실데이터를 사용합니다.",
    "gangnam_search": "첫 번째 목적지는 강남역입니다. 자동 완성에서 강남역 이호선을 선택해 잘못된 장소 검색을 방지합니다.",
    "gangnam_result": "올림픽공원역에서 강남역까지 실시간 버스 경로가 조회되었습니다. 화면의 노선 번호와 소요 시간은 조회 시점의 실제 응답입니다.",
    "gangnam_map": "지도 보기로 전환하면 정류장 순서를 이어 만든 예상 경로가 노선 번호와 함께 표시됩니다.",
    "seoul_search": "두 번째 목적지는 서울역입니다. 서로 다른 거리의 목적지에서도 실제 버스 전용 경로를 다시 조회합니다.",
    "seoul_result": "서울역까지도 같은 절차로 경로를 다시 조회했습니다. 환승 횟수와 예상 요금, 전체 이동 시간을 함께 확인할 수 있습니다.",
    "seoul_map": "환승이 있는 경로는 구간마다 다른 색으로 나뉘어 갈아타는 지점을 확인할 수 있습니다.",
    "jamsil_search": "세 번째 목적지는 잠실역입니다. 가까운 목적지에서도 같은 방식으로 장소 좌표와 경로를 새로 요청합니다.",
    "jamsil_result": "잠실역까지의 경로도 독립적으로 조회했습니다. 세 목적지 모두 좌표 확인과 안전 검증 절차를 거쳤습니다.",
    "jamsil_map": "출발 정류장과 도착 지점에는 표식이 표시되며, 지도는 전체 경로가 들어오도록 자동으로 맞춰집니다.",
    "voice": "마지막으로 음성 입력 경로를 시연합니다. 매번 같은 조건으로 재현할 수 있도록 준비한 음성 샘플을 마이크로 넣어, 인식과 장소 확인 절차를 그대로 확인합니다.",
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


def pad_with_silence(audio: bytes, seconds: float) -> bytes:
    """뒤에 무음을 붙여 가짜 마이크가 같은 문장을 두 번 들려주지 않게 합니다.

    Chromium 의 ``--use-file-for-fake-audio-capture`` 는 파일을 끝까지 재생한 뒤
    처음부터 다시 재생합니다. 발화가 녹음 창보다 짧으면 STT 가 같은 문장을 두 번
    받아 확인 화면에 "...알려줘. ...알려줘." 처럼 중복된 인식 결과가 남습니다.
    """
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[36:40] != b"data":
        return audio
    channels = struct.unpack_from("<H", audio, 22)[0]
    sample_rate = struct.unpack_from("<I", audio, 24)[0]
    bits_per_sample = struct.unpack_from("<H", audio, 34)[0]
    frame_bytes = max(1, channels * (bits_per_sample // 8))
    silence = b"\0" * (int(sample_rate * seconds) * frame_bytes)
    padded = bytearray(audio + silence)
    padded[4:8] = struct.pack("<I", len(padded) - 8)
    padded[40:44] = struct.pack("<I", len(padded) - 44)
    return bytes(padded)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, str | int]] = {}
    with httpx.Client() as client:
        for segment_id, text in SEGMENTS.items():
            audio = synthesize(client, text)
            # 발화 2.4초 + 무음 4초. 시연 스크립트의 5초 녹음 창 안에서 한 번만 들립니다.
            if segment_id == "voice_input":
                audio = pad_with_silence(audio, 4.0)
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
