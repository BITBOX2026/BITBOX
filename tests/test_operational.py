"""Operational behavior tests."""

import asyncio
import json
import re
import ssl

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

import app.main as main_module
from app.core.request_context import request_context_middleware, request_id_for
from app.core.runtime_metrics import record_safety_decision, runtime_snapshot
from app.main import readiness_check
from scripts import production_smoke


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    })


def test_request_id_accepts_safe_proxy_value() -> None:
    request = _request([(b"x-request-id", b"proxy-request-123")])
    assert request_id_for(request) == "proxy-request-123"


def test_request_id_replaces_untrusted_value() -> None:
    request = _request([(b"x-request-id", b"bad value with spaces")])
    assert re.fullmatch(r"[0-9a-f]{32}", request_id_for(request))


def test_request_context_adds_operational_headers() -> None:
    async def call_next(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    response = asyncio.run(request_context_middleware(_request(), call_next))
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert int(response.headers["x-response-time-ms"]) >= 0
    assert response.headers["cache-control"] == "no-store"


def test_runtime_metrics_count_privacy_safe_pipeline_dimensions() -> None:
    before = runtime_snapshot()
    record_safety_decision("verified", "odsay", "route")
    after = runtime_snapshot()

    assert after["safety_decisions"].get("verified", 0) == before["safety_decisions"].get("verified", 0) + 1
    assert after["pipeline_sources"].get("odsay", 0) == before["pipeline_sources"].get("odsay", 0) + 1
    assert after["pipeline_intents"].get("route", 0) == before["pipeline_intents"].get("route", 0) + 1


def test_readiness_contract(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "circuit_snapshot", dict)
    monkeypatch.setattr(main_module.settings, "RELEASE_SHA", "a" * 40)
    response = readiness_check()
    assert response.status == "ready"
    assert response.version
    assert response.release_sha == "a" * 40


def test_health_contract_includes_release_sha(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "RELEASE_SHA", "b" * 40)
    response = main_module.health_check()
    assert response.release_sha == "b" * 40


def test_production_smoke_rejects_a_stale_release(monkeypatch) -> None:
    headers = {
        "Content-Security-Policy": "default-src 'self'",
        "Strict-Transport-Security": "max-age=31536000",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Request-ID": "test-request",
    }

    def fake_request(url: str):
        if url.endswith("/health"):
            return 200, headers, b'{"status":"ok","release_sha":"old"}'
        if url.endswith("/ready"):
            return 200, headers, b'{"status":"ready","release_sha":"old"}'
        return 404, headers, b"{}"

    monkeypatch.setattr(production_smoke, "_request", fake_request)
    monkeypatch.setattr(production_smoke, "_certificate_days_remaining", lambda *_: 30)

    errors = production_smoke.verify(
        "https://example.com",
        minimum_certificate_days=14,
        expected_release_sha="c" * 40,
    )
    assert "/health release_sha does not match the deployment commit" in errors
    assert "/ready release_sha does not match the deployment commit" in errors


def test_production_transit_smoke_rejects_inconsistent_route_time(monkeypatch) -> None:
    def fake_request(url: str, **_kwargs):
        if url.endswith("/api/bus/default"):
            return 200, {}, b'{"success":true,"items":[]}'
        if "/api/places/suggest" in url:
            return 200, {}, b'{"suggestions":[{"category_code":"SW8"}]}'
        return 200, {}, json.dumps({
            "success": True,
            "buses": [{
                "routeDetail": {
                    "totalMin": 30,
                    "steps": [
                        {"type": "walk", "durationMin": 1},
                        {"type": "bus", "durationMin": 41},
                    ],
                }
            }],
        }).encode()

    monkeypatch.setattr(production_smoke, "_request", fake_request)
    errors: list[str] = []
    production_smoke._verify_transit_apis("https://example.com", errors)
    assert errors == ["route API did not return a consistent bus-only route"]


def test_readiness_fails_while_external_circuit_is_open(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "circuit_snapshot",
        lambda: {"seoul_bus": {"open": True, "failures": 3}},
    )

    with pytest.raises(HTTPException) as exc_info:
        readiness_check()

    assert exc_info.value.status_code == 503


def test_readiness_http_boundary_returns_503_for_open_circuit(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "circuit_snapshot",
        lambda: {"odsay": {"open": True, "failures": 5}},
    )

    async def request_ready() -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/ready")

    response = asyncio.run(request_ready())
    assert response.status_code == 503
    assert response.json()["detail"]


def test_production_smoke_requires_tls_1_2_or_newer() -> None:
    context = production_smoke._secure_ssl_context()
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_production_smoke_tolerates_provider_wait_time_in_the_total(monkeypatch) -> None:
    """ODsay 총시간은 대기시간을 포함할 수 있어 구간합과 정확히 같지 않을 수 있습니다.

    배포 스모크가 등호를 요구하면 정상 데이터에서도 배포가 실패합니다. 계약은
    "구간합이 총시간을 넘지 않는다"이므로 그 조건만 검사해야 합니다.
    """
    route_payload = {
        "success": True,
        "buses": [{
            "routeDetail": {
                "totalMin": 30,
                "steps": [
                    {"type": "walk", "durationMin": 3},
                    {"type": "bus", "durationMin": 20},
                ],
            }
        }],
    }
    errors = _run_transit_verification(monkeypatch, route_payload)
    assert not [error for error in errors if "route API" in error]


def test_production_smoke_survives_a_malformed_suggestion_payload(monkeypatch) -> None:
    """후보 목록이 dict 가 아니어도 traceback 대신 오류 문자열을 남겨야 합니다."""
    errors = _run_transit_verification(
        monkeypatch,
        {"success": True, "buses": [{"routeDetail": {"totalMin": 5, "steps": [{"type": "bus", "durationMin": 5}]}}]},
        suggestions=["강남역"],
    )
    assert any("place suggestion" in error for error in errors)


def _run_transit_verification(monkeypatch, route_payload: dict, suggestions=None) -> list[str]:
    """`_verify_transit_apis` 를 네트워크 없이 실행합니다."""
    if suggestions is None:
        suggestions = [{"category_code": "SW8", "name": "강남역"}]

    def fake_request(url: str, **_kwargs):
        if url.endswith("/api/bus/default"):
            body = {"success": True}
        elif "/api/places/suggest" in url:
            body = {"suggestions": suggestions}
        else:
            body = route_payload
        return 200, {}, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(production_smoke, "_request", fake_request)
    errors: list[str] = []
    production_smoke._verify_transit_apis("https://example.test", errors)
    return errors
