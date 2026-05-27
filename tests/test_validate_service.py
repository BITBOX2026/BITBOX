import os
from unittest.mock import patch

import pytest

from app.services.core.service_types import ParsedIntent
from app.services.core.settings_helper import clear_settings_cache
from app.services.transit.validate_service import validate_parsed_intent


def _parsed(**kwargs) -> ParsedIntent:
    return ParsedIntent(**kwargs)


class TestValidateUnknownIntent:
    def test_unknown_intent_fails(self):
        result = validate_parsed_intent(_parsed(intent="unknown", confidence=0.9))
        assert result.is_valid is False

    def test_low_confidence_fails(self):
        result = validate_parsed_intent(
            _parsed(intent="route", confidence=0.3, destination_text="강남역")
        )
        assert result.is_valid is False

    def test_exactly_min_confidence_passes(self):
        result = validate_parsed_intent(
            _parsed(
                intent="route", confidence=0.5,
                origin_text="서울역", destination_text="강남역",
                transport_mode="bus",
            )
        )
        assert result.is_valid is True


class TestValidateRoute:
    def test_missing_destination_fails(self):
        with patch.dict(os.environ, {"DEFAULT_ORIGIN_NAME": "서울역"}):
            clear_settings_cache()
            result = validate_parsed_intent(
                _parsed(intent="route", confidence=0.9, origin_text="잠실역")
            )
        assert result.is_valid is False
        assert "목적지" in result.message

    def test_origin_and_dest_passes(self):
        result = validate_parsed_intent(
            _parsed(
                intent="route", confidence=0.9,
                origin_text="서울역", destination_text="강남역",
                transport_mode="bus",
            )
        )
        assert result.is_valid is True

    def test_no_origin_with_default_passes(self):
        with patch.dict(os.environ, {"DEFAULT_ORIGIN_NAME": "잠실역"}):
            clear_settings_cache()
            result = validate_parsed_intent(
                _parsed(
                    intent="route", confidence=0.9,
                    destination_text="강남역", transport_mode="bus",
                )
            )
        assert result.is_valid is True

    def test_no_origin_no_default_fails(self):
        env = {
            "DEFAULT_ORIGIN_NAME": "",
            "DEFAULT_ORIGIN_X": "",
            "DEFAULT_ORIGIN_Y": "",
            "ORIGIN_X": "",
            "ORIGIN_Y": "",
        }
        with patch.dict(os.environ, env):
            clear_settings_cache()
            result = validate_parsed_intent(
                _parsed(intent="route", confidence=0.9, destination_text="강남역")
            )
        assert result.is_valid is False
        assert "출발지" in result.message

    def test_default_coords_pass(self):
        env = {
            "DEFAULT_ORIGIN_NAME": "",
            "DEFAULT_ORIGIN_X": "127.0",
            "DEFAULT_ORIGIN_Y": "37.5",
        }
        with patch.dict(os.environ, env):
            clear_settings_cache()
            result = validate_parsed_intent(
                _parsed(intent="route", confidence=0.9, destination_text="강남역")
            )
        assert result.is_valid is True


class TestValidateArrival:
    def test_missing_bus_number_fails(self):
        result = validate_parsed_intent(
            _parsed(intent="arrival", confidence=0.9, stop_text="서울역")
        )
        assert result.is_valid is False
        assert "버스 번호" in result.message

    def test_missing_stop_fails(self):
        result = validate_parsed_intent(
            _parsed(intent="arrival", confidence=0.9, bus_number="402")
        )
        assert result.is_valid is False
        assert "정류장" in result.message

    def test_bus_and_stop_passes(self):
        result = validate_parsed_intent(
            _parsed(intent="arrival", confidence=0.9, bus_number="402", stop_text="서울역")
        )
        assert result.is_valid is True
