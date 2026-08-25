"""
Kakao Local API 클라이언트 — 장소명 → 좌표 변환

사용자가 말한 장소명("강남역", "서울역 앞" 등)을 ODsay에 전달할 수 있는
경도/위도 좌표로 변환합니다.

기기 기본 출발지는 프로세스 동안 캐싱되어 반복 API 호출을 방지합니다.
Kakao API 실패 시 KNOWN_PLACE_COORDS(내장 좌표 목록)를 보조로 사용합니다.
"""

import asyncio
import re
from dataclasses import dataclass

import httpx

from app.core.logger import get_logger
from app.services.core.constants import (
    KAKAO_KEYWORD_SEARCH_URL,
    KNOWN_PLACE_COORDS,
    KOREA_LATITUDE_MAX,
    KOREA_LATITUDE_MIN,
    KOREA_LONGITUDE_MAX,
    KOREA_LONGITUDE_MIN,
)
from app.services.core.exceptions import (
    CoordinateResolveError,
    ExternalServiceError,
    TransportAPIError,
)
from app.services.core.http_client import get_http_client
from app.services.core.http_utils import http_retry as _http_retry
from app.services.core.settings_helper import get_setting

logger = get_logger(__name__)

# 기기 기본 출발지 캐시 — 서버 재시작 전까지 유지
_default_origin_cache: tuple[str, float, float] | None = None
_default_origin_lock = asyncio.Lock()


@dataclass(frozen=True)
class PlaceResolution:
    selected: dict
    alternatives: list[dict]
    needs_confirmation: bool
    prompt: str


@_http_retry
async def _kakao_fetch(
    kakao_key: str,
    place_text: str,
    x: float | None = None,
    y: float | None = None,
    size: int = 5,
) -> dict:
    """Kakao Local 키워드 검색 API를 호출합니다. 실패 시 자동 재시도합니다."""
    params: dict = {"query": place_text, "size": size}
    if x is not None and y is not None:
        # 위치는 거리 정보와 보조 신호로만 사용합니다. 거리순 정렬은 이름이 정확한
        # 목적지보다 가까운 동명이 장소를 앞세울 수 있어 정확도순을 유지합니다.
        params["x"] = x
        params["y"] = y
    params["sort"] = "accuracy"
    response = await get_http_client().get(
        KAKAO_KEYWORD_SEARCH_URL,
        headers={"Authorization": f"KakaoAK {kakao_key}"},
        params=params,
    )
    if response.status_code >= 400:
        raise ExternalServiceError(
            f"Kakao Local API HTTP 오류: {response.status_code}",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            retryable=response.status_code == 429 or response.status_code >= 500,
            provider_down=response.status_code in {401, 403},
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ExternalServiceError(
            "Kakao Local API 응답을 파싱하지 못했습니다.",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc


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
    resolution = await resolve_place_candidate(place_text, label)
    selected = resolution.selected
    return float(selected["x"]), float(selected["y"])


async def resolve_place_candidate(place_text: str, label: str = "목적지") -> PlaceResolution:
    """상위 5개를 이름·카테고리·거리로 재정렬하고 모호성을 함께 반환합니다."""
    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key:
        raise TransportAPIError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    device_x, device_y = _get_device_coordinates()

    try:
        payload = await _kakao_fetch(kakao_key, place_text, device_x, device_y, size=5)

    except httpx.RequestError as exc:
        raise ExternalServiceError(
            "Kakao Local API 요청 오류가 발생했습니다.",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    documents = payload.get("documents", [])
    if not documents:
        raise CoordinateResolveError(f"'{place_text}' 검색 결과가 없습니다.")

    ranked = _rank_place_documents(place_text, documents)[:5]
    first_place = ranked[0]

    try:
        longitude = float(first_place["x"])
        latitude = float(first_place["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CoordinateResolveError(
            "Kakao Local API 응답에서 좌표를 찾지 못했습니다."
        ) from exc

    _validate_korea_coordinates(longitude, latitude, label)
    selected = _place_document_to_candidate(first_place)
    alternatives = [_place_document_to_candidate(doc) for doc in ranked[1:]]
    needs_confirmation = _needs_place_confirmation(place_text, ranked)
    prompt = f"{selected['name']}이 맞나요?" if needs_confirmation else ""
    return PlaceResolution(selected, alternatives, needs_confirmation, prompt)


async def search_place_suggestions(
    query: str,
    max_results: int = 5,
) -> list[dict]:
    """
    장소명 자동완성 후보를 반환합니다.

    Kakao 키워드 검색으로 최대 max_results개 결과를 가져와
    [{"name": ..., "address": ..., "x": ..., "y": ...}, ...] 형태로 반환합니다.
    검색 결과가 없으면 빈 리스트를 반환하고, API 장애는 예외로 구분합니다.
    """
    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key or not query.strip():
        return []

    device_x, device_y = _get_device_coordinates()

    try:
        payload = await _kakao_fetch(
            kakao_key, query.strip(), device_x, device_y, size=max_results
        )
    except httpx.RequestError as exc:
        raise ExternalServiceError(
            "Kakao Local API 요청 오류가 발생했습니다.",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    return [
        _place_document_to_candidate(doc)
        for doc in _rank_place_documents(query, payload.get("documents", []))
        if doc.get("place_name")
    ][:max_results]


def _normalize_place_name(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", value).lower()


def _is_station_query(query: str) -> bool:
    normalized = _normalize_place_name(query)
    return normalized.endswith("역") or "지하철역" in normalized


def _place_score(query: str, document: dict) -> tuple[float, float]:
    query_name = _normalize_place_name(query)
    place_name = _normalize_place_name(str(document.get("place_name") or ""))
    score = 0.0
    if place_name == query_name:
        score += 120
    elif place_name.startswith(query_name):
        score += 90
    elif query_name and query_name in place_name:
        score += 60

    category_code = str(document.get("category_group_code") or "")
    category_name = str(document.get("category_name") or "")
    if _is_station_query(query):
        if category_code == "SW8":
            score += 80
        if "지하철역" in category_name:
            score += 40
        elif "교통" in category_name:
            score += 20

    try:
        distance = float(document.get("distance") or 10**9)
    except (TypeError, ValueError):
        distance = float(10**9)
    return score, -distance


def _rank_place_documents(query: str, documents: list[dict]) -> list[dict]:
    """Kakao 상위 후보를 의미 적합도 우선으로 안정 정렬합니다."""
    return sorted(documents, key=lambda doc: _place_score(query, doc), reverse=True)


def _needs_place_confirmation(query: str, ranked: list[dict]) -> bool:
    if not ranked:
        return False
    selected_name = str(ranked[0].get("place_name") or "")
    if _is_station_query(query) and _normalize_place_name(selected_name) != _normalize_place_name(query):
        return True
    if len(ranked) < 2:
        return False
    first_score = _place_score(query, ranked[0])[0]
    second_score = _place_score(query, ranked[1])[0]
    return first_score < 100 and first_score - second_score < 15


def _place_document_to_candidate(document: dict) -> dict:
    return {
        "name": document.get("place_name", ""),
        "address": document.get("road_address_name") or document.get("address_name") or "",
        "category": document.get("category_name") or document.get("category_group_name") or "",
        "category_code": document.get("category_group_code") or "",
        "x": document.get("x"),
        "y": document.get("y"),
    }


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

    async with _default_origin_lock:
        if _default_origin_cache is not None:
            return _default_origin_cache

        default_name = get_setting("DEFAULT_ORIGIN_NAME")
        if default_name:
            x, y = await resolve_place_coordinates(default_name, "기본 출발지")
            _default_origin_cache = (default_name, x, y)
            return _default_origin_cache

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


def _get_device_coordinates() -> tuple[float | None, float | None]:
    """기기 설치 위치의 (경도, 위도)를 반환합니다.

    캐시된 기본 출발지 좌표를 우선 사용하고, 없으면 환경변수에서 읽습니다.
    좌표를 알 수 없으면 (None, None)을 반환합니다.
    """
    if _default_origin_cache is not None:
        _, x, y = _default_origin_cache
        return x, y

    origin_x = get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X")
    origin_y = get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y")
    if origin_x is None or origin_y is None:
        return None, None

    try:
        return float(origin_x), float(origin_y)
    except (TypeError, ValueError):
        return None, None


def _allow_known_place_fallback() -> bool:
    """운영 환경에서는 Kakao 장애를 내장 좌표로 숨기지 않습니다."""
    explicit = get_setting("ALLOW_KNOWN_PLACE_FALLBACK")
    if explicit is not None:
        return str(explicit).strip().lower() in {"true", "1", "yes", "y", "on"}

    return str(get_setting("APP_ENV", "local")).strip().lower() != "prod"
