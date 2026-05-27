from typing import Any
from xml.etree import ElementTree


def extract_items(payload: Any) -> list[dict[str, str]]:
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


def first_item_value(item: dict[str, str], names: list[str]) -> str | None:
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


def extract_arrival_time(item: dict[str, str]) -> str | None:
    """서울시 도착 응답에서 사용자에게 보여줄 도착 시간을 추출합니다."""

    first_message = first_item_value(item, ["arrmsg1"])

    for message_key, time_key in [
        ("arrmsg1", "traTime1"),
        ("arrmsg2", "traTime2"),
    ]:
        arrival_message = first_item_value(item, [message_key])
        if arrival_message and arrival_message != "출발대기":
            return arrival_message

        travel_time = safe_int(first_item_value(item, [time_key]))
        if travel_time is not None and travel_time > 0:
            minutes = max((travel_time + 59) // 60, 1)
            return f"{minutes}분 후"

    return first_message


def extract_arrival_station_name(item: dict[str, str]) -> str | None:
    """도착정보 응답에서 정류장명 후보를 추출합니다."""

    return first_item_value(
        item,
        ["stNm", "stationNm", "stationNm1", "stationNm2"],
    )


def build_route_station(item: dict[str, str]) -> dict[str, str] | None:
    station_id = first_item_value(item, ["station", "stId", "stationId"])
    order = first_item_value(item, ["seq", "staOrd", "ord"])
    station_name = first_item_value(item, ["stationNm", "stNm"]) or ""
    ars_id = first_item_value(item, ["arsId", "stationNo"]) or ""

    if not station_id or not order:
        return None

    return {
        "station_id": station_id,
        "order": order,
        "station_name": station_name,
        "ars_id": ars_id,
    }


def is_matching_bus_route(item: dict[str, str], bus_number: str) -> bool:
    target = normalize_token(bus_number)
    route_names = [
        first_item_value(item, ["busRouteNm"]),
        first_item_value(item, ["busRouteAbrv"]),
    ]

    return any(normalize_token(route_name) == target for route_name in route_names)


def contains_normalized(text: str, keyword: str) -> bool:
    normalized_text = normalize_token(text)
    normalized_keyword = normalize_token(keyword)
    return bool(normalized_keyword and normalized_keyword in normalized_text)


def normalize_token(value: object) -> str:
    return "".join(str(value or "").split()).upper()


def find_first(
    items: list[dict[str, str]],
    predicate: Any,
) -> dict[str, str] | None:
    for item in items:
        if predicate(item):
            return item

    return None


def safe_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None
