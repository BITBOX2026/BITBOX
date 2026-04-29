# ODsay와 Kakao Local API를 이용해 교통 정보를 조회하는 서비스 파일입니다.

from typing import Any

import httpx

from app.services.constants import (
    KAKAO_KEYWORD_SEARCH_URL,
    KNOWN_DESTINATION_COORDS,
    KOREA_LATITUDE_MAX,
    KOREA_LATITUDE_MIN,
    KOREA_LONGITUDE_MAX,
    KOREA_LONGITUDE_MIN,
    ODSAY_ROUTE_URL,
)
from app.services.exceptions import CoordinateResolveError, TransportAPIError
from app.services.service_types import ParsedIntent, TransportResult
from app.services.settings_helper import get_setting, is_mock_mode


async def search_transport_info(parsed: ParsedIntent) -> TransportResult:
    """
    검증된 사용자 요청을 바탕으로 교통 정보를 조회하는 함수입니다.

    기능:
        - mock 모드에서는 테스트용 교통 정보를 반환합니다.
        - 실제 모드에서 route 요청이면 ODsay 길찾기 API를 호출합니다.
        - 실제 모드에서 arrival 요청은 아직 공공데이터 API 연동 전이므로 에러 처리합니다.

    입력:
        parsed:
            - 검증된 LLM 분석 결과입니다.

    반환:
        TransportResult:
            - 교통 API 조회 결과입니다.
    """

    if is_mock_mode():
        return _mock_transport_result(parsed)

    if parsed.intent == "route":
        return await _search_route_with_odsay(parsed)

    if parsed.intent == "arrival":
        raise TransportAPIError(
            "실시간 버스 도착 정보는 공공데이터 API 연동 후 구현해야 합니다."
        )

    raise TransportAPIError("지원하지 않는 교통 요청입니다.")


async def _search_route_with_odsay(parsed: ParsedIntent) -> TransportResult:
    """
    ODsay 대중교통 길찾기 API로 출발지에서 목적지까지의 경로를 조회하는 함수입니다.

    기능:
        - 출발지 좌표와 목적지 좌표를 이용해 ODsay API를 호출합니다.
        - ODsay 응답에서 가장 짧은 소요 시간의 경로를 선택합니다.
        - 선택된 경로를 TransportResult 형태로 변환합니다.

    필요한 환경변수:
        ODSAY_API_KEY:
            - ODsay Server API Key입니다.

        ORIGIN_X:
            - 출발지 경도입니다.

        ORIGIN_Y:
            - 출발지 위도입니다.

    입력:
        parsed:
            - destination_text가 포함된 분석 결과입니다.

    반환:
        TransportResult:
            - ODsay 조회 결과를 정리한 데이터입니다.
    """

    api_key = get_setting("ODSAY_API_KEY")
    if not api_key:
        raise TransportAPIError("ODSAY_API_KEY가 설정되지 않았습니다.")

    origin_x, origin_y = _get_origin_coordinates()

    if not parsed.destination_text:
        raise CoordinateResolveError("목적지가 비어 있습니다.")

    destination_x, destination_y = await _resolve_destination_coordinates(
        parsed.destination_text
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
        raise TransportAPIError(f"ODsay API 요청 오류가 발생했습니다: {exc}") from exc

    except ValueError as exc:
        raise TransportAPIError("ODsay API 응답을 JSON으로 해석하지 못했습니다.") from exc

    if "error" in payload:
        raise TransportAPIError(f"ODsay API 오류: {payload['error']}")

    best_path = _select_best_path(payload)

    if not best_path:
        return TransportResult(
            destination=parsed.destination_text,
            bus_number=None,
            arrival_time=None,
            total_time_min=None,
            transfer_count=None,
            route_summary="조회 가능한 대중교통 경로를 찾지 못했습니다.",
            source="odsay",
        )

    return _convert_odsay_path_to_transport_result(
        destination=parsed.destination_text,
        path=best_path,
    )


def _get_origin_coordinates() -> tuple[float, float]:
    """
    환경변수에서 출발지 좌표를 읽어오는 함수입니다.

    기능:
        - ORIGIN_X, ORIGIN_Y 값을 읽어 float로 변환합니다.
        - 좌표가 대한민국 대략 범위를 벗어나면 예외를 발생시킵니다.
        - ODsay API에 잘못된 좌표가 전달되는 것을 사전에 방지합니다.

    반환:
        tuple[float, float]:
            - (출발지 경도, 출발지 위도)
    """

    origin_x = get_setting("ORIGIN_X")
    origin_y = get_setting("ORIGIN_Y")

    if origin_x is None or origin_y is None:
        raise TransportAPIError("ORIGIN_X, ORIGIN_Y 출발지 좌표가 설정되지 않았습니다.")

    try:
        longitude = float(origin_x)
        latitude = float(origin_y)

    except ValueError as exc:
        raise TransportAPIError("ORIGIN_X, ORIGIN_Y는 숫자여야 합니다.") from exc

    _validate_korea_coordinates(
        longitude=longitude,
        latitude=latitude,
        label="출발지",
    )

    return longitude, latitude


async def _resolve_destination_coordinates(destination_text: str) -> tuple[float, float]:
    """
    목적지명을 경도, 위도 좌표로 변환하는 함수입니다.

    기능:
        - 먼저 하드코딩된 개발용 좌표 목록에서 찾습니다.
        - 없으면 Kakao Local API로 장소 키워드 검색을 수행합니다.
        - 변환된 좌표는 대한민국 서비스 범위 안에 있는지 검증합니다.

    입력:
        destination_text:
            - 사용자가 말한 목적지명입니다.

    반환:
        tuple[float, float]:
            - (목적지 경도, 목적지 위도)
    """

    normalized = destination_text.strip()

    if normalized in KNOWN_DESTINATION_COORDS:
        longitude, latitude = KNOWN_DESTINATION_COORDS[normalized]

        _validate_korea_coordinates(
            longitude=longitude,
            latitude=latitude,
            label="목적지",
        )

        return longitude, latitude

    return await _resolve_destination_coordinates_via_kakao(normalized)


async def _resolve_destination_coordinates_via_kakao(
    destination_text: str,
) -> tuple[float, float]:
    """
    Kakao Local API를 이용해 목적지명을 좌표로 변환하는 함수입니다.

    기능:
        - 목적지명을 키워드로 검색합니다.
        - 검색 결과 중 첫 번째 장소의 x, y 값을 사용합니다.
        - Kakao 응답에서 x는 경도, y는 위도입니다.

    필요한 환경변수:
        KAKAO_REST_API_KEY:
            - Kakao Developers에서 발급받은 REST API 키입니다.

    입력:
        destination_text:
            - 검색할 장소명입니다.

    반환:
        tuple[float, float]:
            - (경도, 위도)
    """

    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key:
        raise TransportAPIError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    headers = {
        "Authorization": f"KakaoAK {kakao_key}",
    }

    params = {
        "query": destination_text,
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
        raise TransportAPIError(f"Kakao Local API 요청 오류가 발생했습니다: {exc}") from exc

    except ValueError as exc:
        raise TransportAPIError("Kakao Local API 응답을 JSON으로 해석하지 못했습니다.") from exc

    documents = payload.get("documents", [])

    if not documents:
        raise CoordinateResolveError(f"'{destination_text}' 검색 결과가 없습니다.")

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
        label="목적지",
    )

    return longitude, latitude


def _validate_korea_coordinates(
    longitude: float,
    latitude: float,
    label: str,
) -> None:
    """
    좌표가 대한민국 대략 범위 안에 있는지 검증하는 함수입니다.

    기능:
        - 경도, 위도가 한국 서비스 범위를 벗어나면 예외를 발생시킵니다.
        - 예: 0, 0 같은 잘못된 좌표를 사전에 차단합니다.

    입력:
        longitude:
            - 경도 값입니다. ODsay 기준 X에 해당합니다.

        latitude:
            - 위도 값입니다. ODsay 기준 Y에 해당합니다.

        label:
            - 에러 메시지에 표시할 좌표 이름입니다.
            - 예: "출발지", "목적지"

    반환:
        None:
            - 정상 좌표면 아무것도 반환하지 않습니다.
    """

    is_valid_longitude = KOREA_LONGITUDE_MIN <= longitude <= KOREA_LONGITUDE_MAX
    is_valid_latitude = KOREA_LATITUDE_MIN <= latitude <= KOREA_LATITUDE_MAX

    if not is_valid_longitude or not is_valid_latitude:
        raise CoordinateResolveError(
            f"{label} 좌표가 대한민국 서비스 범위를 벗어났습니다. "
            f"입력값: longitude={longitude}, latitude={latitude}"
        )


def _select_best_path(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    ODsay 응답에서 가장 적절한 경로 하나를 선택하는 함수입니다.

    기능:
        - result.path 목록을 가져옵니다.
        - totalTime이 있는 경로 중 가장 짧은 경로를 선택합니다.
        - 경로가 없으면 None을 반환합니다.

    입력:
        payload:
            - ODsay API 전체 응답 JSON입니다.

    반환:
        dict | None:
            - 선택된 경로 데이터입니다.
    """

    paths = payload.get("result", {}).get("path", [])

    if not paths:
        return None

    valid_paths = [
        path
        for path in paths
        if isinstance(path.get("info", {}).get("totalTime"), int)
    ]

    if not valid_paths:
        return paths[0]

    return min(
        valid_paths,
        key=lambda path: path.get("info", {}).get("totalTime", 999999),
    )


def _convert_odsay_path_to_transport_result(
    destination: str,
    path: dict[str, Any],
) -> TransportResult:
    """
    ODsay 경로 응답을 TransportResult 구조로 변환하는 함수입니다.

    기능:
        - ODsay 응답에서 총 소요 시간, 환승 횟수, 첫 번째 버스 번호를 추출합니다.
        - 백엔드 전체에서 사용하는 TransportResult 형태로 변환합니다.

    입력:
        destination:
            - 사용자 목적지명입니다.

        path:
            - ODsay result.path 안의 단일 경로 데이터입니다.

    반환:
        TransportResult:
            - 정리된 교통 정보입니다.
    """

    info = path.get("info", {})
    sub_paths = path.get("subPath", [])

    total_time_min = info.get("totalTime")
    transfer_count = info.get("busTransitCount")
    first_bus_number = _extract_first_bus_number(sub_paths)

    route_summary = _build_route_summary(
        destination=destination,
        first_bus_number=first_bus_number,
        total_time_min=total_time_min,
        transfer_count=transfer_count,
    )

    return TransportResult(
        destination=destination,
        bus_number=first_bus_number,
        arrival_time=None,
        total_time_min=total_time_min,
        transfer_count=transfer_count,
        route_summary=route_summary,
        source="odsay",
    )


def _extract_first_bus_number(sub_paths: list[dict[str, Any]]) -> str | None:
    """
    ODsay subPath에서 첫 번째 버스 번호를 추출하는 함수입니다.

    기능:
        - trafficType이 2인 버스 구간을 찾습니다.
        - 해당 구간의 lane 목록에서 busNo를 추출합니다.

    입력:
        sub_paths:
            - ODsay 경로의 세부 이동 구간 목록입니다.

    반환:
        str | None:
            - 첫 번째 버스 번호입니다.
            - 버스 구간이 없으면 None을 반환합니다.
    """

    for sub_path in sub_paths:
        if sub_path.get("trafficType") != 2:
            continue

        lanes = sub_path.get("lane", [])

        for lane in lanes:
            bus_number = lane.get("busNo")

            if bus_number:
                return str(bus_number)

    return None


def _build_route_summary(
    destination: str,
    first_bus_number: str | None,
    total_time_min: int | None,
    transfer_count: int | None,
) -> str:
    """
    경로 조회 결과를 요약 문장으로 만드는 함수입니다.

    기능:
        - 교통 API 결과를 사람이 이해하기 쉬운 한 문장으로 정리합니다.
        - 최종 사용자 응답은 response_builder.py에서 다시 생성합니다.

    입력:
        destination:
            - 목적지명입니다.

        first_bus_number:
            - 첫 번째로 이용할 수 있는 버스 번호입니다.

        total_time_min:
            - 예상 총 소요 시간입니다.

        transfer_count:
            - 버스 환승 횟수입니다.

    반환:
        str:
            - 경로 요약 문장입니다.
    """

    parts = [f"{destination}까지 가는 경로를 찾았습니다."]

    if first_bus_number:
        parts.append(f"첫 번째로 이용할 수 있는 버스는 {first_bus_number}번입니다.")

    if total_time_min is not None:
        parts.append(f"예상 소요 시간은 약 {total_time_min}분입니다.")

    if transfer_count is not None:
        parts.append(f"버스 환승 횟수는 {transfer_count}회입니다.")

    return " ".join(parts)


def _mock_transport_result(parsed: ParsedIntent) -> TransportResult:
    """
    외부 API 없이 교통 정보 결과를 테스트하는 mock 함수입니다.

    기능:
        - OpenAI, ODsay, Kakao API 없이 전체 백엔드 흐름을 테스트합니다.
        - 실제 운영 응답으로 사용하면 안 됩니다.

    입력:
        parsed:
            - LLM 분석 결과입니다.

    반환:
        TransportResult:
            - 테스트용 교통 정보입니다.
    """

    if parsed.intent == "route":
        return TransportResult(
            destination=parsed.destination_text,
            bus_number="146",
            arrival_time="5분 후",
            total_time_min=24,
            transfer_count=0,
            route_summary=f"{parsed.destination_text} 방향 146번 버스를 이용하는 경로입니다.",
            source="mock",
        )

    if parsed.intent == "arrival":
        return TransportResult(
            destination=None,
            bus_number=parsed.bus_number,
            arrival_time="3분 후",
            total_time_min=None,
            transfer_count=None,
            route_summary=f"{parsed.bus_number}번 버스가 약 3분 후 도착 예정입니다.",
            source="mock",
        )

    return TransportResult(
        destination=None,
        bus_number=None,
        arrival_time=None,
        total_time_min=None,
        transfer_count=None,
        route_summary=None,
        source="mock",
    )