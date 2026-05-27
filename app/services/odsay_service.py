from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.services.constants import ODSAY_ROUTE_URL, SUBWAY_LINE_NAMES
from app.services.exceptions import TransportAPIError
from app.services.service_types import RouteSegment, TransportResult
from app.services.settings_helper import get_setting


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


_http_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)


@_http_retry
async def _odsay_fetch(params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(ODSAY_ROUTE_URL, params=params)
        response.raise_for_status()
        return response.json()


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
        "SX": origin_x,
        "SY": origin_y,
        "EX": destination_x,
        "EY": destination_y,
        "apiKey": api_key,
    }

    try:
        payload = await _odsay_fetch(params)

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"ODsay API HTTP 오류가 발생했습니다: {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError("ODsay API 요청 오류가 발생했습니다.") from exc

    if "error" in payload:
        raise TransportAPIError(f"ODsay API 오류: {payload['error']}")

    best_path = _select_best_path(payload=payload, transport_mode=transport_mode)

    if not best_path:
        if transport_mode == "bus":
            raise TransportAPIError(
                "버스가 포함된 경로를 찾지 못했습니다. 다른 출발지나 목적지로 다시 말씀해 주세요."
            )
        raise TransportAPIError("조회 가능한 대중교통 경로를 찾지 못했습니다.")

    return _convert_odsay_path_to_transport_result(
        origin=origin_name,
        destination=destination_text,
        path=best_path,
        transport_mode=transport_mode,
    )


def _select_best_path(
    payload: dict[str, Any],
    transport_mode: str,
) -> dict[str, Any] | None:
    paths = payload.get("result", {}).get("path", [])
    if not paths:
        return None

    valid_paths = [
        p for p in paths
        if _safe_int(p.get("info", {}).get("totalTime")) is not None
    ] or paths

    if transport_mode == "bus":
        bus_paths = [p for p in valid_paths if _path_has_bus(p)]
        if not bus_paths:
            return None
        regular = [p for p in bus_paths if _path_has_regular_bus(p)]
        valid_paths = regular or bus_paths

    elif transport_mode == "subway":
        valid_paths = [p for p in valid_paths if _path_has_subway(p)]

    if not valid_paths:
        return None

    return min(
        valid_paths,
        key=lambda p: _safe_int(p.get("info", {}).get("totalTime")) or 999999,
    )


def _path_has_bus(path: dict[str, Any]) -> bool:
    info = path.get("info", {})
    if _safe_int(info.get("busTransitCount")):
        return True
    return any(sp.get("trafficType") == 2 for sp in path.get("subPath", []))


def _path_has_subway(path: dict[str, Any]) -> bool:
    info = path.get("info", {})
    if _safe_int(info.get("subwayTransitCount")):
        return True
    return any(sp.get("trafficType") == 1 for sp in path.get("subPath", []))


def _path_has_regular_bus(path: dict[str, Any]) -> bool:
    return any(
        not _is_night_bus_number(n)
        for n in _extract_bus_numbers(path.get("subPath", []))
    )


def _convert_odsay_path_to_transport_result(
    origin: str,
    destination: str,
    path: dict[str, Any],
    transport_mode: str,
) -> TransportResult:
    info = path.get("info", {})
    sub_paths = path.get("subPath", [])

    total_time_min = _safe_int(info.get("totalTime"))
    payment = _safe_int(info.get("payment"))
    bus_transit_count = _safe_int(info.get("busTransitCount"))
    subway_transit_count = _safe_int(info.get("subwayTransitCount"))
    path_type = _safe_int(path.get("pathType"))
    transfer_count = _calculate_transfer_count(bus_transit_count, subway_transit_count)
    first_bus_number = _select_display_bus_number(sub_paths)
    route_segments = _extract_route_segments(sub_paths)
    route_summary = _build_route_summary(
        origin=origin,
        destination=destination,
        first_bus_number=first_bus_number,
        total_time_min=total_time_min,
        payment=payment,
        bus_transit_count=bus_transit_count,
        subway_transit_count=subway_transit_count,
    )

    return TransportResult(
        origin=origin,
        destination=destination,
        transport_mode=transport_mode,
        bus_number=first_bus_number,
        arrival_time=None,
        total_time_min=total_time_min,
        payment=payment,
        bus_transit_count=bus_transit_count,
        subway_transit_count=subway_transit_count,
        transfer_count=transfer_count,
        path_type=path_type,
        route_summary=route_summary,
        route_segments=route_segments,
        source="odsay",
    )


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _calculate_transfer_count(
    bus_transit_count: int | None,
    subway_transit_count: int | None,
) -> int | None:
    counts = [c for c in [bus_transit_count, subway_transit_count] if c is not None]
    if not counts:
        return None
    return max(sum(counts) - 1, 0)


def _select_display_bus_number(sub_paths: list[dict[str, Any]]) -> str | None:
    bus_numbers = _extract_bus_numbers(sub_paths)
    for n in bus_numbers:
        if not _is_night_bus_number(n):
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


def _is_night_bus_number(bus_number: str) -> bool:
    return bus_number.strip().upper().startswith("N")


def _extract_route_segments(sub_paths: list[dict[str, Any]]) -> list[RouteSegment] | None:
    segments: list[RouteSegment] = []

    for sp in sub_paths:
        traffic_type = sp.get("trafficType")
        if traffic_type == 3:
            continue

        start_name = sp.get("startName") or ""
        end_name = sp.get("endName") or ""
        lanes = sp.get("lane") or []

        if traffic_type == 2:
            bus_no = str(lanes[0].get("busNo", "")) if lanes else ""
            if bus_no:
                segments.append(RouteSegment(
                    vehicle_type="버스",
                    line=f"{bus_no}번",
                    start_name=start_name,
                    end_name=end_name,
                ))
        elif traffic_type == 1:
            subway_code = int(lanes[0].get("subwayCode", 0)) if lanes else 0
            line_name = SUBWAY_LINE_NAMES.get(subway_code, f"{subway_code}호선")
            segments.append(RouteSegment(
                vehicle_type="지하철",
                line=line_name,
                start_name=start_name,
                end_name=end_name,
            ))

    return segments if segments else None


def _build_route_summary(
    origin: str,
    destination: str,
    first_bus_number: str | None,
    total_time_min: int | None,
    payment: int | None,
    bus_transit_count: int | None,
    subway_transit_count: int | None,
) -> str:
    parts = [f"{origin}에서 {destination}까지 가는 경로를 찾았습니다."]
    if first_bus_number:
        parts.append(f"첫 번째로 이용할 수 있는 버스는 {first_bus_number}번입니다.")
    if total_time_min is not None:
        parts.append(f"예상 소요 시간은 약 {total_time_min}분입니다.")
    if payment is not None:
        parts.append(f"요금은 {payment}원입니다.")
    if bus_transit_count is not None:
        parts.append(f"버스 이용 구간은 {bus_transit_count}개입니다.")
    if subway_transit_count is not None:
        parts.append(f"지하철 이용 구간은 {subway_transit_count}개입니다.")
    return " ".join(parts)
