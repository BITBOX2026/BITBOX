from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree

import httpx

from app.services.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.exceptions import TransportAPIError
from app.services.service_types import ParsedIntent, TransportResult
from app.services.settings_helper import get_setting


SUCCESS_CODES = {"0", "00", "NORMAL_CODE", "INFO-000", "SUCCESS"}


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

    bus_route_id = _first_item_value(bus_route, ["busRouteId"])
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

    payload = await _request_seoul_bus_payload(
        SEOUL_BUS_ROUTE_SEARCH_URL,
        {"strSrch": bus_number},
        stage="노선 ID 조회",
    )

    items = _extract_items(payload)
    if not items:
        return None

    exact_match = _find_first(
        items,
        lambda item: _is_matching_bus_route(item, bus_number),
    )
    selected = exact_match or items[0]

    return selected if _first_item_value(selected, ["busRouteId"]) else None


async def search_bus_route_id(bus_number: str) -> str | None:
    """버스 번호로 서울시 busRouteId를 조회합니다."""

    route = await search_bus_route(bus_number)
    if not route:
        return None

    return _first_item_value(route, ["busRouteId"])


async def search_station_id(stop_text: str) -> str | None:
    """정류장명으로 서울시 stId를 조회합니다."""

    station = await search_station(stop_text)
    if not station:
        return None

    return station["station_id"]


async def search_station(stop_text: str) -> dict[str, str] | None:
    """정류장명으로 첫 번째 서울시 정류장 후보를 조회합니다."""

    payload = await _request_seoul_bus_payload(
        SEOUL_STATION_SEARCH_URL,
        {"stSrch": stop_text},
        stage="정류소정보 조회",
    )

    items = _extract_items(payload)
    if not items:
        return None

    selected = items[0]
    station_id = _first_item_value(selected, ["stId", "station", "stationId"])
    station_name = _first_item_value(selected, ["stNm", "stationNm"]) or stop_text

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

    payload = await _request_seoul_bus_payload(
        SEOUL_BUS_ARRIVAL_URL,
        {
            "stId": station_id,
            "busRouteId": bus_route_id,
            "ord": route_station["order"],
        },
        stage="도착정보 조회",
        service_key_param_names=("ServiceKey", "serviceKey"),
    )

    items = _extract_items(payload)
    if not items:
        return {
            "arrival_time": None,
            "station_name": route_station["station_name"],
        }

    first_arrival = items[0]
    return {
        "arrival_time": _extract_arrival_time(first_arrival),
        "station_name": _extract_arrival_station_name(first_arrival)
        or route_station["station_name"],
    }


async def _find_route_station_by_stop_text(
    bus_route_id: str,
    stop_text: str,
) -> dict[str, str] | None:
    """노선 경유 정류소 목록에서 정류장명으로 도착정보 조회에 필요한 값을 찾습니다."""

    payload = await _request_seoul_bus_payload(
        SEOUL_ROUTE_STATION_URL,
        {"busRouteId": bus_route_id},
        stage="노선 경유 정류소 조회",
    )

    for item in _extract_items(payload):
        station_name = _first_item_value(item, ["stationNm", "stNm"]) or ""
        if not _contains_normalized(station_name, stop_text):
            continue

        route_station = _build_route_station(item)
        if route_station:
            return route_station

    return None


async def _find_route_station(
    bus_route_id: str,
    station_id: str,
) -> dict[str, str] | None:
    """노선의 정류장 목록에서 정류장 순번(ord)을 찾습니다."""

    payload = await _request_seoul_bus_payload(
        SEOUL_ROUTE_STATION_URL,
        {"busRouteId": bus_route_id},
        stage="노선 경유 정류소 조회",
    )

    for item in _extract_items(payload):
        item_station_id = _first_item_value(item, ["station", "stId", "stationId"])
        if item_station_id != station_id:
            continue

        return _build_route_station(item)

    return None


async def _request_seoul_bus_payload(
    url: str,
    params: dict[str, str],
    stage: str,
    service_key_param_names: tuple[str, ...] = ("ServiceKey", "serviceKey"),
) -> Any:
    """서울시 버스 API를 호출하고 JSON 우선으로 응답을 반환합니다."""

    service_key = _normalize_service_key(get_setting("PUBLIC_DATA_SERVICE_KEY"))
    if not service_key:
        raise TransportAPIError("PUBLIC_DATA_SERVICE_KEY가 설정되지 않았습니다.")

    last_auth_error: tuple[str, str] | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for index, service_key_param_name in enumerate(service_key_param_names):
                safe_params = {
                    service_key_param_name: service_key,
                    **params,
                    "resultType": "json",
                }

                response = await client.get(url, params=safe_params)
                response.raise_for_status()
                payload = _parse_response_payload(response, stage)

                code, message = _extract_result_code_message(payload)
                if code and not _is_success_code(code):
                    message = message or "공공데이터 API 오류"
                    if (
                        index + 1 < len(service_key_param_names)
                        and _is_service_key_error(code, message)
                    ):
                        last_auth_error = (code, message)
                        continue

                    raise TransportAPIError(
                        f"공공데이터 API 오류({stage}): resultCode={code}, resultMsg={message}"
                    )

                return payload

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"공공데이터 API HTTP 오류({stage}): status={exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError(f"공공데이터 API 요청 오류({stage})") from exc

    if last_auth_error:
        code, message = last_auth_error
        raise TransportAPIError(
            f"공공데이터 API 오류({stage}): resultCode={code}, resultMsg={message}"
        )

    raise TransportAPIError(f"공공데이터 API 오류({stage})")


def _parse_response_payload(response: httpx.Response, stage: str) -> Any:
    try:
        return response.json()

    except ValueError:
        pass

    try:
        return ElementTree.fromstring(response.text)

    except ElementTree.ParseError as exc:
        raise TransportAPIError(f"공공데이터 API 응답 해석 오류({stage})") from exc


def _normalize_service_key(service_key: object) -> str:
    """
    공공데이터포털의 Encoding/Decoding 키 입력을 모두 허용합니다.

    httpx params에 이미 percent-encoded 된 키를 그대로 넣으면 '%'가 다시
    인코딩되어 인증 실패가 날 수 있으므로, params에는 decoded 형태로 넣습니다.
    """

    if service_key is None:
        return ""

    return unquote(str(service_key).strip())


def _extract_items(payload: Any) -> list[dict[str, str]]:
    """서울시 API의 itemList/StationList를 dict 목록으로 정규화합니다."""

    if isinstance(payload, ElementTree.Element):
        return _extract_xml_items(payload)

    if isinstance(payload, dict):
        return _extract_json_items(payload)

    return []


def _extract_xml_items(root: ElementTree.Element) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    for item in list(root.iter("itemList")) + list(root.iter("StationList")):
        values: dict[str, str] = {}
        for child in list(item):
            values[child.tag] = child.text or ""

        items.append(values)

    return items


def _extract_json_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    item_keys = {"itemlist", "stationlist"}

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if str(key).lower() in item_keys:
                    items.extend(_normalize_item_container(nested_value))
                elif isinstance(nested_value, (dict, list)):
                    collect(nested_value)

        elif isinstance(value, list):
            for nested_value in value:
                if isinstance(nested_value, (dict, list)):
                    collect(nested_value)

    collect(payload)
    return items


def _normalize_item_container(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        return [
            _stringify_item(item)
            for item in value
            if isinstance(item, dict)
        ]

    if isinstance(value, dict):
        return [_stringify_item(value)]

    return []


def _stringify_item(item: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): "" if value is None else str(value)
        for key, value in item.items()
        if not isinstance(value, (dict, list))
    }


def _extract_arrival_time(item: dict[str, str]) -> str | None:
    """서울시 도착 응답에서 사용자에게 보여줄 도착 시간을 추출합니다."""

    first_message = _first_item_value(item, ["arrmsg1"])

    for message_key, time_key in [
        ("arrmsg1", "traTime1"),
        ("arrmsg2", "traTime2"),
    ]:
        arrival_message = _first_item_value(item, [message_key])
        if arrival_message and arrival_message != "출발대기":
            return arrival_message

        travel_time = _safe_int(_first_item_value(item, [time_key]))
        if travel_time is not None and travel_time > 0:
            minutes = max((travel_time + 59) // 60, 1)
            return f"{minutes}분 후"

    return first_message


def _extract_arrival_station_name(item: dict[str, str]) -> str | None:
    """도착정보 응답에서 정류장명 후보를 추출합니다."""

    return _first_item_value(
        item,
        ["stNm", "stationNm", "stationNm1", "stationNm2"],
    )


def _extract_result_code_message(payload: Any) -> tuple[str | None, str | None]:
    if isinstance(payload, ElementTree.Element):
        return (
            _find_first_xml_text(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_first_xml_text(
                payload,
                ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"],
            ),
        )

    if isinstance(payload, dict):
        return (
            _find_nested_value(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_nested_value(payload, ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"]),
        )

    return None, None


def _find_nested_value(value: Any, names: list[str]) -> str | None:
    normalized_names = {name.lower() for name in names}

    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in normalized_names and nested_value is not None:
                return str(nested_value)

        for nested_value in value.values():
            found = _find_nested_value(nested_value, names)
            if found:
                return found

    elif isinstance(value, list):
        for nested_value in value:
            found = _find_nested_value(nested_value, names)
            if found:
                return found

    return None


def _find_first_xml_text(root: ElementTree.Element, tag_names: list[str]) -> str | None:
    for tag_name in tag_names:
        for element in root.iter(tag_name):
            if element.text:
                return element.text

    return None


def _build_route_station(item: dict[str, str]) -> dict[str, str] | None:
    station_id = _first_item_value(item, ["station", "stId", "stationId"])
    order = _first_item_value(item, ["seq", "staOrd", "ord"])
    station_name = _first_item_value(item, ["stationNm", "stNm"]) or ""
    ars_id = _first_item_value(item, ["arsId", "stationNo"]) or ""

    if not station_id or not order:
        return None

    return {
        "station_id": station_id,
        "order": order,
        "station_name": station_name,
        "ars_id": ars_id,
    }


def _first_item_value(item: dict[str, str], names: list[str]) -> str | None:
    for name in names:
        value = item.get(name)
        if value:
            return value

    lower_item = {key.lower(): value for key, value in item.items()}
    for name in names:
        value = lower_item.get(name.lower())
        if value:
            return value

    return None


def _is_matching_bus_route(item: dict[str, str], bus_number: str) -> bool:
    target = _normalize_token(bus_number)
    route_names = [
        _first_item_value(item, ["busRouteNm"]),
        _first_item_value(item, ["busRouteAbrv"]),
    ]

    return any(_normalize_token(route_name) == target for route_name in route_names)


def _contains_normalized(text: str, keyword: str) -> bool:
    normalized_text = _normalize_token(text)
    normalized_keyword = _normalize_token(keyword)
    return bool(normalized_keyword and normalized_keyword in normalized_text)


def _normalize_token(value: object) -> str:
    return "".join(str(value or "").split()).upper()


def _is_success_code(code: str) -> bool:
    return code.strip().upper() in SUCCESS_CODES


def _is_service_key_error(code: str, message: str) -> bool:
    normalized_message = message.upper()
    return code.strip() in {"7", "30"} or "SERVICE KEY" in normalized_message or "KEY인증실패" in message


def _find_first(
    items: list[dict[str, str]],
    predicate: Any,
) -> dict[str, str] | None:
    for item in items:
        if predicate(item):
            return item

    return None


def _safe_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None
