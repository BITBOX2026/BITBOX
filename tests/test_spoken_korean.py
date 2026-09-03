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


def test_hyphen_is_read_as_the_seoul_terminal_says_it() -> None:
    """서울시가 안내단말기 음성에서 `-` 를 "다시"에서 "대시"로 고쳤습니다.

    정류장에서 들리는 소리와 이 서비스가 다르면, 이용자는 같은 노선을 다른
    번호로 듣습니다. 근거: 서울시 「버스정보 안내 단말기 개선」
    news.seoul.go.kr/traffic/archives/514398
    """
    assert to_spoken_korean("30-5하남번 버스") == "삼공 대시 오 하남 번 버스"
    assert to_spoken_korean("9401-1번 버스") == "구사공일 대시 일 번 버스"


def test_short_route_in_the_use_phrasing_is_spelled_out() -> None:
    """안내 문구의 "…에서 5번을 이용하시면" 형태도 노선으로 읽어야 합니다."""
    assert (
        to_spoken_korean("올림픽공원역에서 10번을 이용하시면 됩니다.")
        == "올림픽공원역에서 일공 번을 이용하시면 됩니다."
    )
    # 같은 "이용" 이라도 출구는 시설 번호이므로 건드리지 않습니다.
    assert (
        to_spoken_korean("강남역 12번 출구를 이용하시면 됩니다.")
        == "강남역 12번 출구를 이용하시면 됩니다."
    )


def test_browser_and_server_read_a_whole_route_sentence_the_same_way() -> None:
    """프론트(spokenKorean.ts)와 이 모듈이 같은 문장을 같게 읽어야 합니다.

    브라우저가 한국어를 말할 수 있으면 프론트가, 없으면 서버 TTS 가 읽습니다.
    두 경로의 규칙이 갈라지면 기기에 따라 같은 노선이 다르게 들립니다.
    """
    sentence = (
        "서울역버스환승센터(6번승강장)에서 708번 버스를 타고 "
        "경복궁역1번출구에 내리세요. 약 17분 소요되며, 요금은 1,500원입니다."
    )
    assert to_spoken_korean(sentence) == (
        "서울역버스환승센터(6번승강장)에서 칠공팔 번 버스를 타고 "
        "경복궁역1번출구에 내리세요. 약 17분 소요되며, 요금은 1,500원입니다."
    )
