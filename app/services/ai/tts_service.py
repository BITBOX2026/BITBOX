"""
TTS (Text-to-Speech) 서비스

안내 문장을 음성으로 변환해 base64 문자열로 반환합니다.
OpenAI TTS API를 사용하며, 실패해도 파이프라인을 중단하지 않습니다.
(오디오 없이 텍스트 응답만 전달하는 것이 완전 실패보다 낫기 때문입니다.)
"""

import base64

from app.core.logger import get_logger
from app.services.ai.spoken_korean import to_spoken_korean
from app.services.core.constants import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE
from app.services.core.openai_client import get_openai_client as _get_openai_client
from app.services.core.settings_helper import get_setting, is_mock_mode

logger = get_logger(__name__)


async def generate_tts_audio(text: str) -> str | None:
    """
    텍스트를 음성으로 변환하고 base64 인코딩된 WAV 문자열을 반환합니다.

    다음 경우에는 None을 반환합니다 (파이프라인 중단 없음):
    - mock 모드
    - API 키 미설정
    - TTS API 오류 (텍스트 응답은 정상 반환)
    """

    if not text or not text.strip():
        return None

    if is_mock_mode():
        return None

    if not get_setting("OPENAI_API_KEY"):
        return None

    tts_model = get_setting("TTS_MODEL", DEFAULT_TTS_MODEL)
    tts_voice = get_setting("TTS_VOICE", DEFAULT_TTS_VOICE)
    tts_speed = max(0.25, min(4.0, float(get_setting("TTS_SPEED") or 0.85)))

    try:
        client = _get_openai_client()

        response = await client.audio.speech.create(
            model=tts_model,
            voice=tts_voice,
            # 음성 업로드 경로는 서버가 오디오를 미리 만들어 내려주므로 프론트의
            # browser speech 변환을 거치지 않습니다. TTS 경계에서도 정규화해야
            # `3412`, `M6405`, `N13` 같은 노선이 모든 경로에서 같은 방식으로 들립니다.
            input=to_spoken_korean(text),
            response_format="wav",
            speed=tts_speed,
        )

        return base64.b64encode(response.content).decode("utf-8")

    except Exception as exc:  # noqa: BLE001 - TTS is optional and must never fail the text response.
        # TTS 실패는 경고만 기록하고 None 반환 — 텍스트 안내는 계속 전달됨
        logger.warning("TTS 생성 실패 (텍스트 응답은 정상 반환): error_type=%s", type(exc).__name__)
        return None
