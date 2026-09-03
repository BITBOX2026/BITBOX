import asyncio

from app.services.transit import kakao_service
from app.services.transit.kakao_service import (
    _fetch_place_documents,
    _has_transit_document,
    _needs_place_confirmation,
    _rank_place_documents,
)


def _doc(name: str, category_code: str, category: str, distance: str) -> dict:
    return {
        "place_name": name,
        "category_group_code": category_code,
        "category_name": category,
        "distance": distance,
        "x": "127.0",
        "y": "37.5",
    }


def test_station_category_beats_nearer_non_transport_place() -> None:
    documents = [
        _doc("강남역 맛집", "FD6", "음식점", "100"),
        _doc("강남역 2호선", "SW8", "교통,수송 > 지하철역", "15000"),
        _doc("강남역 신분당선", "SW8", "교통,수송 > 지하철역", "15100"),
    ]
    ranked = _rank_place_documents("강남역", documents)
    assert ranked[0]["place_name"] == "강남역 2호선"


def test_line_specific_station_candidate_requires_confirmation() -> None:
    ranked = [
        _doc("강남역 2호선", "SW8", "교통,수송 > 지하철역", "100"),
        _doc("강남역 신분당선", "SW8", "교통,수송 > 지하철역", "120"),
    ]
    assert _needs_place_confirmation("강남역", ranked) is True


def test_exact_clear_place_does_not_require_confirmation() -> None:
    ranked = [
        _doc("서울시청", "PO3", "공공,사회기관 > 시청", "100"),
        _doc("서울시청 서소문청사", "PO3", "공공,사회기관", "150"),
    ]
    assert _needs_place_confirmation("서울시청", ranked) is False


# 아래 문서 묶음은 Kakao Local API 가 실제로 돌려준 순서와 카테고리를 그대로 옮긴
# 것입니다. 합성 데이터로는 드러나지 않던 오정렬이 실호출에서 나왔기 때문입니다.


def test_a_brand_store_never_outranks_the_place_it_is_named_after() -> None:
    """`서울시청` 검색이 `다이소 서울시청광장점` 으로 가면 안 됩니다.

    예전 규칙은 "이름에 질의가 들어 있으면 +60" 이라 다이소가 60점, 정작
    `서울특별시청` 은 포함 관계가 아니라 0점이었습니다. Kakao 가 1위로 준 답을
    우리가 꼴찌로 밀어내고 생활용품점을 목적지로 잡던 상태였습니다.
    """
    documents = [
        _doc("서울특별시청", "PO3", "사회,공공기관 > 지방행정기관 > 시청 > 특별시청", ""),
        _doc("서울특별시청 서소문2청사", "", "사회,공공기관 > 지방행정기관", ""),
        _doc("서울특별시청 서소문청사", "", "사회,공공기관 > 지방행정기관", ""),
        _doc("서울특별시청 서소문청사 주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
        _doc("다이소 서울시청광장점", "", "가정,생활 > 생활용품점 > 다이소", ""),
    ]
    ranked = _rank_place_documents("서울시청", documents)
    assert ranked[0]["place_name"] == "서울특별시청"


def test_a_station_never_replaces_the_landmark_the_user_named() -> None:
    """`경복궁` 을 찾는 사람을 `경복궁역` 으로 보내면 안 됩니다.

    교통 장소 가산점은 이름이 정확히 맞는 후보를 뒤집지 않을 만큼만 둡니다.
    """
    documents = [
        _doc("경복궁", "AT4", "여행 > 관광,명소 > 문화유적 > 고궁,궁", ""),
        _doc("경복궁 주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
        _doc("경복궁역 3호선", "SW8", "교통,수송 > 지하철,전철 > 수도권3호선", ""),
    ]
    ranked = _rank_place_documents("경복궁", documents)
    assert ranked[0]["place_name"] == "경복궁"


def test_station_leads_when_the_query_is_only_an_area_name() -> None:
    """`잠실` 처럼 역 이름을 끝까지 말하지 않아도 역이 앞에 와야 합니다.

    Kakao 는 `잠실` 에 대해 석촌호수·롯데월드 같은 관광명소만 돌려줍니다(size 를
    15로 늘려도 역은 없습니다). 그래서 서비스가 `잠실역` 으로 한 번 더 찾아 후보에
    합칩니다. 이 테스트는 합쳐진 뒤의 정렬을 고정합니다.
    """
    documents = [
        _doc("석촌호수 서호", "AT4", "여행 > 관광,명소 > 호수", ""),
        _doc("롯데월드 어드벤처", "AT4", "여행 > 관광,명소 > 테마파크", ""),
        _doc("더 스피어", "", "여행 > 관광,명소", ""),
        # 아래 두 건이 보조 검색("잠실역")에서 합쳐진 후보입니다.
        _doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", ""),
        _doc("잠실역 공영주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
    ]
    ranked = _rank_place_documents("잠실", documents)
    assert ranked[0]["place_name"] == "잠실역 2호선"


def test_a_guessed_station_name_must_be_confirmed() -> None:
    """이용자가 말하지 않은 이름을 채워 넣었으면 묻고 넘어갑니다."""
    ranked = [
        _doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", ""),
        _doc("석촌호수 서호", "AT4", "여행 > 관광,명소 > 호수", ""),
    ]
    assert _needs_place_confirmation("잠실", ranked, {"잠실역2호선"}) is True
    # 이용자가 직접 말한 이름이라면 굳이 되묻지 않습니다.
    assert _needs_place_confirmation("잠실역 2호선", ranked, set()) is False


def test_second_lookup_runs_only_when_no_transit_place_was_found() -> None:
    """`홍대` 처럼 첫 검색에 이미 역이 있으면 추가 호출을 하지 않습니다.

    자동완성은 글자마다 호출되므로, 필요할 때만 한 번 더 찾아야 합니다.
    """
    with_station = [
        _doc("홍익대학교 서울캠퍼스", "SC4", "교육,학문 > 학교 > 대학교", ""),
        _doc("홍대입구역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", ""),
    ]
    without_station = [
        _doc("석촌호수 서호", "AT4", "여행 > 관광,명소 > 호수", ""),
        _doc("더 스피어", "", "여행 > 관광,명소", ""),
    ]
    assert _has_transit_document(with_station) is True
    assert _has_transit_document(without_station) is False


def _run_fetch(monkeypatch, query: str, responses: dict[str, list[dict]]) -> tuple[list[dict], set[str], list[str]]:
    """`_kakao_fetch` 를 가짜로 바꿔, 어떤 질의가 몇 번 나갔는지까지 기록합니다."""
    asked: list[str] = []

    async def fake_fetch(_key, place_text, _x=None, _y=None, size=5):
        asked.append(place_text)
        return {"documents": responses.get(place_text, [])}

    monkeypatch.setattr(kakao_service, "_kakao_fetch", fake_fetch)
    documents, augmented = asyncio.run(_fetch_place_documents("key", query, None, None, 5))
    return documents, augmented, asked


def test_area_name_triggers_a_station_lookup_and_merges_it(monkeypatch) -> None:
    """`잠실` 은 역 후보가 없으므로 `잠실역` 으로 한 번 더 찾아 합칩니다."""
    documents, augmented, asked = _run_fetch(
        monkeypatch,
        "잠실",
        {
            "잠실": [_doc("석촌호수 서호", "AT4", "여행 > 관광,명소 > 호수", "")],
            "잠실역": [_doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", "")],
        },
    )
    assert asked == ["잠실", "잠실역"]
    assert [d["place_name"] for d in documents] == ["석촌호수 서호", "잠실역 2호선"]
    # 합쳐 넣은 이름은 이용자가 말하지 않은 것이므로 확인 대상으로 표시합니다.
    assert augmented == {"잠실역2호선"}


def test_no_second_lookup_when_the_first_result_already_has_a_station(monkeypatch) -> None:
    """`홍대` 는 첫 검색에 이미 역이 있어 추가 호출을 하지 않습니다."""
    _documents, augmented, asked = _run_fetch(
        monkeypatch,
        "홍대",
        {"홍대": [_doc("홍대입구역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", "")]},
    )
    assert asked == ["홍대"]
    assert augmented == set()


def test_no_second_lookup_when_the_user_already_said_station(monkeypatch) -> None:
    """`잠실역` 처럼 이미 역을 말한 질의는 그대로 한 번만 찾습니다."""
    _documents, _augmented, asked = _run_fetch(
        monkeypatch,
        "잠실역",
        {"잠실역": [_doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", "")]},
    )
    assert asked == ["잠실역"]
