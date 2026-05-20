# 음성 파일을 텍스트로 변환하는 STT 서비스 파일입니다.

import io

from openai import AsyncOpenAI

from app.services.constants import DEFAULT_STT_MODEL
from app.services.exceptions import STTProcessingError
from app.services.settings_helper import get_setting, is_mock_mode


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
) -> str:
    """
    음성 파일을 텍스트로 변환하는 함수입니다.

    기능:
        - 라즈베리파이에서 업로드한 음성 bytes를 OpenAI STT API로 전송합니다.
        - mock 모드에서는 실제 API를 호출하지 않고 테스트 문장을 반환합니다.

    입력:
        audio_bytes:
            - 업로드된 음성 파일의 bytes 데이터입니다.

        filename:
            - 업로드된 파일명입니다.
            - OpenAI SDK에 파일 객체로 넘길 때 사용합니다.

    반환:
        str:
            - STT 결과 텍스트입니다.

    예:
        "서울역에서 강남역 가는 버스 알려줘"
    """

    if not audio_bytes:
        raise STTProcessingError("음성 파일이 비어 있습니다.")

    if is_mock_mode():
        return "서울역에서 강남역 가는 버스 알려줘"

    api_key = get_setting("OPENAI_API_KEY")
    if not api_key:
        raise STTProcessingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    stt_model = get_setting("STT_MODEL", DEFAULT_STT_MODEL)

    try:
        client = AsyncOpenAI(api_key=api_key)

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename or "audio.wav"

        transcription = await client.audio.transcriptions.create(
            model=stt_model,
            file=audio_file,
            language="ko",
            response_format="json",
        )

        text = getattr(transcription, "text", None)

        if not text or not text.strip():
            raise STTProcessingError("STT 결과가 비어 있습니다.")

        return text.strip()

    except STTProcessingError:
        raise

    except Exception as exc:
        raise STTProcessingError(f"STT 처리 중 오류가 발생했습니다: {exc}") from exc
