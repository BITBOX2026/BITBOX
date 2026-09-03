import asyncio

import pytest

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


def test_parking_is_not_mistaken_for_a_station_or_bus_stop() -> None:
    """Kakao의 주차장 분류에도 `교통`이 있지만 목적지 교통시설은 아닙니다."""
    parking = [
        _doc("잠실역 공영주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
    ]
    bus_stop = [
        _doc("잠실역.롯데월드", "", "교통,수송 > 교통시설 > 버스정류장", ""),
    ]
    assert _has_transit_document(parking) is False
    assert _has_transit_document(bus_stop) is True


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


def test_parking_result_does_not_suppress_the_station_lookup(monkeypatch) -> None:
    """첫 결과가 주차장뿐이어도 `<질의>역` 보조 검색은 계속해야 합니다."""
    documents, augmented, asked = _run_fetch(
        monkeypatch,
        "잠실",
        {
            "잠실": [
                _doc("잠실역 공영주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
            ],
            "잠실역": [
                _doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", ""),
            ],
        },
    )
    assert asked == ["잠실", "잠실역"]
    assert [document["place_name"] for document in documents] == [
        "잠실역 공영주차장",
        "잠실역 2호선",
    ]
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


def test_a_weak_match_is_confirmed_even_when_it_wins_clearly() -> None:
    """1등이 확실해도 이름이 약하게만 맞으면 묻고 넘어갑니다.

    예전 규칙은 "점수가 낮고 **동시에** 2위와 비슷할 때"만 물었습니다. 그래서 오답이
    큰 차이로 1등이면 그냥 지나갔고, 실제로 "없는곳"이 미용실 `헤어나올수없는곳`
    으로, "여의도 가자"가 주류도매 `가자주류 여의도역점`으로 확인 없이 갔습니다.
    """
    ranked = [
        _doc("헤어나올수없는곳", "", "가정,생활 > 미용 > 미용실", ""),
        _doc("없는게없는집", "FD6", "음식점", ""),
    ]
    assert _needs_place_confirmation("없는곳", ranked) is True


def test_an_exact_match_still_goes_through_without_asking() -> None:
    """이름이 정확히 맞는 곳까지 되물으면 그 자체가 장벽이 됩니다."""
    ranked = [
        _doc("올림픽공원", "AT4", "여행 > 공원", ""),
        _doc("올림픽공원 평화의문", "AT4", "여행 > 관광,명소", ""),
    ]
    assert _needs_place_confirmation("올림픽공원", ranked) is False


def test_merged_station_keeps_its_own_accuracy_rank(monkeypatch) -> None:
    """보조 검색의 1위가 첫 검색의 하위 후보에 밀리면 안 됩니다.

    Kakao 정확도 순위를 점수에 반영하는데, 두 결과를 이어 붙이면 뒤 목록의 1위가
    앞 목록의 5위보다 낮은 순위로 취급됩니다. 그대로 두면 `압구정` 이 `압구정역` 이
    아니라 문화유적 `압구정지` 로, `신림` 이 `신림역` 이 아니라 `신림계곡` 으로 갔습니다.
    """
    documents, augmented, asked = _run_fetch(
        monkeypatch,
        "압구정",
        {
            "압구정": [
                _doc("압구정지", "", "여행 > 관광,명소 > 문화유적", ""),
                _doc("압구정로데오거리", "AT4", "여행 > 관광,명소 > 테마거리", ""),
                _doc("한류스타거리", "AT4", "여행 > 관광,명소 > 테마거리", ""),
                _doc("압구정토끼굴", "AT4", "여행 > 관광,명소 > 테마거리", ""),
                _doc("강남메디컬투어센터", "", "여행 > 관광,명소 > 관광안내소", ""),
            ],
            "압구정역": [
                _doc("압구정역 3호선", "SW8", "교통,수송 > 지하철,전철 > 수도권3호선", ""),
            ],
        },
    )
    assert asked == ["압구정", "압구정역"]
    ranked = _rank_place_documents("압구정", documents)
    assert ranked[0]["place_name"] == "압구정역 3호선"
    assert _needs_place_confirmation("압구정", ranked, augmented) is True


@pytest.mark.parametrize(
    ("query", "wrong_name", "wrong_category", "station_name"),
    [
        ("신림", "신림계곡", "여행 > 관광,명소 > 계곡", "신림역 2호선"),
        ("이태원", "이태원거리", "여행 > 관광,명소 > 테마거리", "이태원역 6호선"),
        ("명동", "명동거리", "여행 > 관광,명소 > 테마거리", "명동역 4호선"),
        ("마곡", "마곡광장", "여행 > 관광,명소 > 광장", "마곡역 5호선"),
    ],
)
def test_reported_area_name_regressions_keep_the_station_first(
    monkeypatch,
    query: str,
    wrong_name: str,
    wrong_category: str,
    station_name: str,
) -> None:
    """운영에서 발견된 지역명 오정렬을 최소 응답으로 영구 고정합니다."""
    documents, augmented, asked = _run_fetch(
        monkeypatch,
        query,
        {
            query: [_doc(wrong_name, "AT4", wrong_category, "")],
            f"{query}역": [
                _doc(station_name, "SW8", "교통,수송 > 지하철,전철", ""),
            ],
        },
    )
    ranked = _rank_place_documents(query, documents)
    assert asked == [query, f"{query}역"]
    assert ranked[0]["place_name"] == station_name
    assert _needs_place_confirmation(query, ranked, augmented) is True


def test_an_unrelated_station_gets_no_transit_bonus() -> None:
    """이름이 질의와 이어지지 않는 역은 교통 가산점을 받지 못합니다.

    보조 검색("<질의>역")은 이름이 겹치지 않는 역까지 데려옵니다. 주차장을 교통
    장소에서 제외해 보조 검색이 더 자주 돌게 되자, `서울시청` 검색에 딸려 온
    `시청역 1호선` 이 이름에 "서울시청" 이 없는데도 가산점만으로 `서울특별시청` 을
    6점 차로 눌렀습니다. 가산점은 "그 장소일 법한 후보" 를 앞세우라는 뜻입니다.
    """
    # Kakao 가 실제로 돌려준 순서 그대로입니다. 순위 보정이 점수에 들어가므로
    # 순서를 바꾸면 실제와 다른 상황을 시험하게 됩니다.
    first_search = [
        _doc("서울특별시청", "PO3", "사회,공공기관 > 지방행정기관 > 시청 > 특별시청", ""),
        _doc("서울특별시청 서소문2청사", "", "사회,공공기관 > 지방행정기관", ""),
        _doc("서울특별시청 서소문청사", "", "사회,공공기관 > 지방행정기관", ""),
        _doc("서울특별시청 서소문청사 주차장", "PK6", "교통,수송 > 교통시설 > 주차장", ""),
        _doc("다이소 서울시청광장점", "", "가정,생활 > 생활용품점 > 다이소", ""),
    ]
    for rank, document in enumerate(first_search):
        document["_bitbox_source_rank"] = rank
    # 보조 검색("서울시청역")이 데려온 역입니다. 자기 검색에서는 1위입니다.
    station = _doc("시청역 1호선", "SW8", "교통,수송 > 지하철,전철 > 수도권1호선", "")
    station["_bitbox_source_rank"] = 0

    ranked = _rank_place_documents("서울시청", first_search + [station])
    assert ranked[0]["place_name"] == "서울특별시청"


def test_a_related_station_still_gets_the_bonus() -> None:
    """이름이 이어지는 역은 계속 앞세웁니다. 위 수정이 `잠실`을 되돌리면 안 됩니다."""
    documents = [
        _doc("잠실한강공원 청소년광장", "", "여행 > 공원", ""),
        _doc("잠실역 2호선", "SW8", "교통,수송 > 지하철,전철 > 수도권2호선", ""),
    ]
    ranked = _rank_place_documents("잠실", documents)
    assert ranked[0]["place_name"] == "잠실역 2호선"
