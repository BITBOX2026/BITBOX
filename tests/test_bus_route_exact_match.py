import asyncio

from app.services.transit import public_bus_service


def test_bus_route_search_does_not_fall_back_to_similar_number(monkeypatch) -> None:
    async def fake_payload(*_args, **_kwargs):
        return {
            "msgBody": {
                "itemList": [
                    {"busRouteId": "1", "busRouteNm": "3412"},
                    {"busRouteId": "2", "busRouteNm": "340"},
                ]
            }
        }

    monkeypatch.setattr(public_bus_service, "request_seoul_bus_payload", fake_payload)
    assert asyncio.run(public_bus_service.search_bus_route("3400")) is None


def test_bus_route_search_selects_only_exact_number(monkeypatch) -> None:
    async def fake_payload(*_args, **_kwargs):
        return {
            "msgBody": {
                "itemList": [
                    {"busRouteId": "1", "busRouteNm": "3412"},
                    {"busRouteId": "2", "busRouteNm": "3400"},
                ]
            }
        }

    monkeypatch.setattr(public_bus_service, "request_seoul_bus_payload", fake_payload)
    selected = asyncio.run(public_bus_service.search_bus_route("3400"))
    assert selected and selected["busRouteId"] == "2"
