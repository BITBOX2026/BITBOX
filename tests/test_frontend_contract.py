"""Contract tests for the BIT_REACT feat/info frontend."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.api.gateway import _build_upload_compat_response, _looks_like_supported_audio
from app.api.schemas import ProcessResponse, TextRouteRequest, UploadCompatResponse
from app.routers.bus import router as bus_router
from app.services import pipeline
from app.services.bus_service import _extract_arrival_minutes
from app.services.response_builder import build_user_message
from app.services.ai import llm_service
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
from app.services.transit.odsay_service import _extract_route_segments, _select_best_path
from app.services.transit.validate_service import validate_parsed_intent
from app.core import auth
from app.main import app
import app.api.gateway as gateway_module
import app.routers.bus as bus_module
from app.schemas.bus import DefaultBusArrivalItem, DefaultBusArrivalResponse


def test_shared_api_token_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_setting", lambda _name: "kiosk-secret")
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as exc_info:
        auth.verify_api_token(request)

    assert exc_info.value.status_code == 401


def test_shared_api_token_accepts_kiosk_header(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_setting", lambda _name: "kiosk-secret")
    request = Request({
        "type": "http",
        "headers": [(b"x-bitbox-token", b"kiosk-secret")],
    })

    auth.verify_api_token(request)


def test_clear_destination_uses_fast_intent_path(monkeypatch) -> None:
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("clear route intent should not call the LLM")

    monkeypatch.setattr(llm_service, "_call_llm", fail_if_called)

    parsed = asyncio.run(llm_service.parse_transit_intent("강남역 가는 버스 알려줘"))

    assert parsed.intent == "route"
    assert parsed.destination_text == "강남역"
    assert parsed.transport_mode == "bus"


def test_text_route_contract_only_accepts_bus_mode() -> None:
    assert TextRouteRequest(destination="강남역").transport_mode == "bus"
    with pytest.raises(ValidationError):
        TextRouteRequest(destination="강남역", transport_mode="subway")


def test_text_route_coordinates_must_be_a_valid_pair() -> None:
    request = TextRouteRequest(
        destination="강남역 2호선",
        destination_x=127.0276,
        destination_y=37.4979,
    )
    assert request.destination_x == 127.0276
    with pytest.raises(ValidationError):
        TextRouteRequest(destination="강남역", destination_x=127.0276)


def test_text_route_preserves_selected_destination_coordinates(monkeypatch) -> None:
    captured: ParsedIntent | None = None

    async def search(parsed: ParsedIntent, request_id: str = ""):
        nonlocal captured
        captured = parsed
        return TransportResult(
            origin="올림픽공원역",
            destination=parsed.destination_text,
            destination_x=parsed.destination_x,
            destination_y=parsed.destination_y,
            transport_mode="bus",
            bus_number="3412",
            total_time_min=20,
            route_segments=[RouteSegment("버스", "3412번", "올림픽공원역", "강남역")],
        )

    monkeypatch.setattr(pipeline, "search_transport_info", search)
    asyncio.run(
        pipeline.run_text_route(
            "강남역 2호선",
            127.0276,
            37.4979,
            origin="올림픽공원역",
        )
    )

    assert captured is not None
    assert captured.destination_x == 127.0276
    assert captured.destination_y == 37.4979


def test_explicit_subway_voice_request_is_rejected() -> None:
    validation = validate_parsed_intent(
        ParsedIntent(
            intent="route",
            destination_text="강남역",
            transport_mode="subway",
            confidence=0.95,
        )
    )
    assert validation.is_valid is False
    assert "버스 경로만" in validation.message


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


def test_upload_compat_route_preserves_walk_steps() -> None:
    response = _build_upload_compat_response({
        "status": "success",
        "message": "도보 이동 후 3412번을 타세요.",
        "data": {
            "intent": "route",
            "origin": "올림픽공원역",
            "destination": "강남역",
            "bus_number": "3412",
            "total_time_min": 30,
            "route_segments": [
                {
                    "vehicle_type": "도보", "line": "도보 180m",
                    "start_name": "올림픽공원역", "end_name": "올림픽공원역 정류장",
                    "time_min": 3,
                },
                {
                    "vehicle_type": "버스", "line": "3412번",
                    "start_name": "올림픽공원역 정류장", "end_name": "강남역",
                    "time_min": 27,
                },
            ],
        },
    })

    steps = response["buses"][0]["routeDetail"]["steps"]
    assert [step["type"] for step in steps] == ["walk", "bus"]
    assert steps[0]["description"] == "도보 180m"


def test_ogg_audio_header_is_supported() -> None:
    assert _looks_like_supported_audio("audio/ogg", b"OggS\x00\x02payload") is True
    assert _looks_like_supported_audio("audio/ogg", b"not-ogg") is False


def test_route_message_includes_each_walk_and_bus_segment() -> None:
    message = build_user_message(
        ParsedIntent(intent="route", destination_text="강남역", transport_mode="bus"),
        TransportResult(
            origin="올림픽공원역",
            destination="강남역",
            total_time_min=30,
            route_segments=[
                RouteSegment("도보", "도보 180m", "출발지", "올림픽공원역 정류장", 3),
                RouteSegment("버스", "3412번", "올림픽공원역 정류장", "강남역 정류장", 24),
                RouteSegment("도보", "도보 120m", "강남역 정류장", "강남역", 3),
            ],
        ),
    )

    assert "올림픽공원역 정류장까지 약 3분 걸어가세요" in message
    assert "3412번 버스를 타고" in message
    assert "강남역까지 약 3분 걸어가세요" in message


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

    async def fail_tts(_text: str):
        raise AssertionError("typed route must not request paid TTS")

    monkeypatch.setattr(pipeline, "search_transport_info", search)
    monkeypatch.setattr(pipeline, "generate_tts_audio", fail_tts)

    result = asyncio.run(
        pipeline.run_text_route(
            "강남역",
            destination_x=127.0276,
            destination_y=37.4979,
            origin="서울시청",
            request_id="typed-route",
        )
    )
    compat = _build_upload_compat_response(result)

    assert compat["success"] is True
    assert compat["destination"] == "강남역"
    assert compat["buses"][0]["busNumber"] == "402"
    assert compat["buses"][0]["routeDetail"]["totalMin"] == 28
    assert result["audio_base64"] is None


def test_place_confirmation_is_exposed_to_frontend_contract() -> None:
    result = {
        "status": "success",
        "message": "강남역 2호선이 맞나요?",
        "data": {
            "intent": "route",
            "destination": "강남역 2호선",
            "needs_confirmation": True,
            "confirmation": {
                "kind": "place",
                "prompt": "강남역 2호선이 맞나요?",
                "candidate": {
                    "name": "강남역 2호선",
                    "address": "서울 강남구 강남대로 지하 396",
                    "x": "127.028",
                    "y": "37.498",
                },
                "alternatives": [],
            },
        },
    }
    compat = _build_upload_compat_response(result)
    assert compat["success"] is True
    assert compat["needs_confirmation"] is True
    assert compat["confirmation"]["candidate"]["name"] == "강남역 2호선"
    assert compat["buses"] == []


def test_default_bus_route_omits_none_fields_for_javascript_comparison() -> None:
    route = next(route for route in bus_router.routes if route.path == "/default")
    assert route.response_model_exclude_none is True


@pytest.mark.parametrize("message", ["운행종료", "운행 종료", "출발대기", "출발 대기"])
def test_unavailable_bus_is_not_reported_as_arriving(message: str) -> None:
    assert _extract_arrival_minutes(
        {"traTime1": "0", "arrmsg1": message},
        1,
    ) is None


def test_imminent_bus_with_zero_seconds_is_reported_as_arriving() -> None:
    assert _extract_arrival_minutes(
        {"traTime1": "0", "arrmsg1": "곧 도착"},
        1,
    ) == 0


def test_seoul_bus_urls_use_reachable_http_endpoint() -> None:
    urls = (
        SEOUL_BUS_ARRIVAL_URL,
        SEOUL_BUS_ROUTE_SEARCH_URL,
        SEOUL_ROUTE_STATION_URL,
        SEOUL_STATION_ARRIVAL_URL,
        SEOUL_STATION_SEARCH_URL,
    )
    assert all(url.startswith("http://ws.bus.go.kr/api/rest/") for url in urls)


def test_odsay_segments_preserve_walk_and_bus_order() -> None:
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
                "startX": 127.10,
                "startY": 37.51,
                "endX": 127.12,
                "endY": 37.53,
                "passStopList": {
                    "stations": [
                        {"x": "127.11", "y": "37.52"},
                    ]
                },
            },
        ]
    )

    assert segments is not None
    assert [(segment.vehicle_type, segment.line) for segment in segments] == [
        ("도보", "도보 120m"),
        ("버스", "3214번"),
    ]
    assert segments[1].path_points == [
        {"x": 127.10, "y": 37.51},
        {"x": 127.11, "y": 37.52},
        {"x": 127.12, "y": 37.53},
    ]


def test_odsay_bus_mode_excludes_mixed_subway_path() -> None:
    mixed = {
        "info": {"totalTime": 10, "busTransitCount": 1, "subwayTransitCount": 1},
        "subPath": [{"trafficType": 2, "lane": [{"busNo": "146"}]}, {"trafficType": 1}],
    }
    bus_only = {
        "info": {"totalTime": 20, "busTransitCount": 1, "subwayTransitCount": 0},
        "subPath": [{"trafficType": 2, "lane": [{"busNo": "402"}]}],
    }
    selected = _select_best_path({"result": {"path": [mixed, bus_only]}})
    assert selected is bus_only


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


def test_frontend_http_endpoints_share_the_expected_contract(monkeypatch) -> None:
    """Exercise the same HTTP boundary used by the React application."""

    async def mock_route(**_kwargs):
        return {
            "status": "success",
            "message": "3412번 버스를 타세요.",
            "data": {
                "intent": "route",
                "origin": "올림픽공원역",
                "destination": "강남역",
                "bus_number": "3412",
                "arrival_time": "2분후",
                "total_time_min": 30,
                "route_segments": [
                    {
                        "vehicle_type": "버스",
                        "line": "3412번",
                        "start_name": "올림픽공원역 정류장",
                        "end_name": "강남역 정류장",
                        "time_min": 30,
                    }
                ],
            },
            "audio_base64": None,
            "request_id": "integration",
        }

    async def mock_arrivals():
        return DefaultBusArrivalResponse(
            success=True,
            station_name="올림픽공원역",
            station_id="24245",
            message="정상",
            items=[
                DefaultBusArrivalItem(
                    bus_number="3412",
                    direction="강남역 방면",
                    first_arrival_min=2,
                    message="2분 후 도착",
                    raw_station_nm1="몽촌토성역",
                )
            ],
        )

    monkeypatch.setattr(gateway_module, "verify_api_token", lambda _request: None)
    monkeypatch.setattr(gateway_module, "run_text_route", mock_route)
    monkeypatch.setattr(bus_module, "verify_api_token", lambda _request: None)
    monkeypatch.setattr(bus_module, "get_default_bus_arrivals", mock_arrivals)

    async def exercise_http_boundary():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            route_response = await client.post(
                "/api/route",
                json={"destination": "강남역", "transport_mode": "bus"},
            )
            board_response = await client.get("/api/bus/default")
        return route_response, board_response

    route_response, board_response = asyncio.run(exercise_http_boundary())

    assert route_response.status_code == 200
    assert route_response.json()["buses"][0]["routeDetail"]["steps"][0]["type"] == "bus"
    assert board_response.status_code == 200
    assert board_response.json()["items"][0]["bus_number"] == "3412"
