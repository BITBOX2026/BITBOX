from typing import Any

import httpx

from app.services.constants import (
    KAKAO_KEYWORD_SEARCH_URL,
    KNOWN_PLACE_COORDS,
    KOREA_LATITUDE_MAX,
    KOREA_LATITUDE_MIN,
    KOREA_LONGITUDE_MAX,
    KOREA_LONGITUDE_MIN,
    ODSAY_ROUTE_URL,
)
from app.services.exceptions import CoordinateResolveError, TransportAPIError
from app.services.public_bus_service import search_bus_arrival
from app.services.service_types import ParsedIntent, TransportResult
from app.services.settings_helper import get_setting, is_mock_mode


async def search_transport_info(parsed: ParsedIntent) -> TransportResult:
    """검증된 intent를 바탕으로 교통 정보를 조회합니다."""

    if is_mock_mode():
        return _mock_transport_result(parsed)

    if parsed.intent == "route":
        return await _search_route_with_odsay(parsed)

    if parsed.intent == "arrival":
        return await search_bus_arrival(parsed)

    raise TransportAPIError("지원하지 않는 교통 요청입니다.")


async def _search_route_with_odsay(parsed: ParsedIntent) -> TransportResult:
    """출발지와 목적지를 좌표로 바꾼 뒤 ODsay 경로를 조회합니다."""

    api_key = get_setting("ODSAY_API_KEY")
    if not api_key:
        raise TransportAPIError("ODSAY_API_KEY가 설정되지 않았습니다.")

    if not parsed.destination_text:
        raise CoordinateResolveError("목적지가 비어 있습니다.")

    origin_name, origin_x, origin_y = await _resolve_origin(parsed.origin_text)
    destination_x, destination_y = await _resolve_place_coordinates(
        place_text=parsed.destination_text,
        label="목적지",
    )

    params = {
        "SX": origin_x,
        "SY": origin_y,
        "EX": destination_x,
        "EY": destination_y,
        "apiKey": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(ODSAY_ROUTE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"ODsay API HTTP 오류가 발생했습니다: {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError("ODsay API 요청 오류가 발생했습니다.") from exc

    except ValueError as exc:
        raise TransportAPIError("ODsay API 응답을 JSON으로 해석하지 못했습니다.") from exc

    if "error" in payload:
        raise TransportAPIError(f"ODsay API 오류: {payload['error']}")

    best_path = _select_best_path(
        payload=payload,
        transport_mode=parsed.transport_mode,
    )

    if not best_path:
        if parsed.transport_mode == "bus":
            # Fallback policy: 사용자가 버스를 명시한 경우 지하철 전용 경로로
            # 자동 전환하지 않습니다. 안내 문장을 만들 때 없는 버스 정보를
            # 생성하지 않기 위해 명확한 재요청 메시지로 종료합니다.
            raise TransportAPIError(
                "버스가 포함된 경로를 찾지 못했습니다. 다른 출발지나 목적지로 다시 말씀해 주세요."
            )

        raise TransportAPIError("조회 가능한 대중교통 경로를 찾지 못했습니다.")

    return _convert_odsay_path_to_transport_result(
        origin=origin_name,
        destination=parsed.destination_text,
        path=best_path,
        transport_mode=parsed.transport_mode,
    )


async def _resolve_origin(origin_text: str | None) -> tuple[str, float, float]:
    """
    출발지를 좌표로 변환합니다.

    현재 검증 단계에서는 origin_text가 필수입니다.
    다만 나중에 고정 좌표 fallback을 쓸 수 있도록 DEFAULT_ORIGIN_X/Y 경로를 남겨둡니다.
    """

    if origin_text:
        origin_x, origin_y = await _resolve_place_coordinates(
            place_text=origin_text,
            label="출발지",
        )
        return origin_text, origin_x, origin_y

    origin_x, origin_y = _get_origin_coordinates_fallback()
    return "현재 위치", origin_x, origin_y


def _get_origin_coordinates_fallback() -> tuple[float, float]:
    """DEFAULT_ORIGIN_X/Y 환경변수를 fallback 출발지 좌표로 읽습니다."""

    origin_x = get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X")
    origin_y = get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y")

    if origin_x is None or origin_y is None:
        raise CoordinateResolveError("출발지를 말씀해 주세요.")

    try:
        longitude = float(origin_x)
        latitude = float(origin_y)

    except ValueError as exc:
        raise TransportAPIError("DEFAULT_ORIGIN_X, DEFAULT_ORIGIN_Y는 숫자여야 합니다.") from exc

    _validate_korea_coordinates(
        longitude=longitude,
        latitude=latitude,
        label="출발지",
    )

    return longitude, latitude


async def _resolve_place_coordinates(
    place_text: str,
    label: str,
) -> tuple[float, float]:
    """
    장소명을 Kakao Local API로 좌표 변환합니다.

    Kakao에서 결과가 없을 때만 개발용 알려진 좌표 목록을 보조로 사용합니다.
    """

    normalized = place_text.strip()
    if not normalized:
        raise CoordinateResolveError(f"{label}가 비어 있습니다.")

    try:
        return await _resolve_place_coordinates_via_kakao(
            place_text=normalized,
            label=label,
        )

    except CoordinateResolveError:
        if normalized not in KNOWN_PLACE_COORDS:
            raise

    longitude, latitude = KNOWN_PLACE_COORDS[normalized]

    _validate_korea_coordinates(
        longitude=longitude,
        latitude=latitude,
        label=label,
    )

    return longitude, latitude


async def _resolve_place_coordinates_via_kakao(
    place_text: str,
    label: str,
) -> tuple[float, float]:
    """Kakao Local API 키워드 검색 결과의 첫 번째 장소 좌표를 반환합니다."""

    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key:
        raise TransportAPIError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    headers = {
        "Authorization": f"KakaoAK {kakao_key}",
    }

    params = {
        "query": place_text,
        "size": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                KAKAO_KEYWORD_SEARCH_URL,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"Kakao Local API HTTP 오류가 발생했습니다: {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError("Kakao Local API 요청 오류가 발생했습니다.") from exc

    except ValueError as exc:
        raise TransportAPIError("Kakao Local API 응답을 JSON으로 해석하지 못했습니다.") from exc

    documents = payload.get("documents", [])

    if not documents:
        raise CoordinateResolveError(f"'{place_text}' 검색 결과가 없습니다.")

    first_place = documents[0]

    try:
        longitude = float(first_place["x"])
        latitude = float(first_place["y"])

    except (KeyError, TypeError, ValueError) as exc:
        raise CoordinateResolveError(
            "Kakao Local API 응답에서 좌표를 찾지 못했습니다."
        ) from exc

    _validate_korea_coordinates(
        longitude=longitude,
        latitude=latitude,
        label=label,
    )

    return longitude, latitude


def _validate_korea_coordinates(
    longitude: float,
    latitude: float,
    label: str,
) -> None:
    """ODsay에 전달할 좌표가 대한민국 서비스 범위에 있는지 확인합니다."""

    is_valid_longitude = KOREA_LONGITUDE_MIN <= longitude <= KOREA_LONGITUDE_MAX
    is_valid_latitude = KOREA_LATITUDE_MIN <= latitude <= KOREA_LATITUDE_MAX

    if not is_valid_longitude or not is_valid_latitude:
        raise CoordinateResolveError(
            f"{label} 좌표가 대한민국 서비스 범위를 벗어났습니다. "
            f"입력값: longitude={longitude}, latitude={latitude}"
        )


def _select_best_path(
    payload: dict[str, Any],
    transport_mode: str,
) -> dict[str, Any] | None:
    """ODsay 응답에서 요청한 교통수단에 맞는 최단 경로를 선택합니다."""

    paths = payload.get("result", {}).get("path", [])

    if not paths:
        return None

    valid_paths = [
        path
        for path in paths
        if _safe_int(path.get("info", {}).get("totalTime")) is not None
    ]

    if not valid_paths:
        valid_paths = paths

    if transport_mode == "bus":
        bus_paths = [path for path in valid_paths if _path_has_bus(path)]
        if not bus_paths:
            return None

        regular_bus_paths = [
            path
            for path in bus_paths
            if _path_has_regular_bus(path)
        ]
        valid_paths = regular_bus_paths or bus_paths

    elif transport_mode == "subway":
        valid_paths = [path for path in valid_paths if _path_has_subway(path)]

    if not valid_paths:
        return None

    return min(
        valid_paths,
        key=lambda path: _safe_int(path.get("info", {}).get("totalTime")) or 999999,
    )


def _path_has_bus(path: dict[str, Any]) -> bool:
    """ODsay path에 버스 구간이 포함되어 있는지 확인합니다."""

    info = path.get("info", {})
    bus_transit_count = _safe_int(info.get("busTransitCount"))

    if bus_transit_count and bus_transit_count > 0:
        return True

    return any(
        sub_path.get("trafficType") == 2
        for sub_path in path.get("subPath", [])
    )


def _path_has_subway(path: dict[str, Any]) -> bool:
    """ODsay path에 지하철 구간이 포함되어 있는지 확인합니다."""

    info = path.get("info", {})
    subway_transit_count = _safe_int(info.get("subwayTransitCount"))

    if subway_transit_count and subway_transit_count > 0:
        return True

    return any(
        sub_path.get("trafficType") == 1
        for sub_path in path.get("subPath", [])
    )


def _path_has_regular_bus(path: dict[str, Any]) -> bool:
    """야간버스가 아닌 일반 버스 번호가 path에 포함되어 있는지 확인합니다."""

    return any(
        not _is_night_bus_number(bus_number)
        for bus_number in _extract_bus_numbers(path.get("subPath", []))
    )


def _convert_odsay_path_to_transport_result(
    origin: str,
    destination: str,
    path: dict[str, Any],
    transport_mode: str,
) -> TransportResult:
    """ODsay 단일 경로 응답을 TransportResult로 변환합니다."""

    info = path.get("info", {})
    sub_paths = path.get("subPath", [])

    total_time_min = _safe_int(info.get("totalTime"))
    payment = _safe_int(info.get("payment"))
    bus_transit_count = _safe_int(info.get("busTransitCount"))
    subway_transit_count = _safe_int(info.get("subwayTransitCount"))
    path_type = _safe_int(path.get("pathType"))
    transfer_count = _calculate_transfer_count(
        bus_transit_count=bus_transit_count,
        subway_transit_count=subway_transit_count,
    )
    first_bus_number = _select_display_bus_number(sub_paths)

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
        source="odsay",
    )


def _safe_int(value: object) -> int | None:
    """ODsay 숫자 필드를 int 또는 None으로 정규화합니다."""

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
    """탑승 구간 수로부터 실제 환승 횟수를 보수적으로 계산합니다."""

    counts = [
        count
        for count in [bus_transit_count, subway_transit_count]
        if count is not None
    ]

    if not counts:
        return None

    boarding_count = sum(counts)
    return max(boarding_count - 1, 0)


def _select_display_bus_number(sub_paths: list[dict[str, Any]]) -> str | None:
    """안내에 표시할 버스 번호를 선택합니다. 일반 버스를 야간버스보다 우선합니다."""

    bus_numbers = _extract_bus_numbers(sub_paths)

    for bus_number in bus_numbers:
        if not _is_night_bus_number(bus_number):
            return bus_number

    return bus_numbers[0] if bus_numbers else None


def _extract_bus_numbers(sub_paths: list[dict[str, Any]]) -> list[str]:
    """ODsay subPath에서 버스 번호 후보를 순서대로 추출합니다."""

    bus_numbers: list[str] = []

    for sub_path in sub_paths:
        if sub_path.get("trafficType") != 2:
            continue

        lanes = sub_path.get("lane", [])

        for lane in lanes:
            bus_number = lane.get("busNo")

            if bus_number:
                bus_numbers.append(str(bus_number))

    return bus_numbers


def _is_night_bus_number(bus_number: str) -> bool:
    """서울 N75처럼 N으로 시작하는 야간버스 번호인지 확인합니다."""

    return bus_number.strip().upper().startswith("N")


def _build_route_summary(
    origin: str,
    destination: str,
    first_bus_number: str | None,
    total_time_min: int | None,
    payment: int | None,
    bus_transit_count: int | None,
    subway_transit_count: int | None,
) -> str:
    """교통 조회 결과를 내부 로그/디버깅용 요약 문장으로 만듭니다."""

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


def _mock_transport_result(parsed: ParsedIntent) -> TransportResult:
    """외부 API 없이 전체 파이프라인을 테스트할 mock 교통 결과입니다."""

    if parsed.intent == "route":
        uses_bus = parsed.transport_mode == "bus"
        uses_subway = parsed.transport_mode == "subway"

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
            route_summary=(
                f"{parsed.origin_text}에서 {parsed.destination_text}까지 가는 "
                "mock 경로입니다."
            ),
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
