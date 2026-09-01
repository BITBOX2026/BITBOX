"""Regression tests for security-sensitive input and deployment boundaries."""

import asyncio
import traceback
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.main as main_module
import app.routers.place as place_router_module
from app.api.gateway import _safe_audio_filename
from app.core import config, usage_guard
from app.main import internal_status
from app.services.core import http_utils, openai_client
from app.services.core.exceptions import ProviderUsageError, TransportAPIError
from app.services.transit import odsay_service, seoul_bus_client, transport_service
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


def test_daily_usage_uses_korean_calendar_and_exact_retry_after(monkeypatch) -> None:
    fixed = datetime(2026, 9, 2, 23, 59, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    monkeypatch.setattr(usage_guard, "_service_now", lambda: fixed)
    name = f"kst-{uuid4().hex}"

    async def use_once() -> None:
        async with usage_guard.usage_slot(name, max_concurrent=1, daily_limit=1):
            pass

    asyncio.run(use_once())
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(use_once())
    assert usage_guard.usage_snapshot()[name]["day"] == "2026-09-02"
    assert exc_info.value.headers == {"Retry-After": "30"}


def test_route_concurrency_does_not_consume_a_paid_daily_call() -> None:
    name = f"route-concurrency-{uuid4().hex}"

    async def use_once() -> None:
        async with usage_guard.concurrency_slot(name, max_concurrent=1):
            pass

    asyncio.run(use_once())
    assert usage_guard.usage_snapshot()[name]["used"] == 0


def test_odsay_counts_every_real_http_attempt_and_stops_before_limit(monkeypatch) -> None:
    class FailingClient:
        calls = 0

        async def get(self, url: str, **_kwargs) -> httpx.Response:
            self.calls += 1
            request = httpx.Request("GET", f"{url}?apiKey=must-not-leak")
            return httpx.Response(500, request=request)

    client = FailingClient()
    monkeypatch.setattr(odsay_service, "get_http_client", lambda: client)
    monkeypatch.setattr(odsay_service.settings, "USAGE_DB_PATH", None)
    monkeypatch.setattr(odsay_service.settings, "ODSAY_DAILY_CALL_LIMIT", 2)
    usage_guard._states.pop("odsay", None)
    http_utils._circuits.clear()
    circuit_key = "app.services.transit.odsay_service._odsay_fetch"

    try:
        # 실패한 호출도 ODsay 쪽에서는 소비된 요청이므로 그대로 차감합니다.
        for expected_used in (1, 2):
            with pytest.raises(httpx.HTTPStatusError):
                asyncio.run(odsay_service._odsay_fetch({"apiKey": "must-not-leak"}))
            assert client.calls == expected_used
            assert usage_guard.usage_snapshot()["odsay"]["used"] == expected_used

        failures_before = http_utils.circuit_snapshot().get(circuit_key, {}).get("failures", 0)

        # 한도에 닿으면 HTTP 를 시작하기 전에 막습니다.
        with pytest.raises(ProviderUsageError) as exc_info:
            asyncio.run(odsay_service._odsay_fetch({"apiKey": "must-not-leak"}))

        assert exc_info.value.http_status == 429
        assert client.calls == 2, "한도 초과 요청이 제공자까지 나가면 안 됩니다"
        assert usage_guard.usage_snapshot()["odsay"]["used"] == 2
        # 로컬 한도 거절은 제공자 장애가 아니므로 회로 실패로 세면 안 됩니다.
        failures_after = http_utils.circuit_snapshot().get(circuit_key, {}).get("failures", 0)
        assert failures_after == failures_before
    finally:
        usage_guard._states.pop("odsay", None)
        http_utils._circuits.clear()


@pytest.mark.parametrize(
    "make_failure",
    [
        lambda: httpx.Response(500, request=httpx.Request("GET", "https://odsay.example/p")),
        lambda: httpx.ConnectError("boom", request=httpx.Request("GET", "https://odsay.example/p")),
    ],
    ids=["http_500", "connect_error"],
)
def test_one_route_request_never_costs_more_than_one_odsay_call(monkeypatch, make_failure) -> None:
    """ODsay 는 하루 30회뿐이라 순단 한 번이 쿼터 3회를 쓰면 안 됩니다.

    5xx 든 연결 오류든, 요청 하나는 정확히 한 번만 제공자에 나가야 합니다.
    """
    failure = make_failure()

    class Client:
        calls = 0

        async def get(self, _url: str, **_kwargs):
            self.calls += 1
            if isinstance(failure, Exception):
                raise failure
            return failure

    client = Client()
    monkeypatch.setattr(odsay_service, "get_http_client", lambda: client)
    monkeypatch.setattr(odsay_service.settings, "USAGE_DB_PATH", None)
    monkeypatch.setattr(odsay_service.settings, "ODSAY_DAILY_CALL_LIMIT", 30)
    usage_guard._states.pop("odsay", None)
    http_utils._circuits.clear()

    try:
        with pytest.raises((httpx.HTTPStatusError, httpx.ConnectError)):
            asyncio.run(odsay_service._odsay_fetch({"apiKey": "must-not-leak"}))
        assert client.calls == 1, f"{type(failure).__name__} 에서 재시도가 발생했습니다"
        assert usage_guard.usage_snapshot()["odsay"]["used"] == 1
    finally:
        usage_guard._states.pop("odsay", None)
        http_utils._circuits.clear()


def test_providers_with_room_still_retry(monkeypatch) -> None:
    """쿼터가 넉넉한 Kakao·공공데이터까지 재시도를 잃으면 안 됩니다."""
    from app.services.core import http_utils as utils

    assert utils.DEFAULT_HTTP_ATTEMPTS == 3

    attempts = 0

    @utils.http_retry
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://x.example"))
        return "ok"

    try:
        assert asyncio.run(flaky()) == "ok"
        assert attempts == 3
    finally:
        http_utils._circuits.clear()


def test_odsay_route_cache_hit_consumes_no_provider_call(monkeypatch) -> None:
    parsed = transport_service.ParsedIntent(
        intent="route",
        origin_text="출발지",
        destination_text="목적지",
        destination_x=127.1,
        destination_y=37.5,
        transport_mode="bus",
        confidence=1.0,
    )
    key = transport_service._make_cache_key(
        "출발지", "목적지", "bus", 127.1, 37.5
    )
    cached = transport_service.TransportResult(source="odsay")
    transport_service._route_cache[key] = (cached, transport_service.time.monotonic())
    usage_guard._states.pop("odsay", None)

    async def must_not_call(**_kwargs):
        raise AssertionError("ODsay must not be called for a cache hit")

    monkeypatch.setattr(transport_service, "search_odsay_route", must_not_call)
    try:
        assert asyncio.run(transport_service._search_route_with_odsay(parsed)) is cached
        assert "odsay" not in usage_guard.usage_snapshot()
    finally:
        transport_service._evict_cache_entry(key)


@pytest.mark.parametrize("provider", ["odsay", "seoul"])
def test_provider_http_errors_never_chain_secret_query_urls(monkeypatch, provider: str) -> None:
    secret = "SECRET_KEY_AAAA1111BBBB2222"
    request = httpx.Request("GET", f"https://provider.example/path?apiKey={secret}")
    response = httpx.Response(500, request=request)
    raw_error = httpx.HTTPStatusError("provider failed", request=request, response=response)

    if provider == "odsay":
        async def fail_odsay(_params: dict) -> dict:
            raise raw_error

        monkeypatch.setattr(odsay_service, "_odsay_fetch", fail_odsay)
        monkeypatch.setattr(odsay_service, "get_setting", lambda *_args: "configured")
        operation = odsay_service.search_odsay_route(
            "출발지", 127.0, 37.5, "목적지", 127.1, 37.6, "bus"
        )
    else:
        async def fail_seoul(_url: str, _params: dict[str, str]) -> httpx.Response:
            raise raw_error

        monkeypatch.setattr(seoul_bus_client, "_seoul_bus_get", fail_seoul)
        monkeypatch.setattr(
            seoul_bus_client, "_get_first_service_key", lambda _names: secret
        )
        operation = seoul_bus_client.request_seoul_bus_payload(
            "https://provider.example/path", {}, "보안 테스트"
        )

    with pytest.raises(TransportAPIError) as exc_info:
        asyncio.run(operation)
    rendered = "".join(
        traceback.format_exception(
            type(exc_info.value), exc_info.value, exc_info.value.__traceback__
        )
    )
    assert secret not in rendered
    assert "apiKey=" not in rendered


def test_openai_client_disables_hidden_sdk_retries_and_sets_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(openai_client, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_client.settings, "OPENAI_TIMEOUT_SECONDS", 20.0)
    monkeypatch.setattr(openai_client.settings, "OPENAI_MAX_RETRIES", 0)
    openai_client._client = None
    try:
        assert isinstance(openai_client.get_openai_client(), FakeOpenAI)
        assert captured["timeout"] == 20.0
        assert captured["max_retries"] == 0
    finally:
        openai_client._client = None


def test_place_query_length_is_bounded_before_the_provider_is_called(monkeypatch) -> None:
    """긴 검색어는 Kakao에 전달되기 전에 거절되어야 합니다.

    Kakao Local 키워드 검색은 100자를 넘으면 400을 돌려줍니다. 그 실패가 공용 회로
    차단기에 쌓이면 다섯 번의 요청만으로 회로가 열려 정상 이용자의 장소 검색과
    /ready 가 함께 멈춥니다. 경계는 provider 앞에서 지켜야 합니다.
    """
    calls: list[str] = []

    async def spy_search(query: str, **_kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(place_router_module, "search_place_suggestions", spy_search)

    async def suggest(query: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/places/suggest", params={"query": query})

    too_long = asyncio.run(suggest("가" * 101))
    assert too_long.status_code == 422
    assert calls == []

    at_limit = asyncio.run(suggest("가" * 100))
    assert at_limit.status_code == 200
    assert len(calls) == 1


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
    # discord.com 만 보면 구 도메인 discordapp.com 을 놓쳐 Slack 형식 {"text":...}
    # 을 보내게 되고, Discord 는 이를 400 으로 거절합니다.
    assert "*discord*.com/api/webhooks/*" in script
    assert "{\\\"content\\\"" in script
    # 시크릿에 섞여 들어온 공백은 URL 경로를 깨뜨리므로 떼어내야 합니다.
    assert "${BITBOX_ALERT_WEBHOOK_URL//[[:space:]]/}" in script
    # 상태 코드를 남겨야 400(페이로드 형식)과 401·404(URL·토큰)를 구분할 수 있습니다.
    assert "alert delivery failed (HTTP ${http_code:-000})" in script
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
