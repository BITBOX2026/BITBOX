"""
OpenAI 클라이언트 싱글턴

stt_service, tts_service, llm_service가 동일한 AsyncOpenAI 인스턴스를 공유합니다.
연결 풀을 하나만 유지하고, 설정 변경 시 한 곳만 수정하면 됩니다.
"""

from openai import AsyncOpenAI

from app.services.core.settings_helper import get_setting

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_setting("OPENAI_API_KEY"))
    return _client


async def close_openai_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
