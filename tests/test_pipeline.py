import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("USE_MOCK_EXTERNALS", "true")

from app.services.pipeline import build_timeout_error_response, run_pipeline


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_audio() -> bytes:
    """최소한의 WAV 헤더 바이트 (실제 오디오 불필요, mock 모드)."""
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


# ---------------------------------------------------------------------------
# run_pipeline (mock 모드)
# ---------------------------------------------------------------------------

class TestRunPipelineMockMode:
    @pytest.mark.asyncio
    async def test_route_intent_returns_success(self):
        result = await run_pipeline(_make_audio(), request_id="test01")

        assert result["status"] == "success"
        assert result["request_id"] == "test01"
        assert "message" in result
        assert result["data"]["intent"] == "route"

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_audio_base64_present(self):
        with patch(
            "app.services.pipeline.generate_tts_audio",
            new=AsyncMock(return_value="base64encodedaudio"),
        ):
            result = await run_pipeline(_make_audio(), request_id="test03")

        assert result["audio_base64"] == "base64encodedaudio"

    @pytest.mark.asyncio
    async def test_tts_failure_does_not_crash_pipeline(self):
        with patch(
            "app.services.pipeline.generate_tts_audio",
            new=AsyncMock(return_value=None),
        ):
            result = await run_pipeline(_make_audio(), request_id="test04")

        assert result["status"] == "success"
        assert result["audio_base64"] is None

    @pytest.mark.asyncio
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


# ---------------------------------------------------------------------------
# 에러 케이스
# ---------------------------------------------------------------------------

class TestRunPipelineErrors:
    @pytest.mark.asyncio
    async def test_stt_error_returns_error_response(self):
        from app.services.exceptions import STTProcessingError

        with patch(
            "app.services.pipeline.transcribe_audio",
            new=AsyncMock(side_effect=STTProcessingError("STT 실패")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err01")

        assert result["status"] == "error"
        assert "STT 실패" in result["message"]

    @pytest.mark.asyncio
    async def test_llm_error_returns_error_response(self):
        from app.services.exceptions import LLMParsingError

        with patch(
            "app.services.pipeline.parse_transit_intent",
            new=AsyncMock(side_effect=LLMParsingError("LLM 실패")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err02")

        assert result["status"] == "error"
        assert "LLM 실패" in result["message"]

    @pytest.mark.asyncio
    async def test_transport_error_returns_error_response(self):
        from app.services.exceptions import TransportAPIError

        with patch(
            "app.services.pipeline.search_transport_info",
            new=AsyncMock(side_effect=TransportAPIError("경로 없음")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err03")

        assert result["status"] == "error"
        assert "경로 없음" in result["message"]

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_generic_error(self):
        with patch(
            "app.services.pipeline.transcribe_audio",
            new=AsyncMock(side_effect=RuntimeError("예상치 못한 오류")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err04")

        assert result["status"] == "error"
        assert "다시 말씀해 주세요" in result["message"]

    @pytest.mark.asyncio
    async def test_coordinate_error_returns_needs_confirmation(self):
        from app.services.exceptions import CoordinateResolveError

        with patch(
            "app.services.pipeline.search_transport_info",
            new=AsyncMock(side_effect=CoordinateResolveError("장소 없음")),
        ):
            result = await run_pipeline(_make_audio(), request_id="err05")

        assert result["status"] == "error"
        assert result["data"]["needs_confirmation"] is True


# ---------------------------------------------------------------------------
# build_timeout_error_response
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
