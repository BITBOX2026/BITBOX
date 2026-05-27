import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/process")


def send_audio_to_server(audio_path: str) -> dict:
    """녹음된 WAV 파일을 서버 /api/process로 전송하고 JSON 응답을 반환합니다."""

    path = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(f"음성 파일을 찾을 수 없습니다: {audio_path}")

    if not path.is_file():
        raise ValueError(f"파일 경로가 아닙니다: {audio_path}")

    try:
        with path.open("rb") as audio_file:
            files = {
                "file": (path.name, audio_file, "audio/wav"),
            }

            response = requests.post(
                API_URL,
                files=files,
                timeout=30,
            )

        response.raise_for_status()

    except requests.ConnectionError as exc:
        raise RuntimeError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from exc
    except requests.Timeout as exc:
        raise RuntimeError("서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"서버 요청 중 오류가 발생했습니다: {exc}") from exc

    try:
        return response.json()

    except ValueError as exc:
        raise RuntimeError("서버 응답을 JSON으로 해석하지 못했습니다.") from exc
