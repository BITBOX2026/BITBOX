from app.services.transit.kakao_service import (
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
