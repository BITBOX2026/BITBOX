"""
교통 정보 조회 오케스트레이터

ParsedIntent를 받아 적절한 교통 API를 선택하고 TransportResult를 반환합니다.

intent별 처리:
- route   → ODsay 경로 검색 (Kakao 좌표 변환 → ODsay 경로 조회)
- arrival → 서울버스 공공데이터 실시간 도착 조회

성능 최적화:
- 경로 결과를 5분 TTL, 최대 100개 메모리 캐시에 저장합니다.
- 캐시 키 확인은 Kakao API 호출보다 먼저 수행합니다.
"""

import asyncio
import time

from app.core.logger import get_logger
from app.services.core.exceptions import CoordinateResolveError, TransportAPIError
from app.services.core.service_types import ParsedIntent, RouteSegment, TransportResult
from app.services.core.settings_helper import is_mock_mode
from app.services.transit.kakao_service import resolve_origin, resolve_place_coordinates
from app.services.transit.odsay_service import search_odsay_route
from app.services.transit.public_bus_service import search_bus_arrival

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 경로 캐시 설정
# 동일한 출발지→목적지 경로를 반복 조회할 때 외부 API 호출을 줄입니다.
# per-key lock으로 같은 경로를 동시에 요청할 때 캐시 스탬피드를 방지합니다.
# ---------------------------------------------------------------------------
_route_cache: dict[str, tuple[TransportResult, float]] = {}
_route_cache_locks: dict[str, asyncio.Lock] = {}
_ROUTE_CACHE_TTL = 300       # 캐시 유효 시간: 5분 (초)
_ROUTE_CACHE_MAX_SIZE = 100  # 최대 캐시 항목 수 — 초과 시 가장 오래된 항목 제거


async def search_transport_info(parsed: ParsedIntent) -> TransportResult:
    """검증된 intent를 바탕으로 교통 정보를 조회합니다."""

    if is_mock_mode():
        return _mock_transport_result(parsed)

    if parsed.intent == "route":
        return await _search_route_with_odsay(parsed)

    if parsed.intent == "arrival":
        return await search_bus_arrival(parsed)

    raise TransportAPIError(user_message="지원하지 않는 교통 요청입니다.")


# ---------------------------------------------------------------------------
# 캐시 내부 함수
# ---------------------------------------------------------------------------

def _make_cache_key(origin_name: str, destination_text: str, transport_mode: str) -> str:
    return f"{origin_name}|{destination_text.strip()}|{transport_mode}"


def _get_cached_route(key: str) -> TransportResult | None:
    entry = _route_cache.get(key)
    if entry is None:
        return None
    result, ts = entry
    # TTL 만료 시 캐시에서 제거
    if time.monotonic() - ts > _ROUTE_CACHE_TTL:
        del _route_cache[key]
        return None
    return result


def _set_cached_route(key: str, result: TransportResult) -> None:
    # 최대 크기 초과 시 가장 오래된(타임스탬프가 가장 작은) 항목을 제거
    if len(_route_cache) >= _ROUTE_CACHE_MAX_SIZE:
        oldest_key = min(_route_cache, key=lambda k: _route_cache[k][1])
        del _route_cache[oldest_key]
    _route_cache[key] = (result, time.monotonic())


# ---------------------------------------------------------------------------
# 경로 검색 (ODsay)
# ---------------------------------------------------------------------------

async def _search_route_with_odsay(parsed: ParsedIntent) -> TransportResult:
    """출발지·목적지 좌표를 확보한 뒤 ODsay 경로를 조회합니다."""

    if not parsed.destination_text:
        raise CoordinateResolveError("목적지가 비어 있습니다.")

    # 기본 출발지는 내부적으로 캐싱됨 — lock 밖에서 먼저 resolve
    if parsed.origin_text:
        origin_name = parsed.origin_text.strip()
        origin_coords: tuple[float, float] | None = None
    else:
        origin_name, ox, oy = await resolve_origin(None)
        origin_coords = (ox, oy)

    cache_key = _make_cache_key(origin_name, parsed.destination_text, parsed.transport_mode)

    # 1차 캐시 확인 (lock 없이)
    cached = _get_cached_route(cache_key)
    if cached is not None:
        logger.debug("경로 캐시 히트: %s → %s", origin_name, parsed.destination_text)
        return cached

    # 캐시 미스 — per-key lock으로 동일 경로 요청 직렬화 (캐시 스탬피드 방지)
    async with _route_cache_locks.setdefault(cache_key, asyncio.Lock()):
        cached = _get_cached_route(cache_key)
        if cached is not None:
            return cached

        if origin_coords is None:
            # 출발지·목적지 좌표를 병렬 조회
            (origin_x, origin_y), (destination_x, destination_y) = await asyncio.gather(
                resolve_place_coordinates(origin_name, "출발지"),
                resolve_place_coordinates(parsed.destination_text, "목적지"),
            )
        else:
            origin_x, origin_y = origin_coords
            destination_x, destination_y = await resolve_place_coordinates(
                parsed.destination_text, "목적지"
            )

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


# ---------------------------------------------------------------------------
# Mock 데이터 (외부 API 없이 전체 파이프라인 테스트용)
# ---------------------------------------------------------------------------

def _mock_transport_result(parsed: ParsedIntent) -> TransportResult:
    if parsed.intent == "route":
        origin = parsed.origin_text or "출발지"
        dest = parsed.destination_text or "목적지"
        uses_bus = parsed.transport_mode == "bus"
        uses_subway = parsed.transport_mode == "subway"

        # 교통수단에 따라 mock 경로 구간 생성
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
            origin=origin, destination=dest,
            stop_name=None, transport_mode=parsed.transport_mode,
            bus_number="146" if uses_bus else None,
            arrival_time=None, total_time_min=24, payment=1500,
            bus_transit_count=1 if uses_bus else 0,
            subway_transit_count=1 if uses_subway else 0,
            transfer_count=0,
            path_type=2 if uses_bus else 1 if uses_subway else 3,
            route_summary=f"{origin}에서 {dest}까지 가는 mock 경로입니다.",
            route_segments=mock_segments,
            source="mock",
        )

    if parsed.intent == "arrival":
        return TransportResult(
            stop_name=parsed.stop_text, transport_mode="bus",
            bus_number=parsed.bus_number, arrival_time="3분 후",
            route_summary=f"{parsed.bus_number}번 버스가 약 3분 후 도착 예정입니다.",
            source="mock",
        )

    return TransportResult(source="mock")
