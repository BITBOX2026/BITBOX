"""Default bus stop arrival lookup service."""

import asyncio
import re
import time
from dataclasses import dataclass

from app.schemas.bus import (
    DefaultBusArrivalItem,
    DefaultBusArrivalResponse,
    SeoulStationArrivalItem,
    SeoulStationArrivalResponse,
    SeoulStationMsgBody,
    SeoulStationMsgHeader,
)
from app.services.core.constants import (
    SEOUL_STATION_ARRIVAL_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.core.exceptions import TransportAPIError
from app.services.core.settings_helper import get_setting
from app.services.transit.seoul_bus_client import request_seoul_bus_payload
from app.services.transit.seoul_bus_parser import (
    contains_normalized,
    equals_normalized,
    extract_items,
    first_item_value,
    safe_int,
)

CACHE_TTL_SECONDS = 15.0
STATION_CACHE_MAX_SIZE = 100
_UNAVAILABLE_ARRIVAL_MARKERS = ("운행종료", "운행 종료", "출발대기", "출발 대기")

_default_cache: tuple[float, DefaultBusArrivalResponse] | None = None
_default_cache_lock = asyncio.Lock()

# arsId별 캐시 및 per-key 락 (서로 다른 정류장 요청이 서로를 블로킹하지 않도록)
_station_cache: dict[str, tuple[float, DefaultBusArrivalResponse]] = {}
_station_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class BusStation:
    name: str
    station_id: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_default_bus_arrivals() -> DefaultBusArrivalResponse:
    cached = _get_default_cached()
    if cached:
        return cached

    async with _default_cache_lock:
        cached = _get_default_cached()
        if cached:
            return cached

        try:
            response = await _fetch_default_bus_arrivals()
        except TransportAPIError as exc:
            return _failure_response(_failure_message(exc))

        _set_default_cached(response)
        return response.model_copy(deep=True)


async def get_bus_arrivals_by_station_id(
    ars_id: str,
    station_name: str | None = None,
) -> DefaultBusArrivalResponse:
    cached = _get_station_cached(ars_id)
    if cached:
        return cached

    # per-key 락: 같은 ars_id 요청만 직렬화, 다른 정류장 요청은 병렬 가능
    async with _station_locks.setdefault(ars_id, asyncio.Lock()):
        cached = _get_station_cached(ars_id)
        if cached:
            return cached

        station = BusStation(name=station_name or ars_id, station_id=ars_id)
        try:
            response = await _fetch_bus_arrivals_for_station(station)
        except TransportAPIError as exc:
            return DefaultBusArrivalResponse(
                success=False,
                station_name=station.name,
                station_id=station.station_id,
                items=[],
                message=_failure_message(exc),
            )

        _set_station_cached(ars_id, response)
        return response.model_copy(deep=True)


async def get_seoul_station_arrival_response(ars_id: str) -> SeoulStationArrivalResponse:
    if not ars_id.strip():
        return _seoul_station_failure_response("arsId is required")

    arrivals = await get_bus_arrivals_by_station_id(ars_id.strip())
    if not arrivals.success:
        return _seoul_station_failure_response(arrivals.message)

    return SeoulStationArrivalResponse(
        comMsgHeader={},
        msgHeader=SeoulStationMsgHeader(
            headerCd="0",
            headerMsg="정상적으로 처리되었습니다.",
        ),
        msgBody=SeoulStationMsgBody(
            itemList=[
                _build_seoul_station_item(item, index)
                for index, item in enumerate(arrivals.items)
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

async def _fetch_default_bus_arrivals() -> DefaultBusArrivalResponse:
    station = await _resolve_default_station()
    return await _fetch_bus_arrivals_for_station(station)


async def _fetch_bus_arrivals_for_station(station: BusStation) -> DefaultBusArrivalResponse:
    payload = await request_seoul_bus_payload(
        SEOUL_STATION_ARRIVAL_URL,
        {"arsId": station.station_id},
        stage="정류장 버스 도착정보 조회",
    )

    raw_items = extract_items(payload)
    arrival_items = [_build_arrival_item(item) for item in raw_items]
    arrival_items = [item for item in arrival_items if item.bus_number]
    arrival_items.sort(
        key=lambda item: (
            item.first_arrival_min is None,
            item.first_arrival_min if item.first_arrival_min is not None else 9999,
            item.bus_number,
        )
    )

    station_name = _extract_station_name(raw_items) or station.name

    return DefaultBusArrivalResponse(
        success=True,
        station_name=station_name,
        station_id=station.station_id,
        items=arrival_items,
        message="버스 도착정보 조회 성공",
    )


async def _resolve_default_station() -> BusStation:
    station_name = _default_station_name()
    station_id = _default_station_id()

    if station_id:
        return BusStation(name=station_name, station_id=station_id)

    payload = await request_seoul_bus_payload(
        SEOUL_STATION_SEARCH_URL,
        {"stSrch": station_name},
        stage="기본 정류장 검색",
    )
    station = _select_best_station(station_name, extract_items(payload))
    if not station:
        raise TransportAPIError(
            f"default station not found: {station_name}",
            user_message=f"{station_name} 정류장을 찾지 못했습니다.",
        )

    return station


# ---------------------------------------------------------------------------
# Station selection
# ---------------------------------------------------------------------------

def _select_best_station(station_name: str, items: list[dict[str, str]]) -> BusStation | None:
    candidates = [c for item in items if (c := _station_from_item(item))]

    if not candidates:
        return None

    for candidate in candidates:
        if equals_normalized(candidate.name, station_name):
            return candidate

    for candidate in candidates:
        if contains_normalized(candidate.name, station_name):
            return candidate

    return candidates[0]


def _station_from_item(item: dict[str, str]) -> BusStation | None:
    name = first_item_value(item, ["stNm", "stationNm", "stationName"]) or ""
    station_id = _first_valid_station_id(item)
    if not station_id:
        return None
    return BusStation(name=name, station_id=station_id)


def _first_valid_station_id(item: dict[str, str]) -> str | None:
    for field_names in (["arsId", "stationNo"], ["stId", "stationId"]):
        station_id = first_item_value(item, field_names)
        if station_id and station_id.strip() not in {"0", "-"}:
            return station_id.strip()
    return None


# ---------------------------------------------------------------------------
# Arrival item builders
# ---------------------------------------------------------------------------

def _build_arrival_item(item: dict[str, str]) -> DefaultBusArrivalItem:
    bus_number = first_item_value(
        item, ["rtNm", "busRouteNm", "busRouteAbrv", "routeNm", "busNumber"],
    ) or ""
    direction = _format_direction(
        first_item_value(item, ["adirection", "direction", "nxtStn", "nextStn"])
    )
    first_arrival_min = _extract_arrival_minutes(item, 1)
    second_arrival_min = _extract_arrival_minutes(item, 2)

    return DefaultBusArrivalItem(
        bus_number=bus_number,
        direction=direction,
        first_arrival_min=first_arrival_min,
        second_arrival_min=second_arrival_min,
        message=_arrival_message(bus_number, first_arrival_min, item),
        # Seoul Open API 원본 값 — 변환 과정에서 손실 없이 프론트로 전달
        raw_arrmsg1=first_item_value(item, ["arrmsg1", "arrMsg1"]) or None,
        raw_arrmsg2=first_item_value(item, ["arrmsg2", "arrMsg2"]) or None,
        raw_congestion1=first_item_value(item, ["congestion1", "congetion1"]) or None,
        raw_congestion2=first_item_value(item, ["congestion2", "congetion2"]) or None,
        raw_is_last1=first_item_value(item, ["isLast1"]) or None,
        raw_is_last2=first_item_value(item, ["isLast2"]) or None,
        raw_bus_type1=first_item_value(item, ["busType1"]) or None,
        raw_bus_type2=first_item_value(item, ["busType2"]) or None,
        raw_is_full_flag1=first_item_value(item, ["isFullFlag1"]) or None,
        raw_is_full_flag2=first_item_value(item, ["isFullFlag2"]) or None,
        raw_station_nm1=first_item_value(item, ["stationNm1"]) or None,
        raw_station_nm2=first_item_value(item, ["stationNm2"]) or None,
        raw_veh_id1=first_item_value(item, ["vehId1", "vehicleId1"]) or None,
        raw_veh_id2=first_item_value(item, ["vehId2", "vehicleId2"]) or None,
    )


def _extract_arrival_minutes(item: dict[str, str], index: int) -> int | None:
    message = first_item_value(item, [f"arrmsg{index}", f"arrMsg{index}"])
    if message and any(marker in message for marker in _UNAVAILABLE_ARRIVAL_MARKERS):
        return None
    if message and "곧" in message:
        return 0

    travel_seconds = safe_int(
        first_item_value(item, [
            f"traTime{index}", f"travelTime{index}",
            f"arrTime{index}", f"arrivalTime{index}",
        ])
    )
    if travel_seconds is not None and travel_seconds > 0:
        return max((travel_seconds + 59) // 60, 1)

    return _minutes_from_message(message)


def _minutes_from_message(message: str | None) -> int | None:
    if not message:
        return None
    if "곧" in message:
        return 0
    m = re.search(r"(\d+)\s*분", message)
    if m:
        return int(m.group(1))
    if re.search(r"(\d+)\s*초", message):
        return 1
    return None


def _format_direction(direction: str | None) -> str:
    if not direction:
        return "방향 정보 없음"
    direction = direction.strip()
    return direction if direction.endswith("방향") else f"{direction} 방향"


def _arrival_message(bus_number: str, first_arrival_min: int | None, item: dict[str, str]) -> str:
    if not bus_number:
        return "버스 도착정보가 있습니다."
    if first_arrival_min is not None:
        return (
            f"{bus_number}번 버스가 곧 도착합니다."
            if first_arrival_min <= 0
            else f"{bus_number}번 버스가 약 {first_arrival_min}분 후 도착합니다."
        )
    arrival_text = first_item_value(item, ["arrmsg1", "arrMsg1"])
    if arrival_text:
        return f"{bus_number}번 버스: {arrival_text}"
    return f"{bus_number}번 버스 도착정보가 없습니다."


# ---------------------------------------------------------------------------
# Seoul station compat builders
# ---------------------------------------------------------------------------

def _build_seoul_station_item(item: DefaultBusArrivalItem, index: int) -> SeoulStationArrivalItem:
    has_second = item.second_arrival_min is not None
    return SeoulStationArrivalItem(
        busRouteId=f"route-{item.bus_number or index}-{index}",
        rtNm=item.bus_number,
        vehId1="1",
        traTime1=str(_minutes_to_seconds(item.first_arrival_min)),
        # 원본값 우선, 없으면 기본값
        busType1=item.raw_bus_type1 or "0",
        isLast1=item.raw_is_last1 or "0",
        isFullFlag1=item.raw_is_full_flag1 or "0",
        congestion1=item.raw_congestion1 or "3",
        arrmsg1=item.raw_arrmsg1 or item.message,
        # 현재 버스 위치 정류소명 우선, 없으면 방향명으로 대체
        stationNm1=item.raw_station_nm1 or item.direction,
        # 2번째 버스: 데이터 없으면 vehId2="0"으로 설정해 프론트가 필터링하도록
        vehId2="2" if has_second else "0",
        traTime2=str(_minutes_to_seconds(item.second_arrival_min)),
        busType2=item.raw_bus_type2 or "0",
        isLast2=item.raw_is_last2 or "0",
        isFullFlag2=item.raw_is_full_flag2 or "0",
        congestion2=item.raw_congestion2 or "3",
        arrmsg2=item.raw_arrmsg2 or _second_arrival_message(item),
        stationNm2=item.raw_station_nm2 or item.direction,
    )


def _minutes_to_seconds(minutes: int | None) -> int:
    if minutes is None:
        return 0     # 데이터 없음 → 0 반환 → 프론트 traTime > 0 필터에 걸려 제외됨
    if minutes <= 0:
        return 30    # 곧 도착: 30초 → 프론트 필터 통과, arrivalMin = 0 → "곧 도착" 표시
    return minutes * 60


def _second_arrival_message(item: DefaultBusArrivalItem) -> str:
    if item.second_arrival_min is None:
        return ""
    return (
        f"{item.bus_number}번 버스가 곧 도착합니다."
        if item.second_arrival_min <= 0
        else f"{item.bus_number}번 버스가 약 {item.second_arrival_min}분 후 도착합니다."
    )


def _seoul_station_failure_response(message: str) -> SeoulStationArrivalResponse:
    return SeoulStationArrivalResponse(
        comMsgHeader={},
        msgHeader=SeoulStationMsgHeader(
            headerCd="1",
            headerMsg=message or "버스 도착정보 조회에 실패했습니다.",
        ),
        msgBody=SeoulStationMsgBody(itemList=[]),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_station_name(items: list[dict[str, str]]) -> str | None:
    for item in items:
        name = first_item_value(item, ["stNm", "stationNm", "stationName"])
        if name:
            return name
    return None


def _default_station_name() -> str:
    value = str(get_setting("DEFAULT_BUS_STOP_NAME", "잠실역") or "").strip()
    return value or "잠실역"


def _default_station_id() -> str | None:
    value = str(get_setting("DEFAULT_BUS_STATION_ID", "") or "").strip()
    return value or None


def _failure_message(exc: TransportAPIError) -> str:
    return exc.user_message if exc.user_message != TransportAPIError.user_message else "버스 도착정보 조회에 실패했습니다."


def _failure_response(message: str) -> DefaultBusArrivalResponse:
    return DefaultBusArrivalResponse(
        success=False,
        station_name=_default_station_name(),
        station_id=_default_station_id(),
        items=[],
        message=message,
    )


# ---------------------------------------------------------------------------
# Cache read / write
# (쓰기: 원본 저장 / 읽기: deep copy 반환 → 호출당 deep copy 1회)
# ---------------------------------------------------------------------------

def _is_stale(cached_at: float) -> bool:
    return time.monotonic() - cached_at > CACHE_TTL_SECONDS


def _get_default_cached() -> DefaultBusArrivalResponse | None:
    if _default_cache is None:
        return None
    cached_at, response = _default_cache
    if _is_stale(cached_at):
        return None
    return response.model_copy(deep=True)


def _set_default_cached(response: DefaultBusArrivalResponse) -> None:
    global _default_cache
    _default_cache = (time.monotonic(), response)


def _get_station_cached(ars_id: str) -> DefaultBusArrivalResponse | None:
    entry = _station_cache.get(ars_id)
    if entry is None:
        return None
    cached_at, response = entry
    if _is_stale(cached_at):
        del _station_cache[ars_id]  # 만료 항목 즉시 삭제
        lock = _station_locks.get(ars_id)
        if lock is not None and not lock.locked():
            _station_locks.pop(ars_id, None)
        return None
    return response.model_copy(deep=True)


def _set_station_cached(ars_id: str, response: DefaultBusArrivalResponse) -> None:
    if ars_id not in _station_cache and len(_station_cache) >= STATION_CACHE_MAX_SIZE:
        oldest_key = min(_station_cache, key=lambda key: _station_cache[key][0])
        _station_cache.pop(oldest_key, None)
        _station_locks.pop(oldest_key, None)
    _station_cache[ars_id] = (time.monotonic(), response)
