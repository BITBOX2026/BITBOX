"""
Kakao Local API 클라이언트 — 장소명 → 좌표 변환

사용자가 말한 장소명("강남역", "서울역 앞" 등)을 ODsay에 전달할 수 있는
경도/위도 좌표로 변환합니다.

기기 기본 출발지는 프로세스 동안 캐싱되어 반복 API 호출을 방지합니다.
Kakao API 실패 시 KNOWN_PLACE_COORDS(내장 좌표 목록)를 보조로 사용합니다.
"""

import httpx

from app.services.core.constants import (
    KAKAO_KEYWORD_SEARCH_URL,
    KNOWN_PLACE_COORDS,
    KOREA_LATITUDE_MAX,
    KOREA_LATITUDE_MIN,
    KOREA_LONGITUDE_MAX,
    KOREA_LONGITUDE_MIN,
)
from app.services.core.exceptions import CoordinateResolveError, TransportAPIError
from app.services.core.http_client import get_http_client
from app.services.core.http_utils import http_retry as _http_retry
from app.services.core.settings_helper import get_bool_setting, get_setting

# 기기 기본 출발지 캐시 — 서버 재시작 전까지 유지
_default_origin_cache: tuple[str, float, float] | None = None


@_http_retry
async def _kakao_fetch(kakao_key: str, place_text: str) -> dict:
    """Kakao Local 키워드 검색 API를 호출합니다. 실패 시 자동 재시도합니다."""
    response = await get_http_client().get(
        KAKAO_KEYWORD_SEARCH_URL,
        headers={"Authorization": f"KakaoAK {kakao_key}"},
        params={"query": place_text, "size": 1},
    )
    response.raise_for_status()
    return response.json()


async def resolve_place_coordinates(
    place_text: str,
    label: str,
) -> tuple[float, float]:
    """
    장소명을 (경도, 위도) 좌표로 변환합니다.

    Kakao API 실패 시 KNOWN_PLACE_COORDS에서 보조 탐색을 시도합니다.
    두 방법 모두 실패하면 CoordinateResolveError를 발생시킵니다.
    """
    normalized = place_text.strip()
    if not normalized:
        raise CoordinateResolveError(f"{label}가 비어 있습니다.")

    try:
        return await _resolve_via_kakao(normalized, label)

    except (CoordinateResolveError, TransportAPIError):
        # Kakao API 실패(키 미설정 포함) 시 내장 좌표 목록에서 보조 탐색
        if not _allow_known_place_fallback() or normalized not in KNOWN_PLACE_COORDS:
            raise

    longitude, latitude = KNOWN_PLACE_COORDS[normalized]
    _validate_korea_coordinates(longitude, latitude, label)
    return longitude, latitude


async def _resolve_via_kakao(place_text: str, label: str) -> tuple[float, float]:
    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key:
        raise TransportAPIError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    try:
        payload = await _kakao_fetch(kakao_key, place_text)

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"Kakao Local API HTTP 오류: {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError("Kakao Local API 요청 오류가 발생했습니다.") from exc

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

    _validate_korea_coordinates(longitude, latitude, label)
    return longitude, latitude


async def resolve_origin(origin_text: str | None) -> tuple[str, float, float]:
    """
    출발지를 (이름, 경도, 위도)로 반환합니다.
    origin_text가 None이면 기기 기본 출발지를 사용합니다.
    """
    if origin_text:
        x, y = await resolve_place_coordinates(origin_text, "출발지")
        return origin_text.strip(), x, y

    return await _resolve_default_origin()


async def _resolve_default_origin() -> tuple[str, float, float]:
    """
    기기 설치 위치 좌표를 반환합니다.
    서버 재시작 전까지 결과를 메모리에 캐싱합니다.
    """
    global _default_origin_cache

    if _default_origin_cache is not None:
        return _default_origin_cache

    default_name = get_setting("DEFAULT_ORIGIN_NAME")
    if default_name:
        # 장소명이 설정된 경우 Kakao API로 좌표 변환
        x, y = await resolve_place_coordinates(default_name, "기본 출발지")
        _default_origin_cache = (default_name, x, y)
        return _default_origin_cache

    # 좌표가 직접 설정된 경우
    x, y = _get_origin_coordinates_fallback()
    _default_origin_cache = ("현재 위치", x, y)
    return _default_origin_cache


def _get_origin_coordinates_fallback() -> tuple[float, float]:
    """DEFAULT_ORIGIN_X/Y 또는 ORIGIN_X/Y 환경변수에서 좌표를 읽습니다."""
    origin_x = get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X")
    origin_y = get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y")

    if origin_x is None or origin_y is None:
        raise CoordinateResolveError(user_message="출발지를 말씀해 주세요.")

    try:
        longitude = float(origin_x)
        latitude = float(origin_y)
    except ValueError as exc:
        raise TransportAPIError(
            "DEFAULT_ORIGIN_X, DEFAULT_ORIGIN_Y는 숫자여야 합니다."
        ) from exc

    _validate_korea_coordinates(longitude, latitude, "출발지")
    return longitude, latitude


def _validate_korea_coordinates(longitude: float, latitude: float, label: str) -> None:
    """ODsay 서비스 범위(대한민국) 내의 좌표인지 확인합니다."""
    valid = (
        KOREA_LONGITUDE_MIN <= longitude <= KOREA_LONGITUDE_MAX
        and KOREA_LATITUDE_MIN <= latitude <= KOREA_LATITUDE_MAX
    )
    if not valid:
        raise CoordinateResolveError(
            f"{label} 좌표가 대한민국 서비스 범위를 벗어났습니다. "
            f"경도={longitude}, 위도={latitude}"
        )


def _allow_known_place_fallback() -> bool:
    """운영 환경에서는 Kakao 장애를 내장 좌표로 숨기지 않습니다."""
    explicit = get_setting("ALLOW_KNOWN_PLACE_FALLBACK")
    if explicit is not None:
        return str(explicit).strip().lower() in {"true", "1", "yes", "y", "on"}

    return str(get_setting("APP_ENV", "local")).strip().lower() != "prod"
