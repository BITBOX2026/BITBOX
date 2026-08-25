import asyncio

import httpx
import pytest

from app.services.core.exceptions import TransportAPIError
from app.services.core.service_types import ParsedIntent
from app.services.transit import public_bus_service, seoul_bus_client


def test_no_result_code_is_returned_as_empty_search(monkeypatch) -> None:
    async def fake_get(_url: str, _params: dict[str, str]) -> httpx.Response:
        return httpx.Response(
            200,
            json={"msgHeader": {"headerCd": "4", "headerMsg": "결과가 없습니다."}},
            request=httpx.Request("GET", "http://example.test"),
        )

    monkeypatch.setattr(seoul_bus_client, "_seoul_bus_get", fake_get)
    monkeypatch.setattr(seoul_bus_client, "_get_first_service_key", lambda _names: "key")
    payload = asyncio.run(
        seoul_bus_client.request_seoul_bus_payload("http://example.test", {}, "노선 조회")
    )
    assert payload["msgHeader"]["headerCd"] == "4"


def test_missing_bus_route_requests_exact_number_again(monkeypatch) -> None:
    async def no_route(_bus_number: str):
        return None

    monkeypatch.setattr(public_bus_service, "search_bus_route", no_route)
    parsed = ParsedIntent(
        intent="arrival",
        stop_text="올림픽공원역",
        transport_mode="bus",
        bus_number="3423",
        confidence=1.0,
    )
    with pytest.raises(TransportAPIError) as captured:
        asyncio.run(public_bus_service.search_bus_arrival(parsed))
    assert "3423번 노선을 확인하지 못했습니다" in captured.value.user_message
    assert "비슷한 번호로 추정하지 않을게요" in captured.value.user_message
