"""
ODsay 버스 경로 검색 클라이언트

출발지/목적지 좌표를 받아 버스 경로를 조회하고
파이프라인 공통 타입인 TransportResult로 변환합니다.

버스만 이용하는 경로 중 야간버스보다 일반버스를 우선합니다.
"""

from typing import Any

import httpx

from app.services.core.constants import ODSAY_ROUTE_URL
from app.services.core.exceptions import TransportAPIError
from app.services.core.http_client import get_http_client
from app.services.core.http_utils import http_retry as _http_retry
from app.services.core.service_types import RouteSegment, TransportResult
from app.services.core.settings_helper import get_setting
from app.services.transit.seoul_bus_parser import is_night_bus_number, safe_int


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@_http_retry
async def _odsay_fetch(params: dict) -> dict:
    """ODsay 경로 검색 API를 호출합니다. 실패 시 자동 재시도합니다."""
    response = await get_http_client().get(ODSAY_ROUTE_URL, params=params)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise TransportAPIError("ODsay API 응답을 파싱하지 못했습니다.") from exc


async def search_odsay_route(
    origin_name: str,
    origin_x: float,
    origin_y: float,
    destination_text: str,
    destination_x: float,
    destination_y: float,
    transport_mode: str,
) -> TransportResult:
    """ODsay API로 경로를 조회하고 TransportResult로 변환합니다."""

    api_key = get_setting("ODSAY_API_KEY")
    if not api_key:
        raise TransportAPIError("ODSAY_API_KEY가 설정되지 않았습니다.")

    params = {
        "SX": origin_x, "SY": origin_y,
        "EX": destination_x, "EY": destination_y,
        "SearchPathType": 2,
        "apiKey": api_key,
    }

    try:
        payload = await _odsay_fetch(params)

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"ODsay API HTTP 오류: {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError("ODsay API 요청 오류가 발생했습니다.") from exc

    if "error" in payload:
        raise TransportAPIError(f"ODsay API 오류: {payload['error']}")

    best_path = _select_best_path(payload=payload)

    if not best_path:
        if transport_mode == "bus":
            raise TransportAPIError(
                user_message="버스가 포함된 경로를 찾지 못했습니다. 다른 출발지나 목적지로 다시 말씀해 주세요."
            )
        raise TransportAPIError(user_message="조회 가능한 버스 경로를 찾지 못했습니다.")

    return _convert_odsay_path_to_transport_result(
        origin=origin_name, origin_x=origin_x, origin_y=origin_y,
        destination=destination_text, destination_x=destination_x, destination_y=destination_y,
        path=best_path, transport_mode=transport_mode,
    )


def _path_time_key(path: dict[str, Any]) -> int:
    t = safe_int(path.get("info", {}).get("totalTime"))
    return t if t is not None else 999999


def _select_best_path(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """버스만 이용하는 경로 중 소요 시간이 가장 짧은 경로를 선택합니다."""
    paths = payload.get("result", {}).get("path", [])
    if not paths:
        return None

    # totalTime이 없는 경로는 제외 (없으면 원본 목록 유지)
    valid_paths = [
        p for p in paths
        if safe_int(p.get("info", {}).get("totalTime")) is not None
    ] or paths

    bus_paths = [
        p for p in valid_paths
        if _path_has_bus(p) and not _path_has_subway(p)
    ]
    if not bus_paths:
        return None
    regular = [p for p in bus_paths if _path_has_regular_bus(p)]
    valid_paths = regular or bus_paths

    if not valid_paths:
        return None

    return min(valid_paths, key=_path_time_key)


def _path_has_bus(path: dict[str, Any]) -> bool:
    info = path.get("info", {})
    count = safe_int(info.get("busTransitCount"))
    if count is not None:
        return count > 0
    return any(sp.get("trafficType") == 2 for sp in path.get("subPath", []))


def _path_has_subway(path: dict[str, Any]) -> bool:
    info = path.get("info", {})
    count = safe_int(info.get("subwayTransitCount"))
    if count is not None:
        return count > 0
    return any(sp.get("trafficType") == 1 for sp in path.get("subPath", []))


def _path_has_regular_bus(path: dict[str, Any]) -> bool:
    """야간버스(N번대)가 아닌 일반 버스가 하나라도 있으면 True를 반환합니다."""
    return any(
        not is_night_bus_number(n)
        for n in _extract_bus_numbers(path.get("subPath", []))
    )


def _convert_odsay_path_to_transport_result(
    origin: str,
    origin_x: float,
    origin_y: float,
    destination: str,
    destination_x: float,
    destination_y: float,
    path: dict[str, Any],
    transport_mode: str,
) -> TransportResult:
    """ODsay 경로 응답을 TransportResult로 변환합니다."""
    info = path.get("info", {})
    sub_paths = path.get("subPath", [])

    total_time_min = safe_int(info.get("totalTime"))
    raw_payment = safe_int(info.get("payment"))
    payment = raw_payment if (raw_payment is not None and raw_payment >= 0) else None
    bus_transit_count = safe_int(info.get("busTransitCount"))
    path_type = safe_int(path.get("pathType"))
    transfer_count = _calculate_transfer_count(bus_transit_count)
    first_bus_number = _select_display_bus_number(sub_paths)
    route_segments = _extract_route_segments(sub_paths)

    return TransportResult(
        origin=origin,
        origin_x=origin_x,
        origin_y=origin_y,
        destination=destination,
        destination_x=destination_x,
        destination_y=destination_y,
        transport_mode=transport_mode,
        bus_number=first_bus_number,
        arrival_time=None,
        total_time_min=total_time_min,
        payment=payment,
        bus_transit_count=bus_transit_count,
        transfer_count=transfer_count,
        path_type=path_type,
        route_summary=None,
        route_segments=route_segments,
        source="odsay",
    )


def _calculate_transfer_count(bus_transit_count: int | None) -> int | None:
    """버스 탑승 횟수에서 1을 빼 환승 횟수를 계산합니다."""
    if bus_transit_count is None:
        return None
    return max(bus_transit_count - 1, 0)


def _select_display_bus_number(sub_paths: list[dict[str, Any]]) -> str | None:
    """일반 버스를 야간버스보다 우선해 대표 버스 번호를 선택합니다."""
    bus_numbers = _extract_bus_numbers(sub_paths)
    for n in bus_numbers:
        if not is_night_bus_number(n):
            return n
    return bus_numbers[0] if bus_numbers else None


def _extract_bus_numbers(sub_paths: list[dict[str, Any]]) -> list[str]:
    numbers: list[str] = []
    for sp in sub_paths:
        if sp.get("trafficType") != 2:
            continue
        for lane in sp.get("lane", []):
            bus_no = lane.get("busNo")
            if bus_no:
                numbers.append(str(bus_no))
    return numbers


def _extract_route_segments(sub_paths: list[dict[str, Any]]) -> list[RouteSegment] | None:
    """
    ODsay subPath 목록에서 버스와 도보 이동 구간을 순서대로 추출합니다.
    """
    segments: list[RouteSegment] = []

    for sp in sub_paths:
        traffic_type = sp.get("trafficType")

        start_name = sp.get("startName") or ""
        end_name = sp.get("endName") or ""
        lanes = sp.get("lane") or []

        seg_time = safe_int(sp.get("time"))
        start_x = _safe_float(sp.get("startX"))
        start_y = _safe_float(sp.get("startY"))
        end_x = _safe_float(sp.get("endX"))
        end_y = _safe_float(sp.get("endY"))

        if traffic_type == 3:  # 도보
            distance = safe_int(sp.get("distance"))
            description = f"도보 {distance}m" if distance is not None else "도보 이동"
            segments.append(RouteSegment(
                vehicle_type="도보",
                line=description,
                start_name=start_name,
                end_name=end_name,
                time_min=seg_time,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                path_points=_extract_path_points(
                    sp,
                    start_x=start_x,
                    start_y=start_y,
                    end_x=end_x,
                    end_y=end_y,
                ),
            ))
            continue

        if traffic_type == 2:  # 버스
            bus_no = str(lanes[0].get("busNo", "")) if lanes else ""
            if bus_no:
                segments.append(RouteSegment(
                    vehicle_type="버스",
                    line=f"{bus_no}번",
                    start_name=start_name,
                    end_name=end_name,
                    time_min=seg_time,
                    start_x=start_x,
                    start_y=start_y,
                    end_x=end_x,
                    end_y=end_y,
                    path_points=_extract_path_points(
                        sp,
                        start_x=start_x,
                        start_y=start_y,
                        end_x=end_x,
                        end_y=end_y,
                    ),
                ))

    return segments if segments else None


def _extract_path_points(
    sub_path: dict[str, Any],
    *,
    start_x: float | None,
    start_y: float | None,
    end_x: float | None,
    end_y: float | None,
) -> list[dict[str, float]] | None:
    """경유 정류장 좌표를 지도 폴리라인용 순서로 정리합니다."""
    points: list[dict[str, float]] = []

    def append_point(x_value: object, y_value: object) -> None:
        x = _safe_float(x_value)
        y = _safe_float(y_value)
        if x is None or y is None:
            return
        point = {"x": x, "y": y}
        if not points or points[-1] != point:
            points.append(point)

    append_point(start_x, start_y)
    stations = (sub_path.get("passStopList") or {}).get("stations") or []
    for station in stations:
        append_point(station.get("x"), station.get("y"))
    append_point(end_x, end_y)

    return points if len(points) >= 2 else None
