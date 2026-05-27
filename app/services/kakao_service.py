import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.services.constants import (
    KAKAO_KEYWORD_SEARCH_URL,
    KNOWN_PLACE_COORDS,
    KOREA_LATITUDE_MAX,
    KOREA_LATITUDE_MIN,
    KOREA_LONGITUDE_MAX,
    KOREA_LONGITUDE_MIN,
)
from app.services.exceptions import CoordinateResolveError, TransportAPIError
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

_default_origin_cache: tuple[str, float, float] | None = None


@_http_retry
async def _kakao_fetch(kakao_key: str, place_text: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
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
    """장소명을 Kakao Local API로 좌표 변환합니다. 없으면 알려진 좌표를 보조로 사용합니다."""

    normalized = place_text.strip()
    if not normalized:
        raise CoordinateResolveError(f"{label}가 비어 있습니다.")

    try:
        return await _resolve_via_kakao(normalized, label)

    except CoordinateResolveError:
        if normalized not in KNOWN_PLACE_COORDS:
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
            f"Kakao Local API HTTP 오류가 발생했습니다: {exc.response.status_code}"
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
    """출발지를 (이름, x, y) 튜플로 반환합니다. None이면 기기 기본 위치를 사용합니다."""

    if origin_text:
        x, y = await resolve_place_coordinates(origin_text, "출발지")
        return origin_text.strip(), x, y

    return await _resolve_default_origin()


async def _resolve_default_origin() -> tuple[str, float, float]:
    """기기 설치 위치 좌표를 반환합니다. 프로세스 동안 캐싱됩니다."""

    global _default_origin_cache

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
    origin_x = get_setting("DEFAULT_ORIGIN_X") or get_setting("ORIGIN_X")
    origin_y = get_setting("DEFAULT_ORIGIN_Y") or get_setting("ORIGIN_Y")

    if origin_x is None or origin_y is None:
        raise CoordinateResolveError("출발지를 말씀해 주세요.")

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
    """ODsay에 전달할 좌표가 대한민국 서비스 범위 안에 있는지 확인합니다."""

    valid = (
        KOREA_LONGITUDE_MIN <= longitude <= KOREA_LONGITUDE_MAX
        and KOREA_LATITUDE_MIN <= latitude <= KOREA_LATITUDE_MAX
    )
    if not valid:
        raise CoordinateResolveError(
            f"{label} 좌표가 대한민국 서비스 범위를 벗어났습니다. "
            f"longitude={longitude}, latitude={latitude}"
        )
