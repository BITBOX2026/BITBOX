"""Contract tests for the BIT_REACT feat/info frontend."""

import asyncio

from app.api.gateway import _build_upload_compat_response
from app.api.schemas import ProcessResponse, UploadCompatResponse
from app.routers.bus import router as bus_router
from app.services import pipeline
from app.services.core.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
    SEOUL_STATION_ARRIVAL_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.core.service_types import (
    ParsedIntent,
    RouteSegment,
    TransportResult,
    ValidationResult,
)
from app.services.transit import transport_service
from app.services.transit.odsay_service import _extract_route_segments


def test_process_schema_preserves_all_arrival_fields() -> None:
    response = ProcessResponse.model_validate(
        {
            "status": "success",
            "message": "도착 안내",
            "data": {
                "arrival_time": "3분후",
                "arrival_time_2": "12분후",
                "first_bus_time": "05:30",
            },
        }
    ).model_dump()

    assert response["data"]["arrival_time"] == "3분후"
    assert response["data"]["arrival_time_2"] == "12분후"
    assert response["data"]["first_bus_time"] == "05:30"


def test_upload_compat_response_exposes_arrival_fields() -> None:
    response = _build_upload_compat_response(
        {
            "status": "success",
            "message": "3214번 도착 안내",
            "data": {
                "intent": "arrival",
                "stop_name": "올림픽공원역",
                "bus_number": "3214",
                "arrival_time": "3분후",
                "arrival_time_2": "12분후",
                "first_bus_time": "05:30",
            },
        }
    )
    serialized = UploadCompatResponse.model_validate(response).model_dump()

    assert serialized["destination"] == "올림픽공원역"
    assert serialized["arrival_time"] == "3분후"
    assert serialized["arrival_time_2"] == "12분후"
    assert serialized["first_bus_time"] == "05:30"
    assert serialized["buses"][0]["arrivalMin"] == 3


def test_upload_compat_route_exposes_route_detail_for_frontend() -> None:
    response = _build_upload_compat_response(
        {
            "status": "success",
            "message": "146번을 타세요.",
            "data": {
                "intent": "route",
                "origin": "서울역",
                "origin_x": 126.972,
                "origin_y": 37.556,
                "destination": "강남역",
                "destination_x": 127.027,
                "destination_y": 37.498,
                "bus_number": "146",
                "arrival_time": "3분후",
                "total_time_min": 35,
                "route_segments": [
                    {
                        "vehicle_type": "버스",
                        "line": "146번",
                        "start_name": "서울역",
                        "end_name": "강남역",
                        "time_min": 35,
                        "start_x": 126.972,
                        "start_y": 37.556,
                        "end_x": 127.027,
                        "end_y": 37.498,
                    }
                ],
            },
        }
    )

    bus = response["buses"][0]
    assert bus["busNumber"] == "146"
    assert bus["arrivalMin"] == 3
    assert bus["routeDetail"]["totalMin"] == 35
    assert bus["routeDetail"]["origin_x"] == 126.972
    assert bus["routeDetail"]["route_segments"][0]["line"] == "146번"


def test_typed_route_uses_same_frontend_contract(monkeypatch) -> None:
    async def search(_parsed: ParsedIntent, request_id: str = ""):
        return TransportResult(
            origin="서울시청",
            destination="강남역",
            transport_mode="bus",
            bus_number="402",
            total_time_min=28,
            route_segments=[
                RouteSegment(
                    vehicle_type="버스",
                    line="402번",
                    start_name="시청앞",
                    end_name="강남역",
                    time_min=28,
                )
            ],
            source="odsay",
        )

    async def no_tts(_text: str, request_id: str):
        return None

    monkeypatch.setattr(pipeline, "search_transport_info", search)
    monkeypatch.setattr(pipeline, "_generate_tts_audio_safely", no_tts)

    result = asyncio.run(
        pipeline.run_text_route("강남역", origin="서울시청", request_id="typed-route")
    )
    compat = _build_upload_compat_response(result)

    assert compat["success"] is True
    assert compat["destination"] == "강남역"
    assert compat["buses"][0]["busNumber"] == "402"
    assert compat["buses"][0]["routeDetail"]["totalMin"] == 28


def test_default_bus_route_omits_none_fields_for_javascript_comparison() -> None:
    route = next(route for route in bus_router.routes if route.path == "/default")
    assert route.response_model_exclude_none is True


def test_seoul_bus_urls_use_reachable_http_endpoint() -> None:
    urls = (
        SEOUL_BUS_ARRIVAL_URL,
        SEOUL_BUS_ROUTE_SEARCH_URL,
        SEOUL_ROUTE_STATION_URL,
        SEOUL_STATION_ARRIVAL_URL,
        SEOUL_STATION_SEARCH_URL,
    )
    assert all(url.startswith("http://ws.bus.go.kr/api/rest/") for url in urls)


def test_odsay_segments_exclude_walks_rendered_by_frontend() -> None:
    segments = _extract_route_segments(
        [
            {
                "trafficType": 3,
                "distance": 120,
                "time": 2,
                "startName": "출발지",
                "endName": "정류장",
            },
            {
                "trafficType": 2,
                "time": 10,
                "startName": "올림픽공원역",
                "endName": "잠실역",
                "lane": [{"busNo": "3214"}],
            },
        ]
    )

    assert segments is not None
    assert [(segment.vehicle_type, segment.line) for segment in segments] == [
        ("버스", "3214번")
    ]


def test_route_arrival_uses_first_boarding_bus_and_stop_fallback(monkeypatch) -> None:
    async def no_default_arrival(_bus_number: str):
        return None, None

    async def arrival_at_boarding_stop(bus_number: str, stop_name: str):
        assert bus_number == "N13"
        assert stop_name == "서울역버스환승센터"
        return "4분후", "15분후"

    monkeypatch.setattr(
        transport_service,
        "fetch_arrival_at_default_stop",
        no_default_arrival,
    )
    monkeypatch.setattr(
        transport_service,
        "fetch_arrival_at_stop",
        arrival_at_boarding_stop,
    )

    result = TransportResult(
        bus_number="402",
        route_segments=[
            RouteSegment(
                vehicle_type="버스",
                line="N13번",
                start_name="서울역버스환승센터",
                end_name="강남역",
            ),
            RouteSegment(
                vehicle_type="버스",
                line="402번",
                start_name="강남역",
                end_name="양재역",
            ),
        ],
    )

    enriched = asyncio.run(
        transport_service._enrich_arrival_time(
            result,
            ParsedIntent(intent="route", origin_text=None),
            "test-request",
        )
    )

    assert enriched.bus_number == "N13"
    assert enriched.stop_name == "서울역버스환승센터"
    assert enriched.arrival_time == "4분후"
    assert enriched.arrival_time_2 == "15분후"


def test_arrival_intent_uses_stop_name_as_frontend_destination(monkeypatch) -> None:
    parsed = ParsedIntent(
        intent="arrival",
        stop_text="올림픽공원역",
        bus_number="3214",
        transport_mode="bus",
        confidence=0.98,
    )

    async def transcribe(**_kwargs):
        return "올림픽공원역 3214번 언제 와"

    async def parse(_transcript: str, request_id: str = ""):
        return parsed

    async def search(_parsed: ParsedIntent, request_id: str = ""):
        return TransportResult(
            stop_name="올림픽공원역",
            transport_mode="bus",
            bus_number="3214",
            arrival_time="3분후",
            source="public_data",
        )

    monkeypatch.setattr(pipeline, "transcribe_audio", transcribe)
    monkeypatch.setattr(pipeline, "parse_transit_intent", parse)
    monkeypatch.setattr(
        pipeline,
        "validate_parsed_intent",
        lambda _parsed: ValidationResult(is_valid=True, message=""),
    )
    monkeypatch.setattr(pipeline, "search_transport_info", search)

    result = asyncio.run(pipeline._run_pipeline_core(b"audio", "audio.webm", "test"))

    assert result["status"] == "success"
    assert result["data"]["destination"] == "올림픽공원역"
    assert result["data"]["arrival_time"] == "3분후"
