"""
서울시 버스 공공데이터 API 클라이언트 — 실시간 도착 정보 조회

서울시 Open API(ws.bus.go.kr)를 사용하며 다음 순서로 정보를 조회합니다:

1. 버스 번호로 노선 ID 조회 (getBusRouteList)
2. 노선 경유 정류소 목록에서 사용자가 말한 정류장 검색 (getStaionByRoute)
3. 해당 정류장의 실시간 버스 도착 정보 조회 (getArrInfoByRoute)
"""

from app.core.logger import get_logger
from app.services.core.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
)
from app.services.core.exceptions import TransportAPIError
from app.services.core.korean_text import normalize_station_reference
from app.services.core.service_types import ParsedIntent, TransportResult
from app.services.core.settings_helper import get_setting
from app.services.transit.seoul_bus_client import request_seoul_bus_payload
from app.services.transit.seoul_bus_parser import (
    build_route_station,
    contains_normalized,
    equals_normalized,
    extract_arrival_station_name,
    extract_arrival_times,
    extract_items,
    find_first,
    first_item_value,
    is_matching_bus_route,
    normalize_token,
    parse_first_bus_time,
)

logger = get_logger(__name__)


async def search_bus_arrival(parsed: ParsedIntent) -> TransportResult:
    """
    버스 번호와 정류장명으로 실시간 도착 정보를 조회합니다.

    stop_text가 없으면 DEFAULT_BUS_STATION_ID(기기 기본 정류장)를 사용합니다.
    조회 실패 시 TransportAPIError를 발생시킵니다.
    """
    if not parsed.bus_number:
        raise TransportAPIError(user_message="버스 번호를 말씀해 주세요.")

    # stop_text 없으면 getStationByUid로 기본 정류장에서 직접 조회 (더 신뢰성 높음)
    if not parsed.stop_text:
        return await _search_arrival_at_default_stop(parsed.bus_number)

    # 1단계: 버스 번호 → 노선 ID
    bus_route = await search_bus_route(parsed.bus_number)
    if not bus_route:
        raise TransportAPIError(user_message=_bus_number_reconfirmation_message(parsed.bus_number))

    bus_route_id = first_item_value(bus_route, ["busRouteId"])
    if not bus_route_id:
        raise TransportAPIError(user_message=_bus_number_reconfirmation_message(parsed.bus_number))

    # 2단계: 노선 경유 정류소에서 정류장 이름으로 검색
    route_station = await _find_route_station_by_stop_text(
        bus_route_id=bus_route_id,
        stop_text=parsed.stop_text,
    )

    if not route_station:
        raise TransportAPIError(
            user_message="해당 노선에서 정류장을 찾지 못했습니다."
        )

    # 3단계: 실시간 도착 시간 조회
    arrival = await get_bus_arrival_time(
        bus_route_id=bus_route_id,
        station_id=route_station["station_id"],
        order=route_station["order"],
        station_name=route_station["station_name"],
    )

    arrival_time = arrival.get("arrival_time")
    if not arrival_time:
        raise TransportAPIError(
            user_message="해당 정류장의 버스 도착 정보를 찾지 못했습니다."
        )

    # 운행종료 시 노선 정보에서 내일 첫차 시간 추출 (추가 API 호출 없음)
    first_bus_time: str | None = None
    if arrival_time == "운행종료":
        first_bus_time = parse_first_bus_time(
            first_item_value(bus_route, ["firstBusTm", "firstBusTime"])
        )

    return TransportResult(
        stop_name=arrival.get("station_name") or route_station["station_name"],
        transport_mode="bus",
        bus_number=parsed.bus_number,
        arrival_time=arrival_time,
        arrival_time_2=arrival.get("arrival_time_2"),
        first_bus_time=first_bus_time,
        source="public_data",
    )


async def search_bus_route(bus_number: str) -> dict[str, str] | None:
    """버스 번호로 서울시 노선 정보를 조회합니다. 정확히 일치하는 노선을 우선 선택합니다."""
    payload = await request_seoul_bus_payload(
        SEOUL_BUS_ROUTE_SEARCH_URL,
        {"strSrch": bus_number},
        stage="노선 ID 조회",
    )

    items = extract_items(payload)
    if not items:
        return None

    # 검색 API는 유사 노선도 반환하므로 정확히 일치하지 않으면 선택하지 않습니다.
    exact_match = find_first(items, lambda item: is_matching_bus_route(item, bus_number))
    return exact_match if exact_match and first_item_value(exact_match, ["busRouteId"]) else None


async def get_bus_arrival_time(
    bus_route_id: str,
    station_id: str,
    order: str | None = None,
    station_name: str | None = None,
) -> dict[str, str | None]:
    """노선 ID와 정류장 ID로 실시간 도착 예정 정보를 조회합니다."""

    route_station = {
        "order": order or "",
        "station_name": station_name or "",
    }

    # 순번(ord)이 없으면 노선 경유 정류소 목록에서 조회
    if not route_station["order"]:
        found_station = await _find_route_station(
            bus_route_id=bus_route_id,
            station_id=station_id,
        )
        if not found_station:
            return {"arrival_time": None, "station_name": None}
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
            "arrival_time_2": None,
            "station_name": route_station["station_name"],
        }

    first_arrival = items[0]
    arrival_time, arrival_time_2 = extract_arrival_times(first_arrival)
    return {
        "arrival_time": arrival_time,
        "arrival_time_2": arrival_time_2,
        "station_name": (
            extract_arrival_station_name(first_arrival) or route_station["station_name"]
        ),
    }


async def fetch_arrival_at_stop(
    bus_number: str,
    stop_name: str,
) -> tuple[str | None, str | None]:
    """특정 정류장에서 특정 버스의 실시간 도착 시간을 조회합니다.

    경로 결과의 첫 번째 버스 탑승 정류장 기준으로 도착 시간을 가져올 때 사용합니다.

    Returns:
        (arrival_time, arrival_time_2) — 첫 번째·두 번째 버스 도착 시간
    """
    bus_route = await search_bus_route(bus_number)
    if not bus_route:
        return None, None

    bus_route_id = first_item_value(bus_route, ["busRouteId"])
    if not bus_route_id:
        return None, None

    route_station = await _find_route_station_by_stop_text(
        bus_route_id=bus_route_id,
        stop_text=stop_name,
    )
    if not route_station:
        return None, None

    arrival = await get_bus_arrival_time(
        bus_route_id=bus_route_id,
        station_id=route_station["station_id"],
        order=route_station["order"],
        station_name=route_station["station_name"],
    )
    return arrival.get("arrival_time"), arrival.get("arrival_time_2")


async def fetch_arrival_at_default_stop(bus_number: str) -> tuple[str | None, str | None]:
    """기기 기본 정류장(DEFAULT_BUS_STATION_ID)에서 버스 실시간 도착 시간을 조회합니다.

    getStationByUid(arsId)로 정류장 전체 버스를 한 번에 가져온 뒤
    버스 번호로 필터링합니다. route 기반 3-step 조회보다 단순하고 신뢰성이 높습니다.

    Returns:
        (arrival_time, arrival_time_2) — 첫 번째·두 번째 버스 도착 시간
    """
    from app.services.bus_service import get_bus_arrivals_by_station_id

    default_ars_id = str(get_setting("DEFAULT_BUS_STATION_ID") or "").strip()
    if not default_ars_id:
        return None, None

    response = await get_bus_arrivals_by_station_id(default_ars_id)
    if not response.success:
        return None, None

    target = normalize_token(bus_number)
    for item in response.items:
        if normalize_token(item.bus_number) != target:
            continue
        return (
            _arrmsg_or_minutes(item.raw_arrmsg1, item.first_arrival_min),
            _arrmsg_or_minutes(item.raw_arrmsg2, item.second_arrival_min),
        )

    return None, None


async def _search_arrival_at_default_stop(bus_number: str) -> TransportResult:
    """기본 정류장(DEFAULT_BUS_STATION_ID)에서 getStationByUid로 버스 도착 시간을 조회합니다."""
    from app.services.bus_service import get_bus_arrivals_by_station_id

    default_ars_id = str(get_setting("DEFAULT_BUS_STATION_ID") or "").strip()
    if not default_ars_id:
        raise TransportAPIError(user_message="어느 정류장 기준인지 말씀해 주세요.")

    response = await get_bus_arrivals_by_station_id(default_ars_id)
    if not response.success:
        raise TransportAPIError(user_message="버스 도착정보 조회에 실패했습니다.")

    target = normalize_token(bus_number)
    for item in response.items:
        if normalize_token(item.bus_number) != target:
            continue
        arrival_time = _arrmsg_or_minutes(item.raw_arrmsg1, item.first_arrival_min)
        arrival_time_2 = _arrmsg_or_minutes(item.raw_arrmsg2, item.second_arrival_min)
        if not arrival_time:
            continue
        return TransportResult(
            stop_name=response.station_name,
            transport_mode="bus",
            bus_number=bus_number,
            arrival_time=arrival_time,
            arrival_time_2=arrival_time_2,
            source="public_data",
        )

    raise TransportAPIError(user_message=_bus_number_reconfirmation_message(bus_number))


def _bus_number_reconfirmation_message(bus_number: str) -> str:
    return (
        f"현재 정류장에서 {bus_number}번 노선을 확인하지 못했습니다. "
        "비슷한 번호로 추정하지 않을게요. 버스 번호를 다시 말씀해 주세요."
    )


def _arrmsg_or_minutes(raw_arrmsg: str | None, minutes: int | None) -> str | None:
    if raw_arrmsg:
        return raw_arrmsg
    if minutes is None:
        return None
    return "곧 도착" if minutes <= 0 else f"{minutes}분 후"


async def _find_route_station_by_stop_text(
    bus_route_id: str,
    stop_text: str,
) -> dict[str, str] | None:
    """노선 경유 정류소 목록에서 사용자가 말한 정류장명으로 정류소 정보를 찾습니다.

    서울에서는 같은 이름의 정류장이 상·하행 양쪽에 있는 것이 흔합니다. 이름만
    보고 먼저 나온 것을 고르면 **반대 방향 차량의 도착 시간을 안내**할 수 있습니다.
    기기가 설치된 정류장(arsId)은 방향까지 특정되므로, 후보 중에 그 정류장이 있으면
    항상 그것을 씁니다.
    """
    payload = await request_seoul_bus_payload(
        SEOUL_ROUTE_STATION_URL,
        {"busRouteId": bus_route_id},
        stage="노선 경유 정류소 조회",
    )

    normalized_stop_text = normalize_station_reference(stop_text)
    exact_candidates: list[dict[str, str]] = []
    partial_candidates: list[dict[str, str]] = []

    for item in extract_items(payload):
        station_name = first_item_value(item, ["stationNm", "stNm"]) or ""
        if equals_normalized(station_name, normalized_stop_text):
            exact_candidates.append(item)
            continue
        if contains_normalized(station_name, normalized_stop_text):
            partial_candidates.append(item)

    # 정확 일치가 하나라도 있으면 부분 일치는 방향 후보에 섞지 않습니다. 예를 들어
    # "강남역"과 "강남역사거리"가 함께 있어도 전자만 사용해야 합니다.
    matching_items = exact_candidates or partial_candidates
    resolved = [
        station
        for item in matching_items
        if (station := build_route_station(item))
    ]
    if not resolved:
        return None

    device_ars_id = str(get_setting("DEFAULT_BUS_STATION_ID") or "").strip()
    if device_ars_id:
        for station in resolved:
            if station.get("ars_id") == device_ars_id:
                return station

    if len(resolved) == 1:
        return resolved[0]

    # 방향을 확정할 단서가 없습니다. API 반환 순서의 첫 항목을 쓰면 반대 방향
    # 도착정보를 안내할 수 있으므로 조회 실패로 돌려 상위에서 재확인하게 합니다.
    logger.warning(
        "정류장 이름이 노선에서 여러 번 나타납니다. 방향을 확정하지 못했습니다: "
        "route=%s matches=%d ars_ids=%s",
        bus_route_id,
        len(resolved),
        ",".join(station.get("ars_id") or "?" for station in resolved[:4]),
    )
    raise TransportAPIError(
        user_message=(
            "같은 이름의 정류장이 여러 방향에 있습니다. "
            "정류장 번호나 방향을 다시 말씀해 주세요."
        )
    )


async def _find_route_station(
    bus_route_id: str,
    station_id: str,
) -> dict[str, str] | None:
    """노선 경유 정류소 목록에서 정류장 ID로 순번(ord)을 찾습니다."""
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
