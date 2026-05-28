import io
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("USE_MOCK_EXTERNALS", "true")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _wav_bytes() -> bytes:
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


def _upload(content: bytes, content_type: str = "audio/wav", headers: dict | None = None):
    return client.post(
        "/api/process",
        files={"file": ("test.wav", io.BytesIO(content), content_type)},
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Content-Type 검증
# ---------------------------------------------------------------------------

class TestContentTypeValidation:
    def test_valid_wav_accepted(self):
        with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
            "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "x",
        })):
            resp = _upload(_wav_bytes(), "audio/wav")
        assert resp.status_code == 200

    def test_wav_with_codec_param_accepted(self):
        """audio/wav; codecs=1 처럼 파라미터가 붙어도 허용합니다."""
        with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
            "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "x",
        })):
            resp = _upload(_wav_bytes(), "audio/wav; codecs=1")
        assert resp.status_code == 200

    def test_invalid_content_type_rejected(self):
        resp = _upload(_wav_bytes(), "text/plain")
        assert resp.status_code == 400

    def test_video_content_type_rejected(self):
        resp = _upload(_wav_bytes(), "video/mp4")
        assert resp.status_code == 400

    def test_invalid_wav_payload_rejected(self):
        resp = _upload(b"not really wav", "audio/wav")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 파일 크기 검증
# ---------------------------------------------------------------------------

class TestFileSizeValidation:
    def test_oversized_file_rejected(self):
        large_audio = b"X" * (11 * 1024 * 1024)  # 11 MB
        resp = _upload(large_audio, "audio/wav")
        assert resp.status_code == 413

    def test_normal_size_accepted(self):
        with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
            "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "x",
        })):
            resp = _upload(_wav_bytes(), "audio/wav")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 응답 구조
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_response_contains_status(self):
        with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
            "status": "success",
            "message": "안내 메시지",
            "data": {"transcript": "테스트"},
            "audio_base64": None,
            "request_id": "abc123",
        })):
            resp = _upload(_wav_bytes())

        body = resp.json()
        assert body["status"] == "success"
        assert body["request_id"] == "abc123"
        assert "message" in body

    def test_request_id_in_response(self):
        with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
            "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "myid",
        })):
            resp = _upload(_wav_bytes())

        assert resp.json()["request_id"] == "myid"


# ---------------------------------------------------------------------------
# API 토큰 인증
# ---------------------------------------------------------------------------

class TestApiTokenAuth:
    def test_no_token_configured_allows_request(self):
        with patch.dict(os.environ, {"API_AUTH_TOKEN": ""}):
            with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
                "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "x",
            })):
                resp = _upload(_wav_bytes())
        assert resp.status_code == 200

    def test_configured_token_rejects_missing_header(self):
        with patch.dict(os.environ, {"API_AUTH_TOKEN": "secret"}):
            resp = _upload(_wav_bytes())
        assert resp.status_code == 401

    def test_configured_token_accepts_matching_header(self):
        with patch.dict(os.environ, {"API_AUTH_TOKEN": "secret"}):
            with patch("app.api.gateway.run_pipeline", new=AsyncMock(return_value={
                "status": "success", "message": "ok", "data": {}, "audio_base64": None, "request_id": "x",
            })):
                resp = _upload(_wav_bytes(), headers={"x-bitbox-token": "secret"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 헬스체크
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "mock_mode" in body
        assert "api_keys_configured" in body

    def test_health_mock_mode_true_in_test(self):
        resp = client.get("/health")
        assert resp.json()["mock_mode"] is True
