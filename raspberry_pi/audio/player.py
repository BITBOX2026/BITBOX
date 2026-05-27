"""
오디오 재생 모듈

라즈베리파이의 aplay 명령어로 WAV 파일을 재생합니다.
서버에서 받은 base64 인코딩 TTS 음성을 임시 파일로 변환 후 재생합니다.
"""

import base64
import subprocess
import tempfile
from pathlib import Path


def play_audio_file(audio_path: str) -> None:
    """로컬 WAV 파일을 aplay로 재생합니다."""
    path = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    if not path.is_file():
        raise ValueError(f"파일 경로가 아닙니다: {audio_path}")

    try:
        subprocess.run(["aplay", str(path)], check=True)

    except FileNotFoundError as exc:
        raise RuntimeError("오디오 재생 프로그램(aplay)을 찾지 못했습니다.") from exc

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"오디오 재생 중 오류가 발생했습니다: {exc}") from exc


def play_tts_audio(audio_base64: str) -> None:
    """
    서버에서 받은 base64 TTS 음성을 임시 파일로 저장하고 재생합니다.

    재생 후 임시 파일은 항상 삭제됩니다 (finally 블록).
    """
    if not audio_base64 or not audio_base64.strip():
        return

    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception as exc:
        raise ValueError(f"TTS 오디오 디코딩 실패: {exc}") from exc

    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        subprocess.run(["aplay", str(tmp_path)], check=True)

    except FileNotFoundError as exc:
        raise RuntimeError("오디오 재생 프로그램(aplay)을 찾지 못했습니다.") from exc

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"TTS 오디오 재생 중 오류가 발생했습니다: {exc}") from exc

    finally:
        # 재생 성공 여부와 관계없이 임시 파일 삭제
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
