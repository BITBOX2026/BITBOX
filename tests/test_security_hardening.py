"""Regression tests for security-sensitive input and deployment boundaries."""

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.gateway import _safe_audio_filename
from app.core import config, usage_guard
from app.main import internal_status
from app.services.core import http_utils
from app.services.core.exceptions import TransportAPIError
from app.services.transit.seoul_bus_client import _parse_response_payload
from scripts.load_smoke import validate_url


def test_client_filename_is_never_forwarded_to_stt() -> None:
    assert _safe_audio_filename("audio/webm") == "recording.webm"
    assert _safe_audio_filename("audio/mpeg") == "recording.mp3"
    assert _safe_audio_filename("../../secret.txt") == "recording.bin"


def test_external_xml_rejects_entity_expansion() -> None:
    response = httpx.Response(
        200,
        text='<!DOCTYPE x [<!ENTITY attack "expanded">]><root>&attack;</root>',
    )

    with pytest.raises(TransportAPIError):
        _parse_response_payload(response, "security-test")


def test_external_payload_size_is_bounded() -> None:
    response = httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))

    with pytest.raises(TransportAPIError, match="크기 초과"):
        _parse_response_payload(response, "security-test")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/a", "javascript:alert(1)"]
)
def test_load_smoke_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


def test_nginx_blocks_cross_site_api_and_unknown_hosts() -> None:
    config = Path("deploy/nginx-bitbox.conf.example").read_text(encoding="utf-8")
    assert "map $http_sec_fetch_site $bitbox_cross_site" in config
    assert "if ($bitbox_cross_site) { return 403; }" in config
    assert "if ($host != ${BITBOX_SERVER_NAME}) { return 444; }" in config
    assert "Content-Security-Policy" in config
    assert "location ^~ /internal/" in config


def test_paid_usage_guard_enforces_concurrency_and_daily_limits() -> None:
    name = f"test-{uuid4().hex}"

    async def scenario() -> None:
        async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=2):
            with pytest.raises(HTTPException) as concurrent_error:
                async with usage_guard.usage_slot(
                    name, max_concurrent=1, daily_limit=2
                ):
                    pass
            assert concurrent_error.value.status_code == 429

        async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=2):
            pass

        with pytest.raises(HTTPException) as daily_error:
            async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=2):
                pass
        assert daily_error.value.status_code == 429

    asyncio.run(scenario())


def test_paid_usage_guard_survives_process_state_reset(monkeypatch, tmp_path) -> None:
    name = f"persistent-{uuid4().hex}"
    monkeypatch.setattr(usage_guard.settings, "USAGE_DB_PATH", str(tmp_path / "usage.db"))

    async def use_once() -> None:
        async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=2):
            pass

    asyncio.run(use_once())
    asyncio.run(use_once())
    usage_guard._states.pop(name, None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(use_once())
    assert exc_info.value.status_code == 429
    assert usage_guard.usage_snapshot()[name]["used"] == 2


def test_paid_usage_guard_fails_closed_when_storage_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    name = f"unavailable-{uuid4().hex}"
    monkeypatch.setattr(usage_guard.settings, "USAGE_DB_PATH", str(tmp_path))

    async def scenario() -> None:
        async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=2):
            pass

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(scenario())
    assert exc_info.value.status_code == 503


def test_healthcheck_does_not_restart_for_external_readiness_failure() -> None:
    script = Path("deploy/bitbox-healthcheck.sh").read_text(encoding="utf-8")
    health_branch, readiness_branch = script.split(
        "if curl --fail --silent --show-error --max-time 5 "
        "http://127.0.0.1:8001/ready",
        maxsplit=1,
    )
    assert "systemctl restart bitbox-backend.service" in health_branch
    assert "systemctl restart bitbox-backend.service" not in readiness_branch
    assert "backend remains live and was not restarted" in readiness_branch


def test_healthcheck_supports_discord_and_logs_delivery_failure() -> None:
    script = Path("deploy/bitbox-healthcheck.sh").read_text(encoding="utf-8")
    assert "discord.com/api/webhooks/" in script
    assert "{\\\"content\\\"" in script
    assert "alert delivery failed" in script
    assert '"--test-alert"' in script
    assert "test alert delivered" in script
    assert "BITBOX_MONITORING_ENV_FILE" in script


def test_external_production_monitor_is_scheduled() -> None:
    workflow = Path(".github/workflows/production-monitor.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "*/15 * * * *"' in workflow
    assert "scripts/production_smoke.py" in workflow


def test_production_requires_a_full_release_sha(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "APP_ENV", "prod")
    monkeypatch.setattr(config.settings, "USE_MOCK_EXTERNALS", True)
    monkeypatch.setattr(config.settings, "API_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(config.settings, "CORS_ALLOWED_ORIGINS", "")
    monkeypatch.setattr(config.settings, "RELEASE_SHA", None)

    with pytest.raises(RuntimeError, match="RELEASE_SHA"):
        config.validate_required_settings()

    monkeypatch.setattr(config.settings, "RELEASE_SHA", "d" * 40)
    config.validate_required_settings()


def test_external_circuit_opens_after_final_retry(monkeypatch) -> None:
    calls = 0
    monkeypatch.setattr(http_utils.settings, "EXTERNAL_CIRCUIT_FAILURE_THRESHOLD", 1)
    monkeypatch.setattr(http_utils.settings, "EXTERNAL_CIRCUIT_RESET_SECONDS", 60)
    http_utils._circuits.clear()

    @http_utils.http_retry
    async def unavailable() -> None:
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://provider.example")
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(httpx.ConnectError):
        asyncio.run(unavailable())
    assert calls == 3

    with pytest.raises(httpx.ConnectError, match="circuit is open"):
        asyncio.run(unavailable())
    assert calls == 3


def test_internal_status_rejects_non_local_clients() -> None:
    request = Request({"type": "http", "headers": [], "client": ("203.0.113.10", 1234)})
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(internal_status(request))
    assert exc_info.value.status_code == 404
