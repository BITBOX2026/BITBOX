# 라즈베리파이에서 FastAPI 서버로 음성 파일을 전송하는 클라이언트 파일입니다.

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/process")


def send_audio_to_server(audio_path: str) -> dict:
    """
    녹음된 음성 파일을 FastAPI 서버의 /api/process API로 전송하는 함수입니다.

    기능:
        - 라즈베리파이에 저장된 음성 파일을 multipart/form-data 형식으로 전송합니다.
        - 서버 응답을 JSON으로 변환하여 반환합니다.
        - 파일 없음, 서버 연결 실패, JSON 파싱 실패를 구분해서 예외를 발생시킵니다.

    입력:
        audio_path:
            - 전송할 음성 파일 경로입니다.
            - 예: "recorded_audio.wav"

    반환:
        dict:
            - 서버가 반환한 JSON 응답입니다.

    예:
        {
            "status": "success",
            "message": "강남역까지 가는 경로를 찾았습니다.",
            "data": {...}
        }
    """

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

    except requests.RequestException as exc:
        raise RuntimeError(f"서버 요청 중 오류가 발생했습니다: {exc}") from exc

    try:
        return response.json()

    except ValueError as exc:
        raise RuntimeError("서버 응답을 JSON으로 해석하지 못했습니다.") from exc