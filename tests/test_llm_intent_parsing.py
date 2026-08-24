"""
음성 → intent 변환 파이프라인 중 규칙 기반(mock) 파서의 단위 테스트.

_mock_parse_transit_intent와 그 하위 정규식 헬퍼들은 OpenAI 호출 없이도
항상 실행되는 fast-path이므로 (INTENT_FAST_PATH_ENABLED=True가 기본값),
외부 API/환경변수 상태와 무관하게 순수 함수로 테스트할 수 있습니다.
"""

import asyncio

import pytest

from app.services.ai import llm_service
from app.services.core.service_types import ParsedIntent


# ---------------------------------------------------------------------------
# _extract_bus_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("146번 버스 언제 와요", "146"),
        ("740 번 버스 타야 해요", "740"),
        ("3400 열두 번 버스 언제 와요", None),
        ("서울역에서 강남역까지 가는 버스 알려줘", None),
        ("", None),
    ],
)
def test_extract_bus_number(text: str, expected: str | None) -> None:
    assert llm_service._extract_bus_number(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3400 열두 번", "3412번"),
        ("3300 스무세 번", "3323번"),
        ("삼천사백이십삼 번", "3423번"),
        ("삼사일삼 번", "3413번"),
        ("146번", "146번"),
    ],
)
def test_normalize_mixed_spoken_bus_number(text: str, expected: str) -> None:
    assert llm_service.normalize_spoken_bus_numbers(text) == expected


def test_parse_transit_intent_uses_normalized_bus_number(monkeypatch) -> None:
    monkeypatch.setattr(llm_service, "get_bool_setting", lambda name, default=True: True)
    parsed = asyncio.run(
        llm_service.parse_transit_intent("올림픽공원역에서 3400 열두 번 언제 도착해요")
    )
    assert parsed.intent == "arrival"
    assert parsed.stop_text == "올림픽공원역"
    assert parsed.bus_number == "3412"


# ---------------------------------------------------------------------------
# _extract_transport_mode
# ---------------------------------------------------------------------------

def test_extract_transport_mode_prefers_bus_number_over_missing_keyword() -> None:
    assert llm_service._extract_transport_mode("정류장에 가주세요", "146") == "bus"


def test_extract_transport_mode_detects_subway_keyword() -> None:
    assert llm_service._extract_transport_mode("지하철로 강남역 가는 길", None) == "subway"


def test_extract_transport_mode_defaults_to_bus() -> None:
    assert llm_service._extract_transport_mode("아무 말이나", None) == "bus"


# ---------------------------------------------------------------------------
# _extract_route_places
# ---------------------------------------------------------------------------

def test_extract_route_places_finds_origin_and_destination() -> None:
    origin, destination = llm_service._extract_route_places("서울역에서 강남역까지 가는 길")
    assert origin == "서울역"
    assert destination == "강남역"


def test_extract_route_places_handles_origin_only_sentence() -> None:
    origin, destination = llm_service._extract_route_places("잠실역에서 가고 싶어요")
    assert origin == "잠실역"
    assert destination is None


def test_extract_route_places_returns_none_when_no_pattern_matches() -> None:
    assert llm_service._extract_route_places("안녕하세요") == (None, None)


# ---------------------------------------------------------------------------
# _extract_destination (목적지만 있는 문장)
# ---------------------------------------------------------------------------

def test_extract_destination_from_destination_only_sentence() -> None:
    assert llm_service._extract_destination("강남역 가는 버스 뭐예요") == "강남역"


def test_extract_destination_returns_none_for_unrelated_sentence() -> None:
    assert llm_service._extract_destination("오늘 날씨 어때요") is None


# ---------------------------------------------------------------------------
# _clean_place_text — 부분 문자열 보호 확인 (예: "버스터미널"의 "버스"는 유지)
# ---------------------------------------------------------------------------

def test_clean_place_text_strips_standalone_filler_words() -> None:
    assert llm_service._clean_place_text("저는 버스 서울역") == "서울역"


def test_clean_place_text_preserves_substring_matches() -> None:
    assert llm_service._clean_place_text("버스터미널") == "버스터미널"


# ---------------------------------------------------------------------------
# _safe_confidence / _normalize_transport_mode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.5, 0.5),
        (1.5, 1.0),
        (-0.3, 0.0),
        ("not-a-number", 0.0),
        (None, 0.0),
    ],
)
def test_safe_confidence_clamps_to_valid_range(value: object, expected: float) -> None:
    assert llm_service._safe_confidence(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bus", "bus"),
        ("subway", "subway"),
        ("unknown", "unknown"),
        ("walk", "unknown"),
        (None, "unknown"),
    ],
)
def test_normalize_transport_mode_rejects_unexpected_values(value: object, expected: str) -> None:
    assert llm_service._normalize_transport_mode(value) == expected


# ---------------------------------------------------------------------------
# _mock_parse_transit_intent — 전체 규칙 기반 파서 시나리오
# ---------------------------------------------------------------------------

def test_mock_parse_detects_arrival_intent_with_stop_and_bus_number() -> None:
    parsed = llm_service._mock_parse_transit_intent("몽촌토성역에서 146번 버스 언제 도착해요")
    assert parsed.intent == "arrival"
    assert parsed.bus_number == "146"
    assert parsed.stop_text == "몽촌토성역"
    assert parsed.confidence >= 0.8


def test_mock_parse_detects_route_intent_with_origin_and_destination() -> None:
    parsed = llm_service._mock_parse_transit_intent("서울역에서 강남역까지 가는 버스 알려줘")
    assert parsed.intent == "route"
    assert parsed.origin_text == "서울역"
    assert parsed.destination_text == "강남역"
    assert parsed.transport_mode == "bus"


def test_mock_parse_detects_route_intent_with_destination_only() -> None:
    parsed = llm_service._mock_parse_transit_intent("강남역 가는 버스 알려줘")
    assert parsed.intent == "route"
    assert parsed.origin_text is None
    assert parsed.destination_text == "강남역"


def test_mock_parse_falls_back_to_bus_number_only_arrival() -> None:
    parsed = llm_service._mock_parse_transit_intent("146번")
    assert parsed.intent == "arrival"
    assert parsed.bus_number == "146"
    assert parsed.confidence < 0.8  # 낮은 신뢰도 — 확인 절차가 필요함을 표시


def test_mock_parse_returns_unknown_intent_for_unrelated_speech() -> None:
    parsed = llm_service._mock_parse_transit_intent("오늘 날씨가 참 좋네요")
    assert parsed.intent == "unknown"
    assert parsed.destination_text is None
    assert parsed.bus_number is None


# ---------------------------------------------------------------------------
# _is_unambiguous — fast-path 게이트 조건
# ---------------------------------------------------------------------------

def test_is_unambiguous_requires_high_confidence_route() -> None:
    confident = ParsedIntent(intent="route", destination_text="강남역", confidence=0.85)
    unsure = ParsedIntent(intent="route", destination_text="강남역", confidence=0.5)
    assert llm_service._is_unambiguous(confident) is True
    assert llm_service._is_unambiguous(unsure) is False


def test_is_unambiguous_requires_bus_number_for_arrival() -> None:
    missing_bus = ParsedIntent(intent="arrival", bus_number=None, confidence=0.9)
    assert llm_service._is_unambiguous(missing_bus) is False


def test_is_unambiguous_rejects_unknown_intent() -> None:
    unknown = ParsedIntent(intent="unknown", confidence=1.0)
    assert llm_service._is_unambiguous(unknown) is False


# ---------------------------------------------------------------------------
# parse_transit_intent — fast path는 OpenAI 호출 없이 즉시 반환되어야 함
# ---------------------------------------------------------------------------

def test_parse_transit_intent_uses_fast_path_for_unambiguous_route(monkeypatch) -> None:
    monkeypatch.setattr(llm_service, "get_bool_setting", lambda name, default=True: True)
    result = asyncio.run(llm_service.parse_transit_intent("서울역에서 강남역까지 가는 버스 알려줘"))
    assert result.intent == "route"
    assert result.destination_text == "강남역"


def test_parse_transit_intent_returns_empty_intent_for_blank_transcript() -> None:
    result = asyncio.run(llm_service.parse_transit_intent("   "))
    assert result == ParsedIntent()
