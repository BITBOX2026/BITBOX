import io

from openai import AsyncOpenAI

from app.services.constants import DEFAULT_STT_MODEL
from app.services.exceptions import STTProcessingError
from app.services.settings_helper import get_setting, is_mock_mode

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
    """음성 bytes를 OpenAI STT API로 텍스트로 변환합니다."""

    if not audio_bytes:
        raise STTProcessingError("음성 파일이 비어 있습니다.")

    if is_mock_mode():
        return "서울역에서 강남역 가는 버스 알려줘"

    if not get_setting("OPENAI_API_KEY"):
        raise STTProcessingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    stt_model = get_setting("STT_MODEL", DEFAULT_STT_MODEL)

    try:
        client = _get_openai_client()

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename or "audio.wav"

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
