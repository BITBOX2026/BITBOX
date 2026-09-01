"""서버 음성 합성 대체 경로 검사.

기기에 한국어 음성 엔진이 없으면 브라우저 `speechSynthesis` 는 오류 없이 무음으로
끝납니다. 교통약자용 키오스크에서 도착 안내가 들리지 않는 것은 핵심 기능 상실이라
프론트가 이 엔드포인트로 대체합니다. 비용이 무한정 늘지 않도록 캐시·길이 제한·
일일 한도를 함께 확인합니다.
"""

import asyncio
import contextlib

import httpx
import pytest

import app.main as main_module
from app.core import auth
from app.routers import speech as speech_module
from app.services.core.service_types import ParsedIntent, RouteSegment, TransportResult
from app.services.response_builder import build_user_message


@pytest.fixture(autouse=True)
def _clean_cache():
    speech_module.reset_speech_cache()
    yield
    speech_module.reset_speech_cache()


async def _post(payload: dict, headers: dict | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/speech", json=payload, headers=headers or {})


def test_repeated_announcements_reuse_the_cached_audio(monkeypatch) -> None:
    """도착 알림은 같은 문장이 반복되므로 매번 유료 호출을 하면 안 됩니다."""
    calls = {"count": 0}

    async def fake_tts(_text: str) -> str:
        calls["count"] += 1
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)

    first = asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))
    second = asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))

    assert first.status_code == 200
    assert first.json() == {"audio_base64": "QUJD", "cached": False}
    assert second.json() == {"audio_base64": "QUJD", "cached": True}
    assert calls["count"] == 1, "같은 문장에 유료 TTS 를 두 번 호출했습니다"


def test_concurrent_identical_announcements_share_one_paid_call(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_tts(_text: str) -> str:
        calls["count"] += 1
        await asyncio.sleep(0.02)
        return "QUJD"

    async def run_requests() -> list[httpx.Response]:
        monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)
        return await asyncio.gather(*[
            _post({"text": "3412번 버스가 곧 도착합니다."}) for _ in range(5)
        ])

    responses = asyncio.run(run_requests())
    assert all(response.status_code == 200 for response in responses)
    assert calls["count"] == 1


def test_a_different_sentence_is_synthesized_separately(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_tts(text: str) -> str:
        calls.append(text)
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)
    asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))
    asyncio.run(_post({"text": "3423번 버스가 한 정거장 전입니다."}))
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"text": ""}, 422),
        ({"text": "가" * (speech_module.MAX_SPEECH_CHARS + 1)}, 422),
        ({}, 422),
    ],
)
def test_rejects_input_that_is_not_a_short_guidance_sentence(payload, expected_status) -> None:
    assert asyncio.run(_post(payload)).status_code == expected_status


def test_accepts_the_longest_allowed_sentence(monkeypatch) -> None:
    async def fake_tts(_text: str) -> str:
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)
    response = asyncio.run(_post({"text": "가" * speech_module.MAX_SPEECH_CHARS}))
    assert response.status_code == 200


def test_reports_silence_instead_of_failing_when_tts_is_unavailable(monkeypatch) -> None:
    """TTS 를 쓸 수 없어도 화면 안내는 계속되어야 하므로 오류가 아닌 무음으로 답합니다."""

    async def no_audio(_text: str) -> None:
        return None

    monkeypatch.setattr(speech_module, "generate_tts_audio", no_audio)
    response = asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))
    assert response.status_code == 200
    assert response.json()["audio_base64"] is None


def test_production_reports_server_speech_failure(monkeypatch) -> None:
    async def no_audio(_text: str) -> None:
        return None

    monkeypatch.setattr(speech_module, "generate_tts_audio", no_audio)
    monkeypatch.setattr(speech_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(speech_module.settings, "USE_MOCK_EXTERNALS", False)

    response = asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_requires_the_proxy_token_when_one_is_configured(monkeypatch) -> None:
    """공개 인터넷에서 유료 합성을 임의로 호출하지 못하게 합니다."""
    monkeypatch.setattr(auth, "get_setting", lambda name, default=None: "configured-token" if name == "API_AUTH_TOKEN" else default)

    denied = asyncio.run(_post({"text": "안녕하세요"}))
    assert denied.status_code == 401

    async def fake_tts(_text: str) -> str:
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)
    allowed = asyncio.run(_post({"text": "안녕하세요"}, headers={"X-BITBOX-Token": "configured-token"}))
    assert allowed.status_code == 200


def test_slow_synthesis_gives_up_instead_of_holding_the_kiosk(monkeypatch) -> None:
    """느린 합성이 무한정 매달리면 안 됩니다.

    OpenAI 클라이언트 기본 읽기 타임아웃은 600초입니다. 상한이 없으면 그동안
    동시 실행 슬롯을 붙잡아 키오스크의 음성 안내가 통째로 멈추고, 화면은 소리도
    대체 버튼도 없이 "재생 중"에 갇힙니다.
    """

    async def never_returns(_text: str) -> str:
        await asyncio.sleep(60)
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", never_returns)
    monkeypatch.setattr(speech_module.settings, "TTS_TIMEOUT_SECONDS", 0.05)

    response = asyncio.run(_post({"text": "3412번 버스가 곧 도착합니다."}))

    assert response.status_code == 200
    assert response.json()["audio_base64"] is None


def test_a_cancelled_request_does_not_block_later_synthesis(monkeypatch) -> None:
    """먼저 기다리던 요청이 끊겨도 다음 요청이 새로 합성할 수 있어야 합니다."""
    calls = {"count": 0}

    async def slow_tts(_text: str) -> str:
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return "QUJD"

    async def run() -> httpx.Response:
        monkeypatch.setattr(speech_module, "generate_tts_audio", slow_tts)
        text = "3412번 버스가 곧 도착합니다."
        first = asyncio.ensure_future(_post({"text": text}))
        await asyncio.sleep(0.01)
        first.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first
        # 진행 중이던 작업이 끝나 정리될 때까지 기다립니다.
        await asyncio.sleep(0.15)
        assert not speech_module._inflight, "완료된 합성 작업이 정리되지 않았습니다"
        return await _post({"text": text})

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.json()["audio_base64"] == "QUJD"


def test_failed_shared_synthesis_is_observed_after_all_waiters_cancel(monkeypatch) -> None:
    """연결이 먼저 끊긴 공유 task의 예외도 완료 콜백이 관측하고 정리합니다."""
    started = asyncio.Event()
    release = asyncio.Event()
    logged: list[str] = []

    async def failing_tts(_text: str) -> str:
        started.set()
        await release.wait()
        raise RuntimeError("synthetic TTS failure")

    async def run() -> None:
        monkeypatch.setattr(speech_module, "generate_tts_audio", failing_tts)
        monkeypatch.setattr(
            speech_module.logger,
            "error",
            lambda message, *args, **kwargs: logged.append(str(message)),
        )
        waiter = asyncio.create_task(speech_module._get_or_generate_speech("실패 안내"))
        await started.wait()
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())

    assert not speech_module._inflight
    assert logged == ["공유 서버 음성 합성 작업 실패"]


def test_real_route_guidance_fits_the_length_limit_once_split() -> None:
    """실제 안내 문장이 서버 한도를 넘는지 확인합니다.

    환승이 두 번 있는 경로 안내는 200자를 넘습니다. 프론트가 문장 단위로 끊어
    보내지 않으면 422 로 거절당하고, 기기에 한국어 음성이 없는 키오스크에서는
    경로가 복잡할수록 안내가 통째로 무음이 됩니다.
    프론트의 분할 규칙은 frontend/src/utils/speechChunking.test.ts 가 지킵니다.
    """
    segments = []
    for index in range(3):
        segments.append(RouteSegment(
            vehicle_type="도보", line="도보 200m",
            start_name=f"정류장{index}", end_name=f"한국체육대학교입구{index}", time_min=4,
        ))
        segments.append(RouteSegment(
            vehicle_type="버스", line=f"{3412 + index}번",
            start_name=f"한국체육대학교입구{index}",
            end_name=f"잠실종합운동장사거리{index}", time_min=15,
        ))

    message = build_user_message(
        parsed=ParsedIntent(intent="route", destination_text="강남역", transport_mode="bus"),
        transport_result=TransportResult(
            origin="올림픽공원역", destination="강남역 2번 출구", transport_mode="bus",
            bus_number="3412", total_time_min=60, payment=2500,
            route_segments=segments, source="odsay",
        ),
    )

    assert len(message) > speech_module.MAX_SPEECH_CHARS, (
        "안내 문장이 짧아졌다면 이 회귀 방지 테스트를 실제 상한에 맞게 갱신하세요"
    )
    # 한 문장씩 나누면 모든 조각이 상한 안에 들어와야 합니다.
    for sentence in message.split(". "):
        assert len(sentence) + 1 <= speech_module.MAX_SPEECH_CHARS


def test_cache_does_not_grow_without_bound(monkeypatch) -> None:
    async def fake_tts(_text: str) -> str:
        return "QUJD"

    monkeypatch.setattr(speech_module, "generate_tts_audio", fake_tts)
    for index in range(speech_module._CACHE_MAX_ENTRIES + 10):
        asyncio.run(_post({"text": f"{index}번 버스가 곧 도착합니다."}))
    assert len(speech_module._cache) <= speech_module._CACHE_MAX_ENTRIES
