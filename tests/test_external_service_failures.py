"""Regression tests for upstream business errors and API observability."""

import asyncio

import httpx
import pytest

import app.main as main_module
from app.api import gateway
from app.core.runtime_metrics import runtime_snapshot
from app.services.core import http_utils
from app.services.core.exceptions import ExternalServiceError, RouteNotFoundError
from app.services.transit import odsay_service


class _BusinessErrorResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "error": [
                {"code": "500", "message": "[ApiKeyAuthFailed] authentication failed"}
            ]
        }


class _BusinessErrorClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get(self, *_args, **_kwargs) -> _BusinessErrorResponse:
        self.calls += 1
        return _BusinessErrorResponse()


def test_http_200_business_error_opens_circuit_and_fails_readiness(monkeypatch) -> None:
    client = _BusinessErrorClient()
    circuit_name = "app.services.transit.odsay_service._odsay_fetch"
    monkeypatch.setattr(odsay_service, "get_http_client", lambda: client)
    http_utils._circuits.pop(circuit_name, None)

    try:
        with pytest.raises(ExternalServiceError, match="ApiKeyAuthFailed") as exc_info:
            asyncio.run(odsay_service._odsay_fetch({"apiKey": "redacted"}))

        assert exc_info.value.retryable is False
        assert client.calls == 1
        assert http_utils.circuit_snapshot()[circuit_name]["open"] is True
        with pytest.raises(Exception) as ready_exc:
            main_module.readiness_check()
        assert getattr(ready_exc.value, "status_code", None) == 503
    finally:
        http_utils._circuits.pop(circuit_name, None)


def test_healthy_provider_with_no_bus_path_is_not_an_upstream_failure(monkeypatch) -> None:
    async def no_paths(_params: dict) -> dict:
        return {"result": {"path": []}}

    monkeypatch.setattr(odsay_service, "_odsay_fetch", no_paths)
    monkeypatch.setattr(odsay_service, "get_setting", lambda *_args: "configured")

    with pytest.raises(RouteNotFoundError) as exc_info:
        asyncio.run(
            odsay_service.search_odsay_route(
                "출발지",
                127.0,
                37.5,
                "목적지",
                127.1,
                37.6,
                "bus",
            )
        )

    assert exc_info.value.http_status == 404
    assert exc_info.value.error_kind == "route_not_found"


def test_route_endpoint_returns_502_for_upstream_failure(monkeypatch) -> None:
    async def failed_route(**_kwargs) -> dict:
        return {
            "status": "error",
            "message": "외부 경로 서비스를 사용할 수 없습니다.",
            "data": {},
            "error_kind": "external_service",
            "_http_status": 502,
            "audio_base64": None,
            "request_id": "test-request",
        }

    monkeypatch.setattr(gateway, "run_text_route", failed_route)

    async def request_route() -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/route",
                json={
                    "destination": "강남역 2호선",
                    "destination_x": 127.0276,
                    "destination_y": 37.4979,
                    "transport_mode": "bus",
                },
            )

    before = runtime_snapshot()
    response = asyncio.run(request_route())
    after = runtime_snapshot()
    assert response.status_code == 502
    assert response.json()["success"] is False
    assert response.json()["error_kind"] == "external_service"
    assert after["server_errors"] == before["server_errors"] + 1
