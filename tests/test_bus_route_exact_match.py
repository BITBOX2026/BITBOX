import asyncio

import pytest

from app.services.ai import llm_service
from app.services.ai.korean_number_normalizer import normalize_bus_number_token
from app.services.core.service_types import ParsedIntent
from app.services.transit import public_bus_service


def test_bus_number_token_recovers_spoken_digits_without_suffix() -> None:
    """`번` 접미사가 빠져도 버스 번호로 식별된 토큰은 복구되어야 합니다.

    실제 STT가 "삼사이삼 버스 언제 와요?"처럼 `번`을 누락하면 문장 단위
    정규화가 동작하지 않아 한국어 수사가 그대로 조회에 사용되었습니다.
    """
    assert normalize_bus_number_token("삼사이삼") == "3423"
    assert normalize_bus_number_token("삼사일이") == "3412"
    assert normalize_bus_number_token("삼천사백십삼") == "3413"
    assert normalize_bus_number_token("삼사이삼번") == "3423"
    # STT가 앞부분만 숫자로 받아쓴 혼합 표기도 복구되어야 합니다.
    assert normalize_bus_number_token("3400 열두") == "3412"
    assert normalize_bus_number_token("3300 스무세") == "3323"


def test_stt_thousands_separator_does_not_truncate_bus_number() -> None:
    """실제 STT는 "삼천사백십삼번"을 `3,413번`으로 받아쓰는 경우가 있습니다.

    쉼표를 지우지 않으면 추출 정규식이 뒤쪽 `413`만 잡아 전혀 다른 노선을
    조회하게 되므로, 천 단위 쉼표만 제거되는지 확인합니다.
    """
    from app.services.ai.korean_number_normalizer import normalize_spoken_bus_numbers
    from app.services.ai.llm_service import _extract_bus_number

    assert _extract_bus_number(normalize_spoken_bus_numbers("3,413번 버스 언제 와요?")) == "3413"
    assert _extract_bus_number(normalize_spoken_bus_numbers("3,412번")) == "3412"
    assert normalize_bus_number_token("3,413") == "3413"
    # 나열을 뜻하는 쉼표는 지우지 않습니다.
    assert normalize_spoken_bus_numbers("3, 4번 중에") == "3, 4번 중에"


def test_ambiguous_or_overlong_bus_numbers_require_reconfirmation() -> None:
    """목록과 5자리 이상 값은 일부 숫자를 버스 번호로 확정하지 않습니다."""
    from app.services.ai.korean_number_normalizer import normalize_spoken_bus_numbers

    for transcript in (
        "3, 4번 중에 언제 와요",
        "3번 또는 4번 중에 언제 와요",
        "12,345번 언제 와요",
    ):
        normalized = normalize_spoken_bus_numbers(transcript)
        assert llm_service._extract_bus_number(normalized) is None
        parsed = asyncio.run(llm_service.parse_transit_intent(transcript))
        assert parsed.intent == "unknown"
        assert parsed.bus_number is None


def test_numeric_extractor_never_takes_suffix_from_named_routes() -> None:
    """영문 접두 노선은 숫자 노선으로 잘라 확정하지 않습니다."""
    assert llm_service._extract_bus_number("N13번 언제 와요") is None
    assert llm_service._extract_bus_number("M5333번 언제 와요") is None
    assert llm_service._extract_bus_number("3413번 언제 와요") == "3413"


@pytest.mark.parametrize(
    ("transcript", "llm_number", "expected"),
    [
        ("M5333번 언제 와요", "5333", "M5333"),
        ("N13번 언제 와요", "13", "N13"),
        ("30-5하남 버스 언제 와요", "30-5하남", "30-5하남"),
    ],
)
def test_llm_path_preserves_explicit_named_route(
    monkeypatch,
    transcript: str,
    llm_number: str,
    expected: str,
) -> None:
    async def fake_call_llm(*_args, **_kwargs) -> ParsedIntent:
        return ParsedIntent(
            intent="arrival",
            transport_mode="bus",
            bus_number=llm_number,
            confidence=0.9,
        )

    monkeypatch.setattr(llm_service, "_call_llm", fake_call_llm)
    monkeypatch.setattr(llm_service, "get_bool_setting", lambda *_args: False)
    monkeypatch.setattr(llm_service, "is_mock_mode", lambda: False)
    monkeypatch.setattr(
        llm_service,
        "get_setting",
        lambda name, default=None: "configured" if name == "OPENAI_API_KEY" else default,
    )
    monkeypatch.setattr(llm_service, "_get_openai_client", object)

    parsed = asyncio.run(llm_service.parse_transit_intent(transcript))
    assert parsed.intent == "arrival"
    assert parsed.bus_number == expected


def test_llm_conflict_with_hyphenated_route_requires_reconfirmation() -> None:
    parsed = llm_service._preserve_explicit_named_bus_number(
        "30-5하남 버스 언제 와요",
        ParsedIntent(intent="arrival", bus_number="305", confidence=0.9),
    )
    assert parsed == ParsedIntent()
    assert llm_service._extract_explicit_named_bus_numbers("30-5하남번 언제 와요") == [
        "30-5하남"
    ]
    assert llm_service._has_ambiguous_bus_number_expression(
        "M5333번 또는 5333번 중에"
    )


def test_bus_number_token_never_invents_a_number() -> None:
    """숫자로 확정할 수 없는 값은 임의 변환하지 않아야 합니다."""
    for untouched in ("3사리", "30-5하남", "N13", "M5333", "간선", "3400 하남", "5호선"):
        assert normalize_bus_number_token(untouched) == untouched
    assert normalize_bus_number_token(None) is None
    assert normalize_bus_number_token("3423") == "3423"


def test_bus_route_search_does_not_fall_back_to_similar_number(monkeypatch) -> None:
    async def fake_payload(*_args, **_kwargs):
        return {
            "msgBody": {
                "itemList": [
                    {"busRouteId": "1", "busRouteNm": "3412"},
                    {"busRouteId": "2", "busRouteNm": "340"},
                ]
            }
        }

    monkeypatch.setattr(public_bus_service, "request_seoul_bus_payload", fake_payload)
    assert asyncio.run(public_bus_service.search_bus_route("3400")) is None


def test_bus_route_search_selects_only_exact_number(monkeypatch) -> None:
    async def fake_payload(*_args, **_kwargs):
        return {
            "msgBody": {
                "itemList": [
                    {"busRouteId": "1", "busRouteNm": "3412"},
                    {"busRouteId": "2", "busRouteNm": "3400"},
                ]
            }
        }

    monkeypatch.setattr(public_bus_service, "request_seoul_bus_payload", fake_payload)
    selected = asyncio.run(public_bus_service.search_bus_route("3400"))
    assert selected and selected["busRouteId"] == "2"
