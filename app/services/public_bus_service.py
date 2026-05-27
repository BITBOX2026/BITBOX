from app.services.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.exceptions import TransportAPIError
from app.services.seoul_bus_client import request_seoul_bus_payload
from app.services.seoul_bus_parser import (
    build_route_station,
    contains_normalized,
    extract_arrival_station_name,
    extract_arrival_time,
    extract_items,
    find_first,
    first_item_value,
    is_matching_bus_route,
)
from app.services.service_types import ParsedIntent, TransportResult


async def search_bus_arrival(parsed: ParsedIntent) -> TransportResult:
    """서울시 버스 공공데이터 API로 실시간 버스 도착 정보를 조회합니다."""

    if not parsed.bus_number:
        raise TransportAPIError("버스 번호를 말씀해 주세요.")

    if not parsed.stop_text:
        raise TransportAPIError("어느 정류장 기준인지 말씀해 주세요.")

    bus_route = await search_bus_route(parsed.bus_number)
    if not bus_route:
        raise TransportAPIError(
            "공공데이터 노선 ID 조회 실패: 해당 버스 노선을 찾지 못했습니다."
        )

    bus_route_id = first_item_value(bus_route, ["busRouteId"])
    if not bus_route_id:
        raise TransportAPIError(
            "공공데이터 노선 ID 조회 실패: 해당 버스 노선을 찾지 못했습니다."
        )

    route_station = await _find_route_station_by_stop_text(
        bus_route_id=bus_route_id,
        stop_text=parsed.stop_text,
    )
    if not route_station:
        raise TransportAPIError(
            "공공데이터 노선 경유 정류소 조회 실패: 해당 노선에서 정류장을 찾지 못했습니다."
        )

    arrival = await get_bus_arrival_time(
        bus_route_id=bus_route_id,
        station_id=route_station["station_id"],
        order=route_station["order"],
        station_name=route_station["station_name"],
    )

    arrival_time = arrival.get("arrival_time")
    if not arrival_time:
        raise TransportAPIError(
            "공공데이터 도착정보 조회 실패: 해당 정류장의 버스 도착 정보를 찾지 못했습니다."
        )

    return TransportResult(
        origin=None,
        destination=None,
        stop_name=arrival.get("station_name") or route_station["station_name"],
        transport_mode="bus",
        bus_number=parsed.bus_number,
        arrival_time=arrival_time,
        total_time_min=None,
        payment=None,
        bus_transit_count=None,
        subway_transit_count=None,
        transfer_count=None,
        path_type=None,
        route_summary=None,
        source="public_data",
    )


async def search_bus_route(bus_number: str) -> dict[str, str] | None:
    """버스 번호로 서울시 노선 후보를 조회하고 가장 적절한 노선을 선택합니다."""

    payload = await request_seoul_bus_payload(
        SEOUL_BUS_ROUTE_SEARCH_URL,
        {"strSrch": bus_number},
        stage="노선 ID 조회",
    )

    items = extract_items(payload)
    if not items:
        return None

    exact_match = find_first(
        items,
        lambda item: is_matching_bus_route(item, bus_number),
    )
    selected = exact_match or items[0]

    return selected if first_item_value(selected, ["busRouteId"]) else None


async def search_station(stop_text: str) -> dict[str, str] | None:
    """정류장명으로 첫 번째 서울시 정류장 후보를 조회합니다."""

    payload = await request_seoul_bus_payload(
        SEOUL_STATION_SEARCH_URL,
        {"stSrch": stop_text},
        stage="정류소정보 조회",
    )

    items = extract_items(payload)
    if not items:
        return None

    selected = items[0]
    station_id = first_item_value(selected, ["stId", "station", "stationId"])
    station_name = first_item_value(selected, ["stNm", "stationNm"]) or stop_text

    if not station_id:
        return None

    return {
        "station_id": station_id,
        "station_name": station_name,
    }


async def get_bus_arrival_time(
    bus_route_id: str,
    station_id: str,
    order: str | None = None,
    station_name: str | None = None,
) -> dict[str, str | None]:
    """노선 ID와 정류장 ID로 도착 예정 정보를 조회합니다."""

    route_station = {
        "order": order or "",
        "station_name": station_name or "",
    }

    if not route_station["order"]:
        found_station = await _find_route_station(
            bus_route_id=bus_route_id,
            station_id=station_id,
        )
        if not found_station:
            return {
                "arrival_time": None,
                "station_name": None,
            }

        route_station = found_station

    payload = await request_seoul_bus_payload(
        SEOUL_BUS_ARRIVAL_URL,
        {
            "stId": station_id,
            "busRouteId": bus_route_id,
            "ord": route_station["order"],
        },
        stage="도착정보 조회",
        service_key_param_names=("ServiceKey", "serviceKey"),
    )

    items = extract_items(payload)
    if not items:
        return {
            "arrival_time": None,
            "station_name": route_station["station_name"],
        }

    first_arrival = items[0]
    return {
        "arrival_time": extract_arrival_time(first_arrival),
        "station_name": extract_arrival_station_name(first_arrival)
        or route_station["station_name"],
    }


async def _find_route_station_by_stop_text(
    bus_route_id: str,
    stop_text: str,
) -> dict[str, str] | None:
    """노선 경유 정류소 목록에서 정류장명으로 도착정보 조회에 필요한 값을 찾습니다."""

    payload = await request_seoul_bus_payload(
        SEOUL_ROUTE_STATION_URL,
        {"busRouteId": bus_route_id},
        stage="노선 경유 정류소 조회",
    )

    for item in extract_items(payload):
        station_name = first_item_value(item, ["stationNm", "stNm"]) or ""
        if not contains_normalized(station_name, stop_text):
            continue

        route_station = build_route_station(item)
        if route_station:
            return route_station

    return None


async def _find_route_station(
    bus_route_id: str,
    station_id: str,
) -> dict[str, str] | None:
    """노선의 정류장 목록에서 정류장 순번(ord)을 찾습니다."""

    payload = await request_seoul_bus_payload(
        SEOUL_ROUTE_STATION_URL,
        {"busRouteId": bus_route_id},
        stage="노선 경유 정류소 조회",
    )

    for item in extract_items(payload):
        item_station_id = first_item_value(item, ["station", "stId", "stationId"])
        if item_station_id != station_id:
            continue

        return build_route_station(item)

    return None
