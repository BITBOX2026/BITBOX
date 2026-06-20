"""
서울시 버스 API 응답 파서

공공데이터 API가 반환하는 JSON/XML 응답에서 필요한 항목을 추출합니다.
API 버전이나 응답 형식에 따라 필드명이 다를 수 있어 여러 후보 이름을 순서대로 시도합니다.
"""

import re
from collections.abc import Callable
from typing import Any
from xml.etree import ElementTree


def extract_items(payload: Any) -> list[dict[str, str]]:
    """서울시 API 응답에서 itemList / StationList 항목을 dict 목록으로 정규화합니다."""
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
    """JSON 구조를 재귀 탐색해 itemList / stationList 배열을 찾습니다."""
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
        return [_stringify_item(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [_stringify_item(value)]
    return []


def _stringify_item(item: dict[str, Any]) -> dict[str, str]:
    """dict/list 중첩값을 제외하고 모든 값을 문자열로 변환합니다."""
    return {
        str(key): "" if value is None else str(value)
        for key, value in item.items()
        if not isinstance(value, (dict, list))
    }


def first_item_value(item: dict[str, str], names: list[str]) -> str | None:
    """항목에서 후보 키 이름 목록 중 첫 번째로 값이 있는 것을 반환합니다. 대소문자 무시."""
    for name in names:
        value = item.get(name)
        if value:
            return value

    # 대소문자 무시 재시도
    lower_item = {key.lower(): value for key, value in item.items()}
    for name in names:
        value = lower_item.get(name.lower())
        if value:
            return value

    return None


def extract_arrival_time(item: dict[str, str]) -> str | None:
    """첫 번째 버스 도착 시간을 반환합니다."""
    first, _ = extract_arrival_times(item)
    return first


def extract_arrival_times(item: dict[str, str]) -> tuple[str | None, str | None]:
    """첫 번째·두 번째 버스 도착 시간을 반환합니다."""
    return (
        _parse_single_arrival(item, "arrmsg1", "traTime1"),
        _parse_single_arrival(item, "arrmsg2", "traTime2"),
    )


def _parse_single_arrival(item: dict[str, str], msg_key: str, time_key: str) -> str | None:
    """특정 arrmsg/traTime 쌍에서 도착 시간 문자열을 추출합니다."""
    message = first_item_value(item, [msg_key])
    if message and message != "출발대기":
        return message
    travel_time = safe_int(first_item_value(item, [time_key]))
    if travel_time is not None and travel_time > 0:
        minutes = max((travel_time + 59) // 60, 1)
        return f"{minutes}분 후"
    return message or None  # "출발대기" 또는 None


def extract_arrival_station_name(item: dict[str, str]) -> str | None:
    """도착정보 응답에서 정류장명 후보를 추출합니다."""
    return first_item_value(item, ["stNm", "stationNm", "stationNm1", "stationNm2"])


def build_route_station(item: dict[str, str]) -> dict[str, str] | None:
    """
    경유 정류소 항목에서 도착정보 조회에 필요한 필드를 추출합니다.
    station_id 또는 order가 없으면 None을 반환합니다.
    """
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
    """노선 항목이 요청한 버스 번호와 정확히 일치하는지 확인합니다."""
    target = normalize_token(bus_number)
    route_names = [
        first_item_value(item, ["busRouteNm"]),
        first_item_value(item, ["busRouteAbrv"]),
    ]
    return any(normalize_token(name) == target for name in route_names)


def contains_normalized(text: str, keyword: str) -> bool:
    """공백/대소문자를 무시하고 keyword가 text에 포함되는지 확인합니다."""
    normalized_text = normalize_token(text)
    normalized_keyword = normalize_token(keyword)
    return bool(normalized_keyword and normalized_keyword in normalized_text)


def equals_normalized(text: str, keyword: str) -> bool:
    """공백/대소문자를 무시하고 두 값이 같은지 확인합니다."""
    normalized_keyword = normalize_token(keyword)
    return bool(normalized_keyword and normalize_token(text) == normalized_keyword)


def normalize_token(value: object) -> str:
    """공백 제거 + 대문자 변환으로 정규화합니다."""
    return "".join(str(value or "").split()).upper()


def find_first(
    items: list[dict[str, str]],
    predicate: Callable[[dict[str, str]], bool],
) -> dict[str, str] | None:
    """조건 함수(predicate)를 만족하는 첫 번째 항목을 반환합니다."""
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


def is_night_bus_number(bus_number: str) -> bool:
    """야간버스 번호는 N으로 시작합니다 (예: N73, N26)."""
    return bus_number.strip().upper().startswith("N")


def parse_first_bus_time(raw: str | None) -> str | None:
    """
    서울버스 API의 firstBusTm 필드를 HH:MM 형식으로 변환합니다.

    API마다 포맷이 다릅니다:
    - "0500"           → HHMM
    - "050000"         → HHMMSS
    - "20240620050000" → YYYYMMDDHHmmSS
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 12:
        hh, mm = digits[8:10], digits[10:12]
    elif len(digits) >= 4:
        hh, mm = digits[0:2], digits[2:4]
    else:
        return None
    if not hh.isdigit() or not mm.isdigit():
        return None
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"
