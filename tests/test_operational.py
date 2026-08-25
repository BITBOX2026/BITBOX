"""Operational behavior tests."""

import asyncio
import re

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

import app.main as main_module
from app.core.request_context import request_context_middleware, request_id_for
from app.core.runtime_metrics import record_safety_decision, runtime_snapshot
from app.main import readiness_check


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
    response = readiness_check()
    assert response.status == "ready"
    assert response.version


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
