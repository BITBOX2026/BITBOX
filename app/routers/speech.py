"""Server-side speech synthesis for devices whose browser cannot speak Korean.

키오스크 기기(라즈베리파이 등)의 Chromium 은 음성 엔진이 설치돼 있지 않으면
`speechSynthesis.speak()` 가 아무 소리도 내지 않고 조용히 끝납니다. 오류도 나지
않아 화면상으로는 정상으로 보입니다. 교통약자용 기기에서 도착 알림이 무음이면
핵심 기능이 사라지는 것이므로, 브라우저가 한국어를 말할 수 없을 때 프론트가 이
엔드포인트로 대체합니다.

비용 관리:
- 짧은 안내 문구만 허용합니다(길이 상한).
- 같은 문구가 반복되므로("3412번 버스가 곧 도착합니다") 결과를 메모리에
  캐시합니다. 실제 운영에서 도착 알림은 소수의 문장이 반복되기 때문에 캐시
  적중률이 높습니다.
- 일일 한도와 동시 실행 한도는 다른 유료 경로와 동일하게 usage_slot 이 지킵니다.
"""

from collections import OrderedDict
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth import verify_api_token
from app.core.config import settings
from app.core.logger import get_logger
from app.core.rate_limiter import limiter
from app.core.usage_guard import usage_slot
from app.services.ai.tts_service import generate_tts_audio

router = APIRouter()
logger = get_logger(__name__)

MAX_SPEECH_CHARS = 200
_CACHE_MAX_ENTRIES = 64

_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = Lock()


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_SPEECH_CHARS)


class SpeechResponse(BaseModel):
    audio_base64: str | None = None
    cached: bool = False


def _cache_get(text: str) -> str | None:
    with _cache_lock:
        audio = _cache.get(text)
        if audio is not None:
            _cache.move_to_end(text)
        return audio


def _cache_put(text: str, audio: str) -> None:
    with _cache_lock:
        _cache[text] = audio
        _cache.move_to_end(text)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def reset_speech_cache() -> None:
    """테스트에서 캐시 상태를 초기화합니다."""
    with _cache_lock:
        _cache.clear()


@router.post("", response_model=SpeechResponse)
@limiter.limit("30/minute")
async def synthesize_speech(request: Request, body: SpeechRequest) -> SpeechResponse:
    """Return spoken audio for a short guidance sentence.

    브라우저가 한국어를 말할 수 있으면 프론트가 이 엔드포인트를 부르지 않습니다.
    따라서 정상적인 데스크톱/모바일 이용에서는 추가 비용이 발생하지 않습니다.
    """
    verify_api_token(request)

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="읽을 문장이 비어 있습니다.")

    cached = _cache_get(text)
    if cached is not None:
        return SpeechResponse(audio_base64=cached, cached=True)

    async with usage_slot(
        "speech",
        max_concurrent=settings.VOICE_MAX_CONCURRENT_REQUESTS,
        daily_limit=settings.SPEECH_DAILY_REQUEST_LIMIT,
    ):
        audio = await generate_tts_audio(text)

    if not audio:
        # TTS 를 쓸 수 없는 환경(mock/키 미설정/제공자 오류)입니다. 프론트는 화면
        # 안내로만 진행하면 되므로 실패가 아니라 "소리 없음"으로 알립니다.
        logger.info("서버 음성 합성 결과 없음 — 화면 안내만 제공됩니다.")
        return SpeechResponse(audio_base64=None)

    _cache_put(text, audio)
    return SpeechResponse(audio_base64=audio)
