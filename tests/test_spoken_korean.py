from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.ai import tts_service
from app.services.ai.spoken_korean import spell_bus_number, to_spoken_korean


def test_numeric_and_lettered_bus_numbers_are_spoken_digit_by_digit() -> None:
    assert to_spoken_korean("3412번 버스가 곧 도착합니다.") == "삼사일이 번 버스가 곧 도착합니다."
    assert to_spoken_korean("M6405번 버스를 타세요.") == "엠 육사공오 번 버스를 타세요."
    assert to_spoken_korean("N13번에서 3412번으로 갈아타세요.") == (
        "엔 일삼 번에서 삼사일이 번으로 갈아타세요."
    )
    assert spell_bus_number("1311B광주") == "일삼일일 비 광주"


def test_station_exit_and_platform_numbers_are_not_changed() -> None:
    guidance = "강남역 12번 출구에서 2번 승강장으로 이동하세요."
    assert to_spoken_korean(guidance) == guidance
    assert to_spoken_korean("강남역12번출구까지 걸어가세요.") == "강남역12번출구까지 걸어가세요."


def test_short_numeric_routes_require_bus_context() -> None:
    assert to_spoken_korean("51번 버스를 타세요.") == "오일 번 버스를 타세요."
    assert to_spoken_korean("12번 출구에서 51번으로 갈아타세요.") == (
        "12번 출구에서 오일 번으로 갈아타세요."
    )


def test_conversion_is_idempotent() -> None:
    spoken = to_spoken_korean("M6405번 버스와 3412번 버스")
    assert to_spoken_korean(spoken) == spoken


def test_pre_generated_server_audio_uses_the_same_spoken_text(monkeypatch) -> None:
    """음성 입력 응답의 audio_base64도 프론트 변환을 우회하지 않아야 합니다."""
    captured: dict[str, object] = {}

    class FakeSpeech:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=b"WAV")

    fake_client = SimpleNamespace(audio=SimpleNamespace(speech=FakeSpeech()))
    settings = {
        "OPENAI_API_KEY": "offline-test-key",
        "TTS_MODEL": "offline-model",
        "TTS_VOICE": "offline-voice",
        "TTS_SPEED": 0.85,
    }
    monkeypatch.setattr(tts_service, "is_mock_mode", lambda: False)
    monkeypatch.setattr(tts_service, "get_setting", lambda name, default=None: settings.get(name, default))
    monkeypatch.setattr(tts_service, "_get_openai_client", lambda: fake_client)

    audio = asyncio.run(tts_service.generate_tts_audio(
        "강남역 12번 출구까지 걸어간 뒤 M6405번 버스를 타세요."
    ))

    assert audio == "V0FW"
    assert captured["input"] == "강남역 12번 출구까지 걸어간 뒤 엠 육사공오 번 버스를 타세요."
    assert captured["speed"] == 0.85
