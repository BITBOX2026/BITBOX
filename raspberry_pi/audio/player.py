# 라즈베리파이에서 오디오 파일 또는 오디오 URL을 재생하는 파일입니다.

from pathlib import Path
import subprocess
import tempfile

import requests


def play_audio_file(audio_path: str) -> None:
    """
    로컬 오디오 파일을 재생하는 함수입니다.

    기능:
        - 파일 존재 여부를 확인합니다.
        - 파일 경로가 실제 파일인지 확인합니다.
        - Raspberry Pi의 aplay 명령으로 wav 파일을 재생합니다.
        - 재생 프로그램이 없거나 재생에 실패하면 예외를 발생시킵니다.
    """

    path = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    if not path.is_file():
        raise ValueError(f"파일 경로가 아닙니다: {audio_path}")

    try:
        subprocess.run(
            ["aplay", str(path)],
            check=True,
        )

    except FileNotFoundError as exc:
        raise RuntimeError("오디오 재생 프로그램(aplay)을 찾지 못했습니다.") from exc

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"오디오 재생 중 오류가 발생했습니다: {exc}") from exc


def play_audio_from_url(audio_url: str) -> None:
    """
    오디오 URL을 다운로드한 뒤 재생하는 함수입니다.

    기능:
        - URL이 비어 있으면 예외를 발생시킵니다.
        - 네트워크 오류와 HTTP 오류를 처리합니다.
        - 임시 파일로 저장한 뒤 aplay 명령으로 재생합니다.
    """

    if not audio_url or not audio_url.strip():
        raise ValueError("오디오 URL이 비어 있습니다.")

    try:
        response = requests.get(audio_url, timeout=15)
        response.raise_for_status()

    except requests.RequestException as exc:
        raise RuntimeError(f"오디오 파일 다운로드 중 오류가 발생했습니다: {exc}") from exc

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(response.content)
            temp_path = Path(temp_file.name)

    except OSError as exc:
        raise RuntimeError(f"오디오 임시 파일 저장 중 오류가 발생했습니다: {exc}") from exc

    try:
        subprocess.run(
            ["aplay", str(temp_path)],
            check=True,
        )

    except FileNotFoundError as exc:
        raise RuntimeError("오디오 재생 프로그램(aplay)을 찾지 못했습니다.") from exc

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"오디오 재생 중 오류가 발생했습니다: {exc}") from exc