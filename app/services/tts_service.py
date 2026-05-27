import base64

from openai import AsyncOpenAI

from app.core.logger import get_logger
from app.services.constants import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE
from app.services.settings_helper import get_setting, is_mock_mode

logger = get_logger(__name__)

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=get_setting("OPENAI_API_KEY"))
    return _openai_client


async def generate_tts_audio(text: str) -> str | None:
    """
    텍스트를 OpenAI TTS API로 음성 변환하고 base64 문자열로 반환합니다.

    TTS 실패 시 None을 반환하며 전체 파이프라인을 중단하지 않습니다.
    mock 모드이거나 API 키가 없으면 None을 반환합니다.
    """

    if not text or not text.strip():
        return None

    if is_mock_mode():
        return None

    if not get_setting("OPENAI_API_KEY"):
        return None

    tts_model = get_setting("TTS_MODEL", DEFAULT_TTS_MODEL)
    tts_voice = get_setting("TTS_VOICE", DEFAULT_TTS_VOICE)

    try:
        client = _get_openai_client()

        response = await client.audio.speech.create(
            model=tts_model,
            voice=tts_voice,
            input=text,
            response_format="wav",
        )

        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode("utf-8")

    except Exception as exc:
        logger.warning("TTS 생성 실패 (텍스트 응답은 정상 반환): %s", exc)
        return None
