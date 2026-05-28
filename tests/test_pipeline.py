"""
파이프라인 단위 테스트

USE_MOCK_EXTERNALS=true 환경에서 외부 API 없이 전체 파이프라인을 검증합니다.
pytest.ini의 asyncio_mode=auto 설정으로 @pytest.mark.asyncio 없이 동작합니다.
"""

import os
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("USE_MOCK_EXTERNALS", "true")

from app.services.pipeline import build_timeout_error_response, run_pipeline


def _make_audio() -> bytes:
    """최소한의 WAV 헤더 바이트 (실제 오디오 불필요, mock 모드)."""
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


# ---------------------------------------------------------------------------
# run_pipeline — mock 모드 정상 동작 테스트
# ---------------------------------------------------------------------------

class TestRunPipelineMockMode:
    async def test_route_intent_returns_success(self):
        result = await run_pipeline(_make_audio(), request_id="test01")

        assert result["status"] == "success"
        assert result["request_id"] == "test01"
        assert "message" in result
        assert result["data"]["intent"] == "route"

    async def test_response_schema_complete(self):
        result = await run_pipeline(_make_audio(), request_id="test02")
        data = result["data"]

        required_keys = {
            "transcript", "intent", "origin", "destination",
            "stop_text", "stop_name", "transport_mode", "bus_number",
            "arrival_time", "total_time_min", "payment",
            "bus_transit_count", "subway_transit_count", "transfer_count",
            "path_type", "route_segments", "confidence", "source",
            "needs_confirmation",
        }
        assert required_keys.issubset(data.keys())

    async def test_audio_base64_present(self):
        with patch(
            "app.services.pipeline.generate_tts_audio",
            new=AsyncMock(return_value="base64encodedaudio"),
        ):
            result = await run_pipeline(_make_audio(), request_id="test03")

        assert result["audio_base64"] == "base64encodedaudio"

    async def test_tts_failure_does_not_crash_pipeline(self):
        with patch(
            "app.services.pipeline.generate_tts_audio",
            new=AsyncMock(return_value=None),
        ):
            result = await run_pipeline(_make_audio(), request_id="test04")

        assert result["status"] == "success"
        assert result["audio_base64"] is None

    async def test_tts_timeout_does_not_crash_pipeline(self, monkeypatch):
        async def slow_tts(_text: str) -> str:
            await asyncio.sleep(1)
            return "late-audio"

        monkeypatch.setattr("app.services.pipeline.settings.TTS_TIMEOUT_SECONDS", 0.01)

        with patch("app.services.pipeline.generate_tts_audio", slow_tts):
            result = await run_pipeline(_make_audio(), request_id="test-timeout")

        assert result["status"] == "success"
        assert result["audio_base64"] is None

    async def test_route_segments_serialized_as_dicts(self):
        result = await run_pipeline(_make_audio(), request_id="test05")
        segments = result["data"].get("route_segments")

        if segments is not None:
            assert isinstance(segments, list)
            for seg in segments:
                assert isinstance(seg, dict)
                assert "vehicle_type" in seg
                assert "line" in seg
                assert "start_name" in seg
                assert "end_name" in seg

    async def test_missing_destination_after_origin_returns_error(self):
        async def fake_transcribe_audio(*args, **kwargs) -> str:
            return "서울역에서 가는 버스 알려줘"

        with patch("app.services.pipeline.transcribe_audio", fake_transcribe_audio):
            result = await run_pipeline(_make_audio(), request_id="missing-dest")

        assert result["status"] == "error"
        assert "목적지" in result["message"]


# ---------------------------------------------------------------------------
# run_pipeline — 각 단계별 오류 처리 테스트
# ---------------------------------------------------------------------------

class TestRunPipelineErrors:
    async def test_stt_error_returns_error_response(self):
        from app.services.core.exceptions import STTProcessingError

        with patch(
            "app.services.pipeline.transcribe_audio",
            new=AsyncMock(side_effect=STTProcessingError("STT 실패")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err01")

        assert result["status"] == "error"
        # 기술적 오류 메시지가 아닌 user_message가 반환되는지 확인
        assert "음성을 인식하지 못했습니다" in result["message"]

    async def test_llm_error_returns_error_response(self):
        from app.services.core.exceptions import LLMParsingError

        with patch(
            "app.services.pipeline.parse_transit_intent",
            new=AsyncMock(side_effect=LLMParsingError("LLM 실패")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err02")

        assert result["status"] == "error"
        assert "요청 내용을 분석하지 못했습니다" in result["message"]

    async def test_transport_error_returns_error_response(self):
        from app.services.core.exceptions import TransportAPIError

        with patch(
            "app.services.pipeline.search_transport_info",
            new=AsyncMock(side_effect=TransportAPIError("내부 오류 로그용 메시지")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err03")

        assert result["status"] == "error"
        # 기술적 내부 메시지가 아닌 클래스 기본 user_message가 사용자에게 반환되는지 확인
        assert "교통 정보를 조회하지 못했습니다" in result["message"]

    async def test_unexpected_exception_returns_generic_error(self):
        with patch(
            "app.services.pipeline.transcribe_audio",
            new=AsyncMock(side_effect=RuntimeError("예상치 못한 오류")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err04")

        assert result["status"] == "error"
        assert "다시 말씀해 주세요" in result["message"]

    async def test_coordinate_error_returns_needs_confirmation(self):
        from app.services.core.exceptions import CoordinateResolveError

        with patch(
            "app.services.pipeline.search_transport_info",
            new=AsyncMock(side_effect=CoordinateResolveError("장소 없음")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err05")

        assert result["status"] == "error"
        assert result["data"]["needs_confirmation"] is True


# ---------------------------------------------------------------------------
# build_timeout_error_response — 타임아웃 응답 구조 테스트
# ---------------------------------------------------------------------------

class TestBuildTimeoutErrorResponse:
    def test_returns_error_status(self):
        result = build_timeout_error_response()
        assert result["status"] == "error"

    def test_message_contains_timeout_text(self):
        result = build_timeout_error_response()
        assert "초과" in result["message"]

    def test_audio_base64_is_none(self):
        result = build_timeout_error_response()
        assert result["audio_base64"] is None
