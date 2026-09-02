"""음성 파이프라인의 단계별 시간 예산을 고정합니다.

전체 30초 봉투(REQUEST_TIMEOUT_SECONDS)는 원래부터 지켜지고 있었습니다. 문제는
그 안쪽에 단계별 상한이 없어서 생기는 두 가지였습니다.

1. 느리기만 한(실패도 아닌) STT·LLM 호출 하나가 봉투를 다 써 버리면, 이용자는
   무엇이 잘못됐는지 알 수 없는 일반 타임아웃(504)만 받습니다.
2. 앞 단계가 예산을 거의 다 쓴 뒤 TTS가 시작되면, 봉투가 TTS 도중에 터집니다.
   그때 발생하는 CancelledError 는 BaseException 이라 TTS 의 방어 코드가 잡지
   못하고, 이미 완성해 둔 텍스트 안내까지 함께 버려집니다.
"""

import asyncio

import pytest

from app.core.config import settings, validate_required_settings
from app.services import pipeline
from app.services.core.exceptions import LLMParsingError, STTProcessingError


@pytest.fixture(autouse=True)
def never_call_the_paid_tts(monkeypatch):
    """이 파일의 어떤 테스트도 실제 OpenAI TTS 를 호출하지 않게 막습니다.

    저장소에는 전역 conftest 가 없습니다. 실제 키가 담긴 .env 가 있는 개발 PC에서
    run_pipeline 을 그대로 호출하면 유료 TTS 가 실제로 나갑니다. CI 러너는 키가
    없어 조용히 None 을 반환하므로, 이 실수는 로컬에서만 드러납니다.
    """

    async def offline_tts(_text: str) -> None:
        return None

    monkeypatch.setattr(pipeline, "generate_tts_audio", offline_tts)


def test_stt_and_llm_budgets_fit_inside_the_pipeline_envelope() -> None:
    """두 OpenAI 단계만으로 전체 예산을 소진하면 안 됩니다."""
    assert (
        settings.STT_TIMEOUT_SECONDS + settings.LLM_TIMEOUT_SECONDS
        < settings.REQUEST_TIMEOUT_SECONDS
    )


def test_llm_retry_can_actually_finish_inside_its_stage_budget() -> None:
    """재시도가 시작만 하고 잘리면 재시도 로직은 아무 일도 하지 못합니다."""
    assert (
        settings.LLM_ATTEMPT_TIMEOUT_SECONDS * 2 + settings.LLM_RETRY_WAIT_SECONDS
        <= settings.LLM_TIMEOUT_SECONDS
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("STT_TIMEOUT_SECONDS", 25.0),          # 25 + 10 >= 30
        ("LLM_ATTEMPT_TIMEOUT_SECONDS", 9.0),   # 9*2 + 0.5 > 10
        ("STT_TIMEOUT_SECONDS", 0.0),
        ("LLM_TIMEOUT_SECONDS", -1.0),
    ],
)
def test_startup_rejects_a_budget_that_cannot_hold(monkeypatch, name: str, value: float) -> None:
    """설정만으로 예산이 깨질 수 있으므로 기동 시점에 막습니다."""
    monkeypatch.setattr(settings, name, value)
    with pytest.raises(RuntimeError):
        validate_required_settings()


@pytest.mark.parametrize("mock_mode", [True, False])
def test_budget_validation_is_not_skipped_by_mock_mode(monkeypatch, mock_mode: bool) -> None:
    """mock 모드에서도 시간 예산 검증이 살아 있어야 합니다.

    ``USE_MOCK_EXTERNALS`` 는 기본값이 ``True`` 입니다. 그래서 이 검증이 mock
    게이트 뒤에 있으면 ``.env`` 가 없는 CI 러너에서는 한 번도 실행되지 않습니다.
    실제로 그 상태에서는 로컬만 통과하고 CI 는 실패했습니다. 상한과 시간 예산은
    외부 키가 아니라 서비스 내부 동작을 규정하므로 실행 모드와 무관해야 합니다.
    """
    monkeypatch.setattr(settings, "USE_MOCK_EXTERNALS", mock_mode)
    monkeypatch.setattr(settings, "STT_TIMEOUT_SECONDS", 25.0)

    with pytest.raises(RuntimeError, match="REQUEST_TIMEOUT_SECONDS보다 작아야"):
        validate_required_settings()


def test_a_slow_stt_reports_a_speech_error_not_a_generic_timeout(monkeypatch) -> None:
    """느린 STT 는 단계 오류로 끝나야 파이프라인이 원인을 설명할 수 있습니다."""
    monkeypatch.setattr(settings, "STT_TIMEOUT_SECONDS", 0.05)

    async def never_finishes(**_kwargs) -> str:
        await asyncio.sleep(30)
        raise AssertionError("STT should have been cut by the stage budget")

    monkeypatch.setattr(pipeline, "transcribe_audio", never_finishes)

    result = asyncio.run(pipeline.run_pipeline(b"audio", "audio.wav", "req-stt"))

    assert result["status"] == "error"
    assert result["message"] == STTProcessingError.user_message
    # 일반 타임아웃 응답으로 뭉개지면 안 됩니다.
    assert result.get("error_kind") != "timeout"


def test_a_slow_llm_reports_an_analysis_error_not_a_generic_timeout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_TIMEOUT_SECONDS", 0.05)

    async def transcribe(**_kwargs) -> str:
        return "잠실역 가는 버스 알려줘"

    async def never_finishes(*_args, **_kwargs):
        await asyncio.sleep(30)
        raise AssertionError("LLM should have been cut by the stage budget")

    monkeypatch.setattr(pipeline, "transcribe_audio", transcribe)
    monkeypatch.setattr(pipeline, "parse_transit_intent", never_finishes)

    result = asyncio.run(pipeline.run_pipeline(b"audio", "audio.wav", "req-llm"))

    assert result["status"] == "error"
    assert result["message"] == LLMParsingError.user_message
    assert result.get("error_kind") != "timeout"


def test_tts_is_skipped_when_the_envelope_has_no_time_left(monkeypatch) -> None:
    """남은 시간이 없으면 오디오를 포기하고 텍스트 안내를 지켜야 합니다."""
    called = False

    async def should_not_run(_text: str) -> str:
        nonlocal called
        called = True
        return "audio"

    monkeypatch.setattr(pipeline, "generate_tts_audio", should_not_run)

    audio = asyncio.run(
        pipeline._generate_tts_audio_safely("안내 문장", "req-tts", budget_seconds=0.0)
    )

    assert audio is None
    assert called is False, "예산이 없는데 유료 TTS 호출을 시작하면 안 됩니다"


def test_tts_budget_shrinks_as_earlier_stages_spend_the_envelope(monkeypatch) -> None:
    """TTS 상한은 고정값이 아니라 '봉투에 남은 시간'이어야 합니다."""
    monkeypatch.setattr(settings, "REQUEST_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(settings, "TTS_TIMEOUT_SECONDS", 15)

    import time

    now = time.monotonic()
    # 앞 단계가 아직 아무 것도 쓰지 않았으면 TTS 자체 상한이 그대로 적용됩니다.
    assert pipeline._remaining_tts_budget(now) == pytest.approx(15.0, abs=0.5)
    # 25초를 이미 썼다면 남은 시간은 15초가 아니라 4초 남짓뿐입니다.
    assert pipeline._remaining_tts_budget(now - 25) == pytest.approx(4.0, abs=0.5)
    # 봉투를 다 썼다면 0 이하가 되어 TTS 를 건너뜁니다.
    assert pipeline._remaining_tts_budget(now - 30) <= 0
