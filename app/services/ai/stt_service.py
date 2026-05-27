"""
STT (Speech-to-Text) 서비스

음성 파일 bytes를 한국어 텍스트로 변환합니다.
OpenAI Whisper API를 사용하며, mock 모드에서는 API 호출 없이 고정 문장을 반환합니다.
"""

import io

from openai import AsyncOpenAI

from app.services.core.constants import DEFAULT_STT_MODEL
from app.services.core.exceptions import STTProcessingError
from app.services.core.settings_helper import get_setting, is_mock_mode

# 모듈 수준 클라이언트 — 요청마다 새로 생성하지 않고 재사용
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=get_setting("OPENAI_API_KEY"))
    return _openai_client


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
) -> str:
    """
    음성 bytes를 한국어 텍스트로 변환합니다.

    mock 모드: "서울역에서 강남역 가는 버스 알려줘" 고정 반환
    real 모드: OpenAI Whisper API 호출
    """

    if not audio_bytes:
        raise STTProcessingError("음성 파일이 비어 있습니다.")

    if is_mock_mode():
        return "서울역에서 강남역 가는 버스 알려줘"

    if not get_setting("OPENAI_API_KEY"):
        raise STTProcessingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    stt_model = get_setting("STT_MODEL", DEFAULT_STT_MODEL)

    try:
        client = _get_openai_client()

        # BytesIO로 래핑하고 파일명을 설정해야 OpenAI가 확장자로 형식을 인식함
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        transcription = await client.audio.transcriptions.create(
            model=stt_model,
            file=audio_file,
            language="ko",
            response_format="json",
        )

        text = transcription.text
        if not text or not text.strip():
            raise STTProcessingError("STT 결과가 비어 있습니다.")

        return text.strip()

    except STTProcessingError:
        raise

    except Exception as exc:
        raise STTProcessingError(f"STT 처리 중 오류가 발생했습니다: {exc}") from exc
