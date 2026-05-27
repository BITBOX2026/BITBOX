import asyncio
import time

from app.core.logger import get_logger
from app.services.exceptions import CoordinateResolveError, TransportAPIError
from app.services.kakao_service import resolve_origin, resolve_place_coordinates
from app.services.odsay_service import (
    _calculate_transfer_count,
    _extract_route_segments,
    _is_night_bus_number,
    _safe_int,
    _select_best_path,
    search_odsay_route,
)
from app.services.public_bus_service import search_bus_arrival
from app.services.service_types import ParsedIntent, RouteSegment, TransportResult
from app.services.settings_helper import is_mock_mode

logger = get_logger(__name__)

_route_cache: dict[str, tuple[TransportResult, float]] = {}
_ROUTE_CACHE_TTL = 300      # 5분
_ROUTE_CACHE_MAX_SIZE = 100


async def search_transport_info(parsed: ParsedIntent) -> TransportResult:
    """검증된 intent를 바탕으로 교통 정보를 조회합니다."""

    if is_mock_mode():
        return _mock_transport_result(parsed)

    if parsed.intent == "route":
        return await _search_route_with_odsay(parsed)

    if parsed.intent == "arrival":
        return await search_bus_arrival(parsed)

    raise TransportAPIError("지원하지 않는 교통 요청입니다.")


def _get_cached_route(key: str) -> TransportResult | None:
    entry = _route_cache.get(key)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _ROUTE_CACHE_TTL:
        del _route_cache[key]
        return None
    return result


def _set_cached_route(key: str, result: TransportResult) -> None:
    if len(_route_cache) >= _ROUTE_CACHE_MAX_SIZE:
        oldest_key = min(_route_cache, key=lambda k: _route_cache[k][1])
        del _route_cache[oldest_key]
    _route_cache[key] = (result, time.monotonic())


async def _search_route_with_odsay(parsed: ParsedIntent) -> TransportResult:
    """출발지·목적지 좌표를 확보한 뒤 ODsay 경로를 조회합니다."""

    if not parsed.destination_text:
        raise CoordinateResolveError("목적지가 비어 있습니다.")

    if parsed.origin_text:
        # 출발지·목적지 모두 사용자 입력 → Kakao 호출 병렬화
        (origin_x, origin_y), (destination_x, destination_y) = await asyncio.gather(
            resolve_place_coordinates(parsed.origin_text, "출발지"),
            resolve_place_coordinates(parsed.destination_text, "목적지"),
        )
        origin_name = parsed.origin_text.strip()
    else:
        # 기본 출발지 사용 → 캐시 확인 후 목적지만 조회
        origin_name, origin_x, origin_y = await resolve_origin(None)

        cache_key = f"{origin_name}|{parsed.destination_text.strip()}|{parsed.transport_mode}"
        cached = _get_cached_route(cache_key)
        if cached is not None:
            logger.debug("Route cache hit: %s → %s", origin_name, parsed.destination_text)
            return cached

        destination_x, destination_y = await resolve_place_coordinates(
            parsed.destination_text, "목적지"
        )

    cache_key = f"{origin_name}|{parsed.destination_text.strip()}|{parsed.transport_mode}"
    cached = _get_cached_route(cache_key)
    if cached is not None:
        logger.debug("Route cache hit: %s → %s", origin_name, parsed.destination_text)
        return cached

    result = await search_odsay_route(
        origin_name=origin_name,
        origin_x=origin_x,
        origin_y=origin_y,
        destination_text=parsed.destination_text,
        destination_x=destination_x,
        destination_y=destination_y,
        transport_mode=parsed.transport_mode,
    )
    _set_cached_route(cache_key, result)
    return result


def _mock_transport_result(parsed: ParsedIntent) -> TransportResult:
    """외부 API 없이 전체 파이프라인을 테스트할 mock 교통 결과입니다."""

    if parsed.intent == "route":
        uses_bus = parsed.transport_mode == "bus"
        uses_subway = parsed.transport_mode == "subway"
        origin = parsed.origin_text or "출발지"
        dest = parsed.destination_text or "목적지"

        if uses_bus:
            mock_segments: list[RouteSegment] | None = [
                RouteSegment(vehicle_type="버스", line="146번", start_name=origin, end_name=dest)
            ]
        elif uses_subway:
            mock_segments = [
                RouteSegment(vehicle_type="지하철", line="2호선", start_name=origin, end_name=dest)
            ]
        else:
            mock_segments = [
                RouteSegment(vehicle_type="버스", line="146번", start_name=origin, end_name="환승역"),
                RouteSegment(vehicle_type="지하철", line="2호선", start_name="환승역", end_name=dest),
            ]

        return TransportResult(
            origin=parsed.origin_text,
            destination=parsed.destination_text,
            stop_name=None,
            transport_mode=parsed.transport_mode,
            bus_number="146" if uses_bus else None,
            arrival_time=None,
            total_time_min=24,
            payment=1500,
            bus_transit_count=1 if uses_bus else 0,
            subway_transit_count=1 if uses_subway else 0,
            transfer_count=0,
            path_type=2 if uses_bus else 1 if uses_subway else 3,
            route_summary=f"{parsed.origin_text}에서 {parsed.destination_text}까지 가는 mock 경로입니다.",
            route_segments=mock_segments,
            source="mock",
        )

    if parsed.intent == "arrival":
        return TransportResult(
            origin=None,
            destination=None,
            stop_name=parsed.stop_text,
            transport_mode="bus",
            bus_number=parsed.bus_number,
            arrival_time="3분 후",
            total_time_min=None,
            payment=None,
            bus_transit_count=None,
            subway_transit_count=None,
            transfer_count=None,
            path_type=None,
            route_summary=f"{parsed.bus_number}번 버스가 약 3분 후 도착 예정입니다.",
            source="mock",
        )

    return TransportResult(
        origin=None,
        destination=None,
        stop_name=None,
        transport_mode="unknown",
        bus_number=None,
        arrival_time=None,
        total_time_min=None,
        payment=None,
        bus_transit_count=None,
        subway_transit_count=None,
        transfer_count=None,
        path_type=None,
        route_summary=None,
        source="mock",
    )
