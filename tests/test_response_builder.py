import pytest

from app.services.response_builder import (
    _format_arrival_time,
    _is_night_bus,
    _josa_reul,
    _josa_ro,
    build_user_message,
)
from app.services.core.service_types import ParsedIntent, RouteSegment, TransportResult


def _route_parsed(**kwargs) -> ParsedIntent:
    defaults: dict = {"intent": "route", "transport_mode": "bus", "confidence": 0.9}
    defaults.update(kwargs)
    return ParsedIntent(**defaults)


def _route_result(**kwargs) -> TransportResult:
    defaults = {"origin": "서울역", "destination": "강남역", "source": "odsay"}
    return TransportResult(**{**defaults, **kwargs})


# ── 조사 헬퍼 ─────────────────────────────────────────────────────────────────

class TestJosaHelpers:
    def test_reul_no_jongseong(self):
        assert _josa_reul("버스") == "를"

    def test_reul_with_jongseong(self):
        assert _josa_reul("2호선") == "을"

    def test_ro_no_jongseong(self):
        assert _josa_ro("버스") == "로"

    def test_ro_rieul_jongseong(self):
        assert _josa_ro("서울") == "로"

    def test_ro_other_jongseong(self):
        assert _josa_ro("2호선") == "으로"

    def test_ro_airport_rail(self):
        assert _josa_ro("공항철도") == "로"


# ── 야간버스 감지 ──────────────────────────────────────────────────────────────

class TestIsNightBus:
    def test_night_bus_upper(self):
        assert _is_night_bus("N73") is True

    def test_night_bus_lower(self):
        assert _is_night_bus("n75번") is True

    def test_regular_bus(self):
        assert _is_night_bus("740") is False
        assert _is_night_bus("8001") is False


# ── 경로 안내 문장 ─────────────────────────────────────────────────────────────

class TestBuildRouteMessage:
    def test_single_bus_segment_contains_key_info(self):
        parsed = _route_parsed()
        result = _route_result(
            route_segments=[RouteSegment("버스", "740번", "서울역", "강남역")],
            total_time_min=38,
            payment=1650,
        )
        msg = build_user_message(parsed, result)
        assert "서울역" in msg
        assert "740번 버스" in msg
        assert "강남역" in msg
        assert "38분" in msg
        assert "1,650원" in msg

    def test_single_subway_segment(self):
        parsed = _route_parsed(transport_mode="subway")
        result = _route_result(
            route_segments=[RouteSegment("지하철", "2호선", "서울역", "강남역")],
            total_time_min=33,
            payment=1650,
        )
        msg = build_user_message(parsed, result)
        assert "2호선" in msg
        assert "33분" in msg
        assert "1,650원" in msg

    def test_transfer_contains_all_stations(self):
        parsed = _route_parsed(transport_mode="transit")
        result = _route_result(
            route_segments=[
                RouteSegment("버스", "740번", "서울역", "사당역"),
                RouteSegment("지하철", "4호선", "사당역", "강남역"),
            ],
            total_time_min=41,
            payment=1650,
        )
        msg = build_user_message(parsed, result)
        assert "서울역" in msg
        assert "740번" in msg
        assert "사당역" in msg
        assert "4호선" in msg
        assert "강남역" in msg

    def test_night_bus_label_in_message(self):
        parsed = _route_parsed()
        result = _route_result(
            route_segments=[RouteSegment("버스", "N73번", "잠실역", "홍대입구역")],
            total_time_min=65,
            payment=2500,
        )
        msg = build_user_message(parsed, result)
        assert "야간버스" in msg

    def test_payment_formatted_with_comma(self):
        parsed = _route_parsed()
        result = _route_result(
            route_segments=[RouteSegment("버스", "8001번", "잠실역", "강남역")],
            total_time_min=22,
            payment=3450,
        )
        msg = build_user_message(parsed, result)
        assert "3,450원" in msg

    def test_missing_origin(self):
        parsed = _route_parsed()
        result = _route_result(origin=None)
        msg = build_user_message(parsed, result)
        assert "출발지" in msg

    def test_missing_destination(self):
        parsed = _route_parsed()
        result = _route_result(destination=None)
        msg = build_user_message(parsed, result)
        assert "목적지" in msg

    def test_fallback_bus_no_segments(self):
        parsed = _route_parsed()
        result = _route_result(bus_number="402", total_time_min=30, payment=1500)
        msg = build_user_message(parsed, result)
        assert "402번" in msg
        assert "서울역" in msg

    def test_time_only(self):
        parsed = _route_parsed()
        result = _route_result(
            route_segments=[RouteSegment("버스", "402번", "서울역", "강남역")],
            total_time_min=20,
            payment=None,
        )
        msg = build_user_message(parsed, result)
        assert "20분" in msg
        assert "원" not in msg

    def test_payment_only(self):
        parsed = _route_parsed()
        result = _route_result(
            route_segments=[RouteSegment("버스", "402번", "서울역", "강남역")],
            total_time_min=None,
            payment=1500,
        )
        msg = build_user_message(parsed, result)
        assert "1,500원" in msg
        assert "분" not in msg


# ── 도착 안내 문장 ─────────────────────────────────────────────────────────────

class TestBuildArrivalMessage:
    def _arrival_parsed(self) -> ParsedIntent:
        return ParsedIntent(intent="arrival", transport_mode="bus", confidence=0.9)

    def test_normal_arrival(self):
        result = TransportResult(
            stop_name="서울역", bus_number="402",
            arrival_time="3분 후", source="public_data"
        )
        msg = build_user_message(self._arrival_parsed(), result)
        assert "서울역" in msg
        assert "402" in msg
        assert "3분" in msg

    @pytest.mark.parametrize("status,expected_fragment", [
        ("출발대기", "출발 대기"),
        ("곧 도착", "곧 도착 예정"),
        ("운행종료", "종료"),
    ])
    def test_special_arrival_texts(self, status: str, expected_fragment: str):
        result = TransportResult(
            stop_name="서울역", bus_number="402",
            arrival_time=status, source="public_data"
        )
        msg = build_user_message(self._arrival_parsed(), result)
        assert "402" in msg
        assert expected_fragment in msg

    def test_missing_stop_name(self):
        result = TransportResult(bus_number="402", arrival_time="3분 후", source="public_data")
        msg = build_user_message(self._arrival_parsed(), result)
        assert "정류장" in msg

    def test_missing_bus_number(self):
        result = TransportResult(stop_name="서울역", arrival_time="3분 후", source="public_data")
        msg = build_user_message(self._arrival_parsed(), result)
        assert "버스 번호" in msg


# ── 도착 시간 포맷 ─────────────────────────────────────────────────────────────

class TestFormatArrivalTime:
    def test_already_formatted(self):
        assert _format_arrival_time("약 3분 후") == "약 3분 후"

    def test_digit_without_후(self):
        result = _format_arrival_time("5분")
        assert result.startswith("약 ")
        assert "5분" in result
        assert "후" in result

    def test_digit_with_후(self):
        result = _format_arrival_time("3분 후")
        assert result.startswith("약 ")
        assert "후" in result
        assert result.count("후") == 1  # 중복 없음
