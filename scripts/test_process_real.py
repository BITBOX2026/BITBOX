import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")


def print_result(response):
    print("\n========== /api/process 테스트 결과 ==========")
    print("HTTP status code:", response.status_code)

    try:
        body = response.json()
    except Exception:
        print("[ERROR] JSON 응답이 아닙니다.")
        print(response.text[:2000])
        return

    print("\n========== Raw JSON ==========")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    print("\n========== 요약 ==========")
    print("status:", body.get("status"))
    print("message:", body.get("message"))

    data = body.get("data") or {}

    print("origin:", data.get("origin"))
    print("destination:", data.get("destination"))
    print("transport_mode:", data.get("transport_mode"))
    print("bus_number:", data.get("bus_number"))
    print("arrival_time:", data.get("arrival_time"))
    print("total_time_min:", data.get("total_time_min"))
    print("payment:", data.get("payment"))
    print("bus_transit_count:", data.get("bus_transit_count"))
    print("subway_transit_count:", data.get("subway_transit_count"))
    print("transfer_count:", data.get("transfer_count"))
    print("path_type:", data.get("path_type"))
    print("source:", data.get("source"))


def main():
    parser = argparse.ArgumentParser(
        description="BITBOX /api/process real mode 테스트"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="업로드할 테스트 음성 파일 경로. 예: test_audio.wav",
    )
    args = parser.parse_args()

    audio_path = Path(args.file)

    if not audio_path.exists():
        print(f"[ERROR] 테스트 음성 파일을 찾을 수 없습니다: {audio_path}")
        print("먼저 test_audio.wav 파일을 생성하거나 경로를 확인하세요.")
        return

    use_mock = os.getenv("USE_MOCK_EXTERNALS", "true")
    print("[INFO] USE_MOCK_EXTERNALS:", use_mock)

    if use_mock.lower() == "false":
        print("[INFO] real mode입니다. OpenAI/Kakao/ODsay 실제 API를 호출합니다.")
        print("[INFO] API 키 값은 출력하지 않습니다.")
    else:
        print("[INFO] mock mode입니다. 외부 API를 호출하지 않을 수 있습니다.")

    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as e:
        print("[ERROR] FastAPI app import 실패")
        print(type(e).__name__, str(e))
        return

    client = TestClient(app)

    mime_type, _ = mimetypes.guess_type(str(audio_path))
    if not mime_type:
        mime_type = "audio/wav"

    print("[INFO] 업로드 파일:", audio_path)
    print("[INFO] MIME type:", mime_type)

    with audio_path.open("rb") as f:
        files = {
            "file": (
                audio_path.name,
                f,
                mime_type,
            )
        }

        response = client.post("/api/process", files=files)

    print_result(response)


if __name__ == "__main__":
    main()