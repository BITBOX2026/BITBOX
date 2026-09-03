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
from difflib import SequenceMatcher

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


def _has_transit_document(documents: list[dict]) -> bool:
    """결과 안에 역·정류장 같은 교통 장소가 하나라도 있는지 봅니다."""
    for document in documents:
        if str(document.get("category_group_code") or "") == "SW8":
            return True
        if "교통" in str(document.get("category_name") or ""):
            return True
    return False


def _tag_source_rank(documents: list[dict]) -> list[dict]:
    """각 후보에 "자기 검색 안에서 몇 번째였는지"를 표시합니다.

    Kakao 정확도 순위는 쓸 만한 신호라 점수에 반영합니다. 그런데 두 검색 결과를
    합치면 뒤 목록의 1위가 앞 목록의 5위보다 낮은 순위로 취급되어, 순위 보정이
    엉뚱한 쪽을 돕습니다. 그래서 합치기 전에 각자 순위를 새겨 둡니다.
    """
    tagged = list(documents)
    for index, document in enumerate(tagged):
        document["_bitbox_source_rank"] = index
    return tagged


async def _fetch_place_documents(
    kakao_key: str,
    place_text: str,
    x: float | None,
    y: float | None,
    size: int,
) -> tuple[list[dict], set[str]]:
    """장소 후보를 가져오되, 역 후보가 빠지면 한 번 더 찾아 채웁니다.

    왜 필요한가
    -----------
    이용자는 "잠실 가는 버스"처럼 역 이름을 끝까지 말하지 않습니다. 그런데 Kakao
    키워드 검색에 "잠실"을 그대로 넣으면 석촌호수·롯데월드 같은 관광명소만 돌아오고
    잠실역은 결과에 아예 없습니다(size 를 15로 늘려도 마찬가지였습니다). 그대로 두면
    버스로 가려는 사람에게 관광명소 좌표를 목적지로 잡아 줍니다.

    그래서 첫 검색에 교통 장소가 하나도 없을 때만 ``"<질의>역"`` 으로 한 번 더
    찾아 뒤에 붙입니다. "홍대"처럼 첫 검색에 이미 역이 들어 있으면 추가 호출을
    하지 않으므로, 자동완성이 글자마다 호출량을 두 배로 쓰지 않습니다.

    두 번째 검색에서 온 이름을 함께 돌려줍니다. 이용자가 입으로 말하지 않은 이름을
    고른 셈이므로, 호출한 쪽이 확인 절차를 띄울지 판단할 수 있어야 합니다.
    """
    payload = await _kakao_fetch(kakao_key, place_text, x, y, size=size)
    documents = _tag_source_rank(payload.get("documents", []))
    if _is_station_query(place_text) or _has_transit_document(documents):
        return documents, set()
    # 자동완성은 글자마다 들어옵니다. 한 글자짜리에 "역"을 붙여 봐야 의미 있는 역이
    # 나오지 않으므로("잠역"), 두 글자부터 보조 검색을 씁니다.
    if len(_normalize_place_name(place_text)) < 2:
        return documents, set()

    try:
        station_payload = await _kakao_fetch(kakao_key, f"{place_text}역", x, y, size=size)
    except (ExternalServiceError, httpx.RequestError):
        # 보조 검색입니다. 실패해도 첫 검색 결과로 계속 진행합니다.
        return documents, set()

    seen = {
        (str(doc.get("place_name") or ""), str(doc.get("x") or ""), str(doc.get("y") or ""))
        for doc in documents
    }
    augmented: set[str] = set()
    # 보조 검색 결과는 자기 검색 안에서의 순위를 그대로 갖습니다. 합친 목록의 뒤쪽에
    # 붙는다는 이유로 순위 보정에서 손해를 보면, 정작 찾던 역이 관광명소에 밀립니다.
    # (`압구정` 이 `압구정지` 에, `신림` 이 `신림계곡` 에 밀리던 원인이었습니다.)
    for document in _tag_source_rank(station_payload.get("documents", [])):
        key = (
            str(document.get("place_name") or ""),
            str(document.get("x") or ""),
            str(document.get("y") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        documents.append(document)
        augmented.add(_normalize_place_name(str(document.get("place_name") or "")))
    return documents, augmented


async def resolve_place_candidate(place_text: str, label: str = "목적지") -> PlaceResolution:
    """상위 5개를 이름·카테고리·거리로 재정렬하고 모호성을 함께 반환합니다."""
    kakao_key = get_setting("KAKAO_REST_API_KEY")
    if not kakao_key:
        raise TransportAPIError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    device_x, device_y = _get_device_coordinates()

    try:
        documents, augmented_names = await _fetch_place_documents(
            kakao_key, place_text, device_x, device_y, size=5
        )
    except httpx.RequestError as exc:
        raise ExternalServiceError(
            "Kakao Local API 요청 오류가 발생했습니다.",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

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
    needs_confirmation = _needs_place_confirmation(place_text, ranked, augmented_names)
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
        documents, _augmented = await _fetch_place_documents(
            kakao_key, query.strip(), device_x, device_y, size=max_results
        )
    except httpx.RequestError as exc:
        raise ExternalServiceError(
            "Kakao Local API 요청 오류가 발생했습니다.",
            user_message="장소 검색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    return [
        _place_document_to_candidate(doc)
        for doc in _rank_place_documents(query, documents)
        if doc.get("place_name")
    ][:max_results]


def _normalize_place_name(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", value).lower()


def _is_station_query(query: str) -> bool:
    normalized = _normalize_place_name(query)
    return normalized.endswith("역") or "지하철역" in normalized


def _place_score(query: str, document: dict, kakao_rank: int = 0) -> tuple[float, float]:
    """이름 적합도·교통 성격·Kakao 정확도 순위를 합쳐 점수를 냅니다.

    주의해서 볼 점이 둘 있습니다.

    첫째, "포함"만으로 크게 올리면 안 됩니다. `서울시청` 을 찾을 때 `다이소
    서울시청광장점` 은 질의를 통째로 담고 있지만 이용자가 찾는 곳이 아닙니다.
    그래서 포함 점수를 "질의가 이름에서 차지하는 비중"으로 깎습니다.

    둘째, 글자가 조금 어긋나도 같은 곳일 수 있습니다. `서울시청` 과
    `서울특별시청` 은 포함 관계가 아니라 예전에는 0점이었고, 그 결과 다이소가
    1위가 됐습니다. 문자열 유사도를 함께 봐서 이런 경우를 살립니다.

    Kakao 자체 정확도 순위도 약하게 반영합니다. 이미 잘 만들어진 신호이고,
    우리 규칙이 그것을 통째로 뒤집기보다 다듬는 편이 안전합니다.
    """
    query_name = _normalize_place_name(query)
    place_name = _normalize_place_name(str(document.get("place_name") or ""))
    score = 0.0
    if place_name and place_name == query_name:
        score += 120
    elif query_name and place_name.startswith(query_name):
        score += 90
    elif query_name and query_name in place_name:
        # 이름이 길수록 질의가 우연히 들어 있을 가능성이 큽니다.
        score += 60 * (len(query_name) / len(place_name))

    if query_name and place_name:
        score += 40 * SequenceMatcher(None, query_name, place_name).ratio()

    # Kakao 정확도 순위 보정. 이름 등급 간격(30점)을 넘지 않게 작게 둡니다.
    source_rank = document.get("_bitbox_source_rank")
    rank = int(source_rank) if isinstance(source_rank, int) else kakao_rank
    score += max(0.0, 20.0 - 4.0 * rank)

    category_code = str(document.get("category_group_code") or "")
    category_name = str(document.get("category_name") or "")
    # "역"까지 말한 질의는 교통 장소를 크게 우대합니다. 그렇지 않은 질의도 이 서비스의
    # 목적지는 결국 버스로 닿는 곳이므로 약하게 우대합니다. 이 가중치는 이름이 정확히
    # 맞는 장소(+120)를 뒤집지 않을 만큼만 둡니다. "잠실역 2호선"과 "잠실역 공영주차장"
    # 처럼 이름 점수가 같을 때 무엇을 앞세울지가 이 값으로 갈립니다.
    if _is_station_query(query):
        station_bonus, subway_bonus, transit_bonus = 80, 40, 20
    else:
        # 이름 등급 간격(30점)보다 작게 둡니다. 크게 주면 `경복궁` 을 찾는 사람을
        # `경복궁역` 으로 보내 버립니다. 이용자가 말한 곳을 바꾸면 안 됩니다.
        station_bonus, subway_bonus, transit_bonus = 18, 8, 4
    if category_code == "SW8":
        score += station_bonus
    if "지하철역" in category_name:
        score += subway_bonus
    elif "교통" in category_name:
        score += transit_bonus

    try:
        distance = float(document.get("distance") or 10**9)
    except (TypeError, ValueError):
        distance = float(10**9)
    return score, -distance


def _rank_place_documents(query: str, documents: list[dict]) -> list[dict]:
    """Kakao 상위 후보를 의미 적합도 우선으로 안정 정렬합니다."""
    scored = [
        (_place_score(query, document, index), index, document)
        for index, document in enumerate(documents)
    ]
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [document for _score, _index, document in scored]


def _needs_place_confirmation(
    query: str,
    ranked: list[dict],
    augmented_names: set[str] | None = None,
) -> bool:
    if not ranked:
        return False
    selected_name = str(ranked[0].get("place_name") or "")
    normalized_selected = _normalize_place_name(selected_name)
    # 보조 검색("<질의>역")에서 올라온 후보를 골랐다면, 이용자가 입으로 말하지 않은
    # 이름을 우리가 채워 넣은 것입니다. 그 추측을 말없이 목적지로 삼지 않습니다.
    if augmented_names and normalized_selected in augmented_names:
        return True
    if _is_station_query(query) and normalized_selected != _normalize_place_name(query):
        return True
    # 이름이 확실히 맞지 않으면 묻고 넘어갑니다.
    #
    # 예전 규칙은 "점수가 낮고 **동시에** 2위와 비슷할 때"만 물었습니다. 그래서 오답이
    # 확실한 1등일 때는 그냥 지나갔습니다. 실제로 "없는곳"이 미용실 `헤어나올수없는곳`
    # 으로, "여의도 가자"가 주류도매 `가자주류 여의도역점`으로 아무 확인 없이 갔습니다.
    #
    # 임계값 100은 실제 Kakao 응답 26건을 재어 정했습니다. 100점 미만은 전부 오답이거나
    # 사람이 봐도 모호한 후보였고(37·52·64·88점), 정답은 모두 126점 이상이었습니다.
    first_score = _place_score(query, ranked[0])[0]
    if first_score < 100:
        return True
    if len(ranked) < 2:
        return False
    second_score = _place_score(query, ranked[1])[0]
    return first_score - second_score < 15


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
