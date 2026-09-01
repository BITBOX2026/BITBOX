"""Regression tests for upstream business errors and API observability."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

import app.main as main_module
from app.api import gateway
from app.core.config import settings
from app.core.runtime_metrics import runtime_snapshot
from app.routers import bus as bus_router_module
from app.routers import place as place_router_module
from app.schemas.bus import DefaultBusArrivalResponse
from app.services.core import http_utils
from app.services.core.exceptions import ExternalServiceError, RouteNotFoundError
from app.services.transit import kakao_service, odsay_service, seoul_bus_client


@pytest.fixture(autouse=True)
def isolate_external_circuit_state():
    """Make readiness assertions independent of test order and prior providers."""
    with http_utils._circuit_lock:
        http_utils._circuits.clear()
    from app.core import usage_guard
    usage_guard._states.pop("odsay", None)
    yield
    with http_utils._circuit_lock:
        http_utils._circuits.clear()
    usage_guard._states.pop("odsay", None)


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


class _HttpErrorResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _KakaoAuthFailureClient:
    async def get(self, *_args, **_kwargs) -> _HttpErrorResponse:
        return _HttpErrorResponse(401)


def test_kakao_auth_failure_opens_circuit(monkeypatch) -> None:
    circuit_name = "app.services.transit.kakao_service._kakao_fetch"
    monkeypatch.setattr(kakao_service, "get_http_client", _KakaoAuthFailureClient)
    http_utils._circuits.pop(circuit_name, None)

    try:
        with pytest.raises(ExternalServiceError) as exc_info:
            asyncio.run(kakao_service._kakao_fetch("redacted", "강남역"))
        assert exc_info.value.retryable is False
        assert http_utils.circuit_snapshot()[circuit_name]["open"] is True
    finally:
        http_utils._circuits.pop(circuit_name, None)


def test_seoul_bus_business_auth_failure_opens_circuit(monkeypatch) -> None:
    circuit_name = (
        "app.services.transit.seoul_bus_client.request_seoul_bus_payload"
    )

    async def business_error(_url: str, _params: dict[str, str]) -> httpx.Response:
        return httpx.Response(
            200,
            json={"msgHeader": {"headerCd": "7", "headerMsg": "KEY인증실패"}},
            request=httpx.Request("GET", "http://example.test"),
        )

    monkeypatch.setattr(seoul_bus_client, "_seoul_bus_get", business_error)
    monkeypatch.setattr(
        seoul_bus_client,
        "_get_first_service_key",
        lambda _names: "redacted",
    )
    http_utils._circuits.pop(circuit_name, None)

    try:
        with pytest.raises(ExternalServiceError) as exc_info:
            asyncio.run(
                seoul_bus_client.request_seoul_bus_payload(
                    "http://example.test",
                    {},
                    "정류장 조회",
                    service_key_param_names=("ServiceKey",),
                )
            )
        assert exc_info.value.retryable is False
        assert http_utils.circuit_snapshot()[circuit_name]["open"] is True
    finally:
        http_utils._circuits.pop(circuit_name, None)


def test_place_failure_and_empty_result_have_different_http_statuses(monkeypatch) -> None:
    async def failed_search(*_args, **_kwargs):
        raise ExternalServiceError(
            "provider unavailable",
            user_message="장소 검색 서비스를 사용할 수 없습니다.",
        )

    async def request_suggestions() -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/places/suggest", params={"query": "강남역"})

    monkeypatch.setattr(place_router_module, "search_place_suggestions", failed_search)
    failed = asyncio.run(request_suggestions())
    assert failed.status_code == 502
    assert "장소 검색" in failed.json()["detail"]

    async def empty_search(*_args, **_kwargs):
        return []

    monkeypatch.setattr(place_router_module, "search_place_suggestions", empty_search)
    empty = asyncio.run(request_suggestions())
    assert empty.status_code == 200
    assert empty.json() == {"suggestions": []}


def test_bus_provider_failure_is_observable_as_502(monkeypatch) -> None:
    async def failed_arrivals() -> DefaultBusArrivalResponse:
        return DefaultBusArrivalResponse(
            success=False,
            station_name="올림픽공원역",
            station_id="24245",
            message="버스 도착정보 서비스를 사용할 수 없습니다.",
        )

    monkeypatch.setattr(bus_router_module, "get_default_bus_arrivals", failed_arrivals)

    async def request_board() -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/bus/default")

    response = asyncio.run(request_board())
    assert response.status_code == 502
    assert response.json()["success"] is False


# ---------------------------------------------------------------------------
# 회로차단기: "제공자 고장"과 "요청 하나의 4xx"를 구분하는지
#
# /ready 는 회로가 하나라도 열리면 503 을 냅니다. 그래서 요청 하나에 대한 400/404
# 같은 클라이언트 오류로 회로를 즉시 열면, 제공자가 멀쩡한데도 서비스 전체가
# 준비되지 않은 것으로 보고됩니다. 배포 readiness 검사와 외부 모니터가 여기에
# 걸릴 수 있으므로, 즉시 개방은 인증·설정 실패에만 적용되어야 합니다.
# ---------------------------------------------------------------------------

def test_request_level_client_error_does_not_open_the_circuit_immediately(monkeypatch) -> None:
    circuit_name = "app.services.transit.kakao_service._kakao_fetch"
    http_utils._circuits.pop(circuit_name, None)

    class _NotFoundResponse:
        status_code = 404

        def json(self) -> dict:
            return {}

    class _NotFoundClient:
        async def get(self, *_args, **_kwargs):
            return _NotFoundResponse()

    monkeypatch.setattr(kakao_service, "get_http_client", lambda: _NotFoundClient())

    try:
        with pytest.raises(ExternalServiceError) as exc_info:
            asyncio.run(kakao_service._kakao_fetch("key", "존재하지 않는 장소"))

        assert exc_info.value.retryable is False
        assert exc_info.value.provider_down is False
        snapshot = http_utils.circuit_snapshot()[circuit_name]
        assert snapshot["open"] is False, "요청 단위 4xx가 회로를 즉시 열면 안 됩니다"
        assert snapshot["failures"] == 1
        # 제공자가 정상이므로 준비 상태도 유지되어야 합니다.
        assert main_module.readiness_check().status == "ready"
    finally:
        http_utils._circuits.pop(circuit_name, None)


def test_provider_authentication_failure_opens_the_circuit_immediately(monkeypatch) -> None:
    circuit_name = "app.services.transit.kakao_service._kakao_fetch"
    http_utils._circuits.pop(circuit_name, None)

    class _ForbiddenResponse:
        status_code = 401

        def json(self) -> dict:
            return {}

    class _ForbiddenClient:
        async def get(self, *_args, **_kwargs):
            return _ForbiddenResponse()

    monkeypatch.setattr(kakao_service, "get_http_client", lambda: _ForbiddenClient())

    try:
        with pytest.raises(ExternalServiceError) as exc_info:
            asyncio.run(kakao_service._kakao_fetch("bad-key", "강남역"))

        assert exc_info.value.provider_down is True
        assert http_utils.circuit_snapshot()[circuit_name]["open"] is True
        with pytest.raises(HTTPException) as ready_exc:
            main_module.readiness_check()
        assert ready_exc.value.status_code == 503
    finally:
        http_utils._circuits.pop(circuit_name, None)


def test_repeated_request_level_failures_still_open_the_circuit(monkeypatch) -> None:
    """제공자가 계속 실패하면 임계값에서는 열려야 합니다."""
    circuit_name = "app.services.transit.kakao_service._kakao_fetch"
    http_utils._circuits.pop(circuit_name, None)

    class _NotFoundResponse:
        status_code = 404

        def json(self) -> dict:
            return {}

    class _NotFoundClient:
        async def get(self, *_args, **_kwargs):
            return _NotFoundResponse()

    monkeypatch.setattr(kakao_service, "get_http_client", lambda: _NotFoundClient())

    try:
        for _ in range(settings.EXTERNAL_CIRCUIT_FAILURE_THRESHOLD):
            with pytest.raises(ExternalServiceError):
                asyncio.run(kakao_service._kakao_fetch("key", "없는 장소"))
        assert http_utils.circuit_snapshot()[circuit_name]["open"] is True
    finally:
        http_utils._circuits.pop(circuit_name, None)
