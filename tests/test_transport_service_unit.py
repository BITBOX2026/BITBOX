import pytest

from app.services.odsay_service import (
    _calculate_transfer_count,
    _extract_route_segments,
    _is_night_bus_number,
    _safe_int,
    _select_best_path,
)


class TestSafeInt:
    def test_integer(self):
        assert _safe_int(42) == 42

    def test_numeric_string(self):
        assert _safe_int("42") == 42

    def test_none(self):
        assert _safe_int(None) is None

    def test_invalid_string(self):
        assert _safe_int("abc") is None

    def test_float_truncated(self):
        assert _safe_int(3.9) == 3


class TestIsNightBusNumber:
    def test_night_bus(self):
        assert _is_night_bus_number("N73") is True
        assert _is_night_bus_number("n75") is True

    def test_regular_bus(self):
        assert _is_night_bus_number("740") is False
        assert _is_night_bus_number("8001") is False
        assert _is_night_bus_number("402") is False


class TestCalculateTransferCount:
    def test_bus_only_single(self):
        assert _calculate_transfer_count(1, 0) == 0

    def test_subway_only_single(self):
        assert _calculate_transfer_count(0, 1) == 0

    def test_bus_and_subway(self):
        assert _calculate_transfer_count(1, 1) == 1

    def test_two_bus_segments(self):
        assert _calculate_transfer_count(2, 0) == 1

    def test_triple_transfer(self):
        assert _calculate_transfer_count(2, 1) == 2

    def test_both_none(self):
        assert _calculate_transfer_count(None, None) is None

    def test_one_none(self):
        assert _calculate_transfer_count(1, None) == 0


class TestSelectBestPath:
    @staticmethod
    def _make_path(
        total_time: int,
        bus_no: str | None = None,
        subway_code: int | None = None,
    ) -> dict:
        sub_paths = []
        bus_count = 0
        subway_count = 0

        if bus_no:
            sub_paths.append({"trafficType": 2, "lane": [{"busNo": bus_no}]})
            bus_count = 1
        if subway_code:
            sub_paths.append({"trafficType": 1, "lane": [{"subwayCode": subway_code}]})
            subway_count = 1

        return {
            "pathType": 3,
            "info": {
                "totalTime": total_time,
                "busTransitCount": bus_count,
                "subwayTransitCount": subway_count,
                "payment": 1500,
            },
            "subPath": sub_paths,
        }

    def _payload(self, paths: list) -> dict:
        return {"result": {"path": paths}}

    def test_selects_fastest_path(self):
        payload = self._payload([
            self._make_path(40, bus_no="740"),
            self._make_path(30, bus_no="402"),
            self._make_path(50, bus_no="146"),
        ])
        best = _select_best_path(payload, "bus")
        assert best["info"]["totalTime"] == 30

    def test_bus_mode_excludes_subway_only(self):
        payload = self._payload([self._make_path(20, subway_code=2)])
        assert _select_best_path(payload, "bus") is None

    def test_subway_mode_excludes_bus_only(self):
        payload = self._payload([
            self._make_path(30, bus_no="740"),
            self._make_path(40, subway_code=2),
        ])
        best = _select_best_path(payload, "subway")
        assert best["info"]["totalTime"] == 40

    def test_night_bus_fallback_when_no_regular(self):
        payload = self._payload([self._make_path(60, bus_no="N73")])
        best = _select_best_path(payload, "bus")
        assert best is not None

    def test_regular_bus_preferred_over_night(self):
        payload = self._payload([
            self._make_path(60, bus_no="N73"),
            self._make_path(70, bus_no="402"),
        ])
        best = _select_best_path(payload, "bus")
        # 402번이 있는 경로는 regular_bus_paths에 포함 → 선택돼야 함
        sub_paths = best["subPath"]
        bus_nos = [sp["lane"][0]["busNo"] for sp in sub_paths if sp["trafficType"] == 2]
        assert "402" in bus_nos

    def test_empty_paths_returns_none(self):
        assert _select_best_path({"result": {"path": []}}, "bus") is None

    def test_missing_result_returns_none(self):
        assert _select_best_path({}, "bus") is None


class TestExtractRouteSegments:
    def test_single_bus_segment(self):
        sub_paths = [
            {"trafficType": 3, "startName": "출발", "endName": "정류장"},
            {
                "trafficType": 2,
                "startName": "서울역",
                "endName": "강남역",
                "lane": [{"busNo": "740"}],
            },
            {"trafficType": 3, "startName": "강남역", "endName": "목적지"},
        ]
        segments = _extract_route_segments(sub_paths)
        assert segments is not None
        assert len(segments) == 1
        assert segments[0].vehicle_type == "버스"
        assert segments[0].line == "740번"
        assert segments[0].start_name == "서울역"
        assert segments[0].end_name == "강남역"

    def test_single_subway_segment(self):
        sub_paths = [
            {
                "trafficType": 1,
                "startName": "서울역",
                "endName": "강남역",
                "lane": [{"subwayCode": 2}],
            }
        ]
        segments = _extract_route_segments(sub_paths)
        assert segments is not None
        assert segments[0].vehicle_type == "지하철"
        assert segments[0].line == "2호선"

    def test_bus_and_subway_transfer(self):
        sub_paths = [
            {
                "trafficType": 2,
                "startName": "서울역",
                "endName": "사당역",
                "lane": [{"busNo": "740"}],
            },
            {
                "trafficType": 1,
                "startName": "사당역",
                "endName": "강남역",
                "lane": [{"subwayCode": 4}],
            },
        ]
        segments = _extract_route_segments(sub_paths)
        assert segments is not None
        assert len(segments) == 2
        assert segments[0].vehicle_type == "버스"
        assert segments[1].vehicle_type == "지하철"
        assert segments[1].line == "4호선"

    def test_walk_only_returns_none(self):
        sub_paths = [
            {"trafficType": 3, "startName": "a", "endName": "b"}
        ]
        assert _extract_route_segments(sub_paths) is None

    def test_unknown_subway_code_fallback(self):
        sub_paths = [
            {
                "trafficType": 1,
                "startName": "a",
                "endName": "b",
                "lane": [{"subwayCode": 999}],
            }
        ]
        segments = _extract_route_segments(sub_paths)
        assert segments is not None
        assert "999호선" in segments[0].line
