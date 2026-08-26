"""Contract tests for the BIT_REACT feat/info frontend."""

import asyncio
import time
from dataclasses import asdict

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import app.api.gateway as gateway_module
import app.routers.bus as bus_module
from app.api.gateway import (
    ALLOWED_CONTENT_TYPES,
    _build_upload_compat_response,
    _looks_like_supported_audio,
    _safe_audio_filename,
)
from app.api.schemas import ProcessResponse, TextRouteRequest, UploadCompatResponse
from app.core import auth
from app.main import app
from app.routers.bus import router as bus_router
from app.routers.place import PlaceSuggestion
from app.schemas.bus import DefaultBusArrivalItem, DefaultBusArrivalResponse
from app.services import pipeline
from app.services.ai import llm_service
from app.services.bus_service import _extract_arrival_minutes
from app.services.core.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
    SEOUL_STATION_ARRIVAL_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.core.exceptions import CoordinateResolveError
from app.services.core.service_types import (
    ParsedIntent,
    RouteSegment,
    TransportResult,
    ValidationResult,
)
from app.services.response_builder import build_user_message
from app.services.transit import transport_service
from app.services.transit.odsay_service import (
    _extract_route_segments,
    _select_best_path,
    _select_display_bus_number,
)
from app.services.transit.validate_service import validate_parsed_intent


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
    assert serialized["buses"][0]["routeDetail"] is None


def test_standby_arrival_is_not_serialized_as_imminent() -> None:
    response = _build_upload_compat_response({
        "status": "success",
        "message": "출발 대기 중입니다.",
        "data": {
            "intent": "arrival",
            "stop_name": "올림픽공원역",
            "bus_number": "3412",
            "arrival_time": "출발대기",
        },
    })
    bus = response["buses"][0]
    assert bus["arrivalMin"] == -1
    assert bus["traTimeSec"] == -1
    assert bus["arrivalMsg"] == "출발 대기 중"


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


def test_matroska_recording_from_chromium_is_accepted() -> None:
    """일부 Chromium 빌드는 MediaRecorder 결과를 audio/x-matroska 로 보고합니다.

    기기 차이일 뿐 내용은 WebM 과 같은 EBML 컨테이너입니다. 거부하면 그 기기에서는
    음성 입력이 통째로 400 으로 막힙니다.
    """
    ebml_header = b"\x1a\x45\xdf\xa3payload"
    assert "audio/x-matroska" in ALLOWED_CONTENT_TYPES
    assert _looks_like_supported_audio("audio/x-matroska", ebml_header) is True
    assert _looks_like_supported_audio("audio/x-matroska", b"not-ebml") is False
    # STT 가 확장자로 형식을 인식하므로 파일명도 함께 정해져 있어야 합니다.
    assert _safe_audio_filename("audio/x-matroska") == "recording.webm"


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


def test_place_suggestion_contract_preserves_ranking_metadata() -> None:
    suggestion = PlaceSuggestion(
        name="강남역 2호선",
        address="서울 강남구 강남대로 지하 396",
        category="교통,수송 > 지하철,전철 > 수도권 2호선",
        category_code="SW8",
        x="127.028",
        y="37.498",
    ).model_dump()

    assert suggestion["category_code"] == "SW8"
    assert "지하철" in suggestion["category"]


def test_safety_decision_is_preserved_for_frontend() -> None:
    compat = _build_upload_compat_response({
        "status": "success",
        "message": "3412번 버스를 확인했습니다.",
        "data": {
            "intent": "arrival",
            "bus_number": "3412",
            "safety_decision": {
                "level": "verified",
                "title": "검증 절차 완료",
                "reasons": ["운행 노선과 정확히 일치합니다."],
                "auto_corrected": False,
            },
        },
    })

    serialized = UploadCompatResponse.model_validate(compat).model_dump()
    assert serialized["safety_decision"]["level"] == "verified"
    assert serialized["safety_decision"]["auto_corrected"] is False


def test_mock_safety_decision_does_not_claim_external_data() -> None:
    decision = pipeline._verified_safety_decision(
        ParsedIntent(intent="arrival", bus_number="3412", transport_mode="bus"),
        "mock",
    )

    assert all("외부 교통 데이터" not in reason for reason in decision["reasons"])
    assert decision["auto_corrected"] is False
    assert decision["checked_at"] is None


def test_confirmation_contract_rejects_missing_candidate() -> None:
    with pytest.raises(ValidationError):
        UploadCompatResponse.model_validate({
            "success": True,
            "needs_confirmation": True,
            "confirmation": {
                "kind": "place",
                "prompt": "강남역 2호선이 맞나요?",
                "alternatives": [],
            },
        })


def test_failed_route_search_does_not_leak_per_key_locks(monkeypatch) -> None:
    async def resolve_origin(_origin_text: str | None):
        return "송파책박물관", 127.104, 37.498

    async def fail_destination(_place_name: str, _label: str):
        raise CoordinateResolveError("목적지를 찾을 수 없습니다.")

    monkeypatch.setattr(transport_service, "resolve_origin", resolve_origin)
    monkeypatch.setattr(
        transport_service,
        "resolve_place_coordinates",
        fail_destination,
    )
    transport_service._route_cache.clear()
    transport_service._route_cache_locks.clear()

    async def exercise_failures() -> None:
        for index in range(10):
            parsed = ParsedIntent(
                intent="route",
                destination_text=f"존재하지 않는 목적지 {index}",
                transport_mode="bus",
            )
            with pytest.raises(CoordinateResolveError):
                await transport_service._search_route_with_odsay(parsed)

    try:
        asyncio.run(exercise_failures())
        assert transport_service._route_cache == {}
        assert transport_service._route_cache_locks == {}
    finally:
        transport_service._route_cache.clear()
        transport_service._route_cache_locks.clear()


def test_successful_route_cache_eviction_also_releases_locks(monkeypatch) -> None:
    """캐시가 최대 크기를 넘어도 Lock 사전이 함께 정리되는지 확인합니다."""

    async def resolve_origin(_origin_text: str | None):
        return "송파책박물관", 127.104, 37.498

    async def resolve_destination(_place_name: str, _label: str):
        return 127.0, 37.5

    async def fake_odsay(**kwargs):
        return TransportResult(
            origin=kwargs["origin_name"],
            destination=kwargs["destination_text"],
            transport_mode="bus",
            bus_number="3412",
            total_time_min=20,
            source="odsay",
        )

    monkeypatch.setattr(transport_service, "resolve_origin", resolve_origin)
    monkeypatch.setattr(transport_service, "resolve_place_coordinates", resolve_destination)
    monkeypatch.setattr(transport_service, "search_odsay_route", fake_odsay)

    transport_service._route_cache.clear()
    transport_service._route_cache_locks.clear()
    max_size = transport_service._ROUTE_CACHE_MAX_SIZE

    async def exercise_successes() -> None:
        for index in range(max_size + 20):
            await transport_service._search_route_with_odsay(
                ParsedIntent(
                    intent="route",
                    destination_text=f"목적지 {index}",
                    transport_mode="bus",
                )
            )

    try:
        asyncio.run(exercise_successes())
        # LRU 축출이 캐시와 Lock을 함께 제거하므로 두 사전 모두 상한을 넘지 않아야 합니다.
        assert len(transport_service._route_cache) <= max_size
        assert len(transport_service._route_cache_locks) <= max_size
        assert set(transport_service._route_cache_locks) <= set(transport_service._route_cache)
    finally:
        transport_service._route_cache.clear()
        transport_service._route_cache_locks.clear()


def test_expired_route_cache_entry_also_releases_its_lock(monkeypatch) -> None:
    """TTL이 지난 캐시 항목을 읽을 때 대응 Lock도 함께 정리되는지 확인합니다."""
    transport_service._route_cache.clear()
    transport_service._route_cache_locks.clear()

    key = "expired-route-key"
    stale_timestamp = time.monotonic() - transport_service._ROUTE_CACHE_TTL - 1
    transport_service._route_cache[key] = (TransportResult(source="odsay"), stale_timestamp)
    transport_service._route_cache_locks[key] = asyncio.Lock()

    try:
        assert transport_service._get_cached_route(key) is None
        assert key not in transport_service._route_cache
        assert key not in transport_service._route_cache_locks
    finally:
        transport_service._route_cache.clear()
        transport_service._route_cache_locks.clear()


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


def test_odsay_segments_read_real_section_time_field() -> None:
    """ODsay 실제 응답 키(sectionTime)에서 구간 소요시간을 읽어야 합니다.

    실제 API는 subPath 소요시간을 `time`이 아니라 `sectionTime`으로 반환합니다.
    이 값을 놓치면 gateway가 총 소요시간을 구간 수로 균등 분배해
    41m 도보가 41분 버스 구간과 같은 시간으로 안내되는 오류가 발생합니다.
    """
    segments = _extract_route_segments(
        [
            {
                "trafficType": 3,
                "distance": 41,
                "sectionTime": 1,
                "startName": "출발지",
                "endName": "올림픽공원역",
            },
            {
                "trafficType": 2,
                "sectionTime": 41,
                "startName": "올림픽공원역",
                "endName": "강남역12번출구",
                "lane": [{"busNo": "3412"}],
            },
            {
                "trafficType": 3,
                "distance": 157,
                "sectionTime": 2,
                "startName": "강남역12번출구",
                "endName": "강남역 2호선",
            },
        ]
    )

    assert segments is not None
    assert [segment.time_min for segment in segments] == [1, 41, 2]


def test_route_steps_use_real_segment_times_instead_of_even_split() -> None:
    """구간 시간이 있으면 총 시간을 균등 분배하지 않아야 합니다."""
    response = _build_upload_compat_response({
        "status": "success",
        "message": "3412번을 타세요.",
        "data": {
            "intent": "route",
            "origin": "올림픽공원역",
            "destination": "강남역 2호선",
            "bus_number": "3412",
            "total_time_min": 44,
            "route_segments": [
                {
                    "vehicle_type": "도보", "line": "도보 41m",
                    "start_name": "출발지", "end_name": "올림픽공원역", "time_min": 1,
                },
                {
                    "vehicle_type": "버스", "line": "3412번",
                    "start_name": "올림픽공원역", "end_name": "강남역12번출구", "time_min": 41,
                },
                {
                    "vehicle_type": "도보", "line": "도보 157m",
                    "start_name": "강남역12번출구", "end_name": "강남역 2호선", "time_min": 2,
                },
            ],
        },
    })

    steps = response["buses"][0]["routeDetail"]["steps"]
    assert [step["durationMin"] for step in steps] == [1, 41, 2]
    # 균등 분배(44 // 3 = 15)로 무너지지 않았는지 확인합니다.
    assert all(step["durationMin"] != 15 for step in steps)


def test_transfer_route_keeps_each_segment_time_and_order() -> None:
    """환승(버스 2회) 경로에서도 구간 시간과 순서가 보존되어야 합니다."""
    response = _build_upload_compat_response({
        "status": "success",
        "message": "환승 경로",
        "data": {
            "intent": "route",
            "origin": "올림픽공원역",
            "destination": "서울역",
            "bus_number": "3412",
            "total_time_min": 62,
            "transfer_count": 1,
            "route_segments": [
                {"vehicle_type": "도보", "line": "도보 90m",
                 "start_name": "출발지", "end_name": "올림픽공원역", "time_min": 2},
                {"vehicle_type": "버스", "line": "3412번",
                 "start_name": "올림픽공원역", "end_name": "강남역", "time_min": 35},
                {"vehicle_type": "도보", "line": "도보 60m",
                 "start_name": "강남역", "end_name": "강남역환승", "time_min": 1},
                {"vehicle_type": "버스", "line": "146번",
                 "start_name": "강남역환승", "end_name": "서울역", "time_min": 22},
                {"vehicle_type": "도보", "line": "도보 120m",
                 "start_name": "서울역", "end_name": "서울역 광장", "time_min": 2},
            ],
        },
    })

    steps = response["buses"][0]["routeDetail"]["steps"]
    assert [step["type"] for step in steps] == ["walk", "bus", "walk", "bus", "walk"]
    assert [step["durationMin"] for step in steps] == [2, 35, 1, 22, 2]
    assert sum(step["durationMin"] for step in steps) == 62
    # 두 번째 버스 구간의 노선 번호가 첫 구간 번호로 덮이지 않아야 합니다.
    assert [step["busNumber"] for step in steps if step["type"] == "bus"] == ["3412", "146"]


def test_missing_segment_time_uses_only_unallocated_total() -> None:
    response = _build_upload_compat_response({
        "status": "success",
        "message": "경로 안내",
        "data": {
            "intent": "route",
            "destination": "강남역",
            "bus_number": "3412",
            "total_time_min": 45,
            "route_segments": [
                {"vehicle_type": "도보", "line": "도보", "time_min": 1},
                {"vehicle_type": "버스", "line": "3412번", "time_min": 41},
                {"vehicle_type": "도보", "line": "도보", "time_min": None},
            ],
        },
    })

    steps = response["buses"][0]["routeDetail"]["steps"]
    assert [step["durationMin"] for step in steps] == [1, 41, 3]
    assert sum(step["durationMin"] for step in steps) == 45


def test_route_without_live_arrival_never_claims_the_bus_is_imminent() -> None:
    response = _build_upload_compat_response({
        "status": "success",
        "message": "경로 안내",
        "data": {
            "intent": "route",
            "destination": "강남역",
            "bus_number": "3412",
            "arrival_time": None,
            "total_time_min": 45,
            "route_segments": [
                {"vehicle_type": "버스", "line": "3412번", "time_min": 45},
            ],
        },
    })

    bus = response["buses"][0]
    assert bus["arrivalMin"] == -1
    assert bus["traTimeSec"] == -1
    assert bus["arrivalMsg"] == "3412 도착정보 없음"


def test_display_bus_and_segment_use_the_same_preferred_lane() -> None:
    sub_paths = [{
        "trafficType": 2,
        "startName": "출발 정류장",
        "endName": "도착 정류장",
        "sectionTime": 10,
        "lane": [{"busNo": "N13"}, {"busNo": "3412"}],
    }]

    assert _select_display_bus_number(sub_paths) == "3412"
    segments = _extract_route_segments(sub_paths)
    assert segments is not None
    assert segments[0].line == "3412번"
    assert segments[0].alternative_lines == ["N13"]


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


def test_route_arrival_uses_the_actual_boarding_stop(monkeypatch) -> None:
    async def unexpected_default_lookup(_bus_number: str):
        raise AssertionError("a different boarding stop must not use default-stop arrivals")

    async def arrival_at_boarding_stop(bus_number: str, stop_name: str):
        assert bus_number == "N13"
        assert stop_name == "서울역버스환승센터"
        return "4분후", "15분후"

    monkeypatch.setattr(
        transport_service,
        "fetch_arrival_at_default_stop",
        unexpected_default_lookup,
    )
    monkeypatch.setattr(
        transport_service,
        "fetch_arrival_at_stop",
        arrival_at_boarding_stop,
    )
    monkeypatch.setattr(
        transport_service,
        "get_setting",
        lambda name: "올림픽공원역" if name == "DEFAULT_BUS_STOP_NAME" else None,
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


def test_route_arrival_uses_fast_default_lookup_only_for_the_same_stop(monkeypatch) -> None:
    async def default_arrival(bus_number: str):
        assert bus_number == "3412"
        return "2분후", "9분후"

    async def unexpected_named_lookup(_bus_number: str, _stop_name: str):
        raise AssertionError("the exact default stop should use its direct lookup")

    monkeypatch.setattr(transport_service, "fetch_arrival_at_default_stop", default_arrival)
    monkeypatch.setattr(transport_service, "fetch_arrival_at_stop", unexpected_named_lookup)
    monkeypatch.setattr(
        transport_service,
        "get_setting",
        lambda name: "올림픽공원역" if name == "DEFAULT_BUS_STOP_NAME" else None,
    )
    result = TransportResult(
        route_segments=[
            RouteSegment("버스", "3412번", "올림픽공원역", "강남역")
        ]
    )

    enriched = asyncio.run(
        transport_service._enrich_arrival_time(
            result,
            ParsedIntent(intent="route", origin_text=None),
            "test-request",
        )
    )
    assert enriched.arrival_time == "2분후"
    assert enriched.stop_name == "올림픽공원역"


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
    assert result["data"]["safety_decision"]["level"] == "verified"
    assert result["data"]["safety_decision"]["auto_corrected"] is False
    assert result["data"]["safety_decision"]["checked_at"]


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


# ---------------------------------------------------------------------------
# 구간시간 합과 총시간의 일관성
#
# 화면은 각 구간의 소요시간과 총시간을 함께 보여 줍니다. 구간합이 총시간보다
# 크면 이용자에게 모순된 숫자를 보이게 되고, 배포 스모크의 계약 검사도 깨집니다.
# ---------------------------------------------------------------------------

def _route_data(total_time_min: int, segment_times: list[int | None]) -> dict:
    return {
        "intent": "route",
        "bus_number": "3412",
        "total_time_min": total_time_min,
        "origin": "올림픽공원역",
        "route_segments": [
            {
                "vehicle_type": "도보" if index % 2 == 0 else "버스",
                "line": "" if index % 2 == 0 else "3412번",
                "start_name": f"S{index}",
                "end_name": f"E{index}",
                "time_min": value,
            }
            for index, value in enumerate(segment_times)
        ],
    }


def test_segment_durations_never_exceed_the_displayed_total() -> None:
    """제공자 총시간이 구간합보다 작아도 화면 숫자는 모순되지 않아야 합니다."""
    buses = gateway_module._build_buses_from_route(_route_data(10, [8, 9, 4]))
    detail = buses[0]["routeDetail"]
    step_sum = sum(step["durationMin"] for step in detail["steps"])
    assert step_sum == 21
    assert detail["totalMin"] >= step_sum
    assert buses[0]["totalMin"] == detail["totalMin"]


def test_missing_segment_durations_are_distributed_to_match_the_total() -> None:
    buses = gateway_module._build_buses_from_route(_route_data(30, [3, None, None]))
    detail = buses[0]["routeDetail"]
    assert sum(step["durationMin"] for step in detail["steps"]) == detail["totalMin"] == 30


# ---------------------------------------------------------------------------
# 도착 상태 계약 — 백엔드와 프론트가 같은 낱말을 씁니다.
# ---------------------------------------------------------------------------

def test_standby_arrival_is_labelled_instead_of_looking_like_an_eta() -> None:
    buses = gateway_module._build_buses_from_arrival(
        {"intent": "arrival", "bus_number": "3412", "arrival_time": "출발대기", "stop_name": "차고지"}
    )
    assert len(buses) == 1
    assert buses[0]["status"] == "standby"
    assert buses[0]["arrivalMin"] == -1
    assert buses[0]["traTimeSec"] == -1


def test_live_arrival_reports_a_live_status() -> None:
    buses = gateway_module._build_buses_from_arrival(
        {"intent": "arrival", "bus_number": "3412", "arrival_time": "3분 후", "stop_name": "올림픽공원역"}
    )
    assert buses[0]["status"] == "live"
    assert buses[0]["arrivalMin"] == 3


def test_frontend_bus_option_rejects_an_unknown_status() -> None:
    from app.api.schemas import FrontendBusOption

    base = {
        "id": "x", "busNumber": "3412", "arrivalMin": 1, "traTimeSec": 60,
        "arrivalMsg": "1분 후", "currentStationName": "몽촌토성역", "remainingStops": 1,
        "busType": 0, "congestion": 0, "isFullFlag": False, "isLastBus": False,
        "plainNo": "", "isSecond": False,
    }
    assert FrontendBusOption(**base).status == "live"
    with pytest.raises(ValidationError):
        FrontendBusOption(**base, status="곧도착")


# ---------------------------------------------------------------------------
# HTTP 200 으로 나가는 업무 오류가 성공 지표에 묻히지 않는지
# ---------------------------------------------------------------------------

def test_http_200_business_error_is_counted_separately_from_success() -> None:
    from starlette.responses import Response as StarletteResponse

    from app.core.runtime_metrics import runtime_snapshot

    before = runtime_snapshot()["business_errors"].get("request", 0)
    gateway_module._apply_result_http_status(
        StarletteResponse(),
        {"status": "error", "error_kind": "request", "message": "목적지를 말씀해 주세요."},
    )
    after = runtime_snapshot()["business_errors"].get("request", 0)
    assert after == before + 1


def test_successful_result_is_not_counted_as_a_business_error() -> None:
    from starlette.responses import Response as StarletteResponse

    from app.core.runtime_metrics import runtime_snapshot

    before = runtime_snapshot()["business_errors"]
    gateway_module._apply_result_http_status(
        StarletteResponse(), {"status": "success", "message": "ok"}
    )
    assert runtime_snapshot()["business_errors"] == before


def test_alternative_routes_reach_the_rider_by_voice_and_screen() -> None:
    """같은 구간의 다른 노선을 알려 주지 않으면 먼저 오는 차를 그냥 보냅니다.

    ODsay 의 `lane` 은 그 구간에서 서로 바꿔 탈 수 있는 노선 목록입니다.
    버스를 기다리는 시간이 곧 이동 시간인 이용자에게는 이 차이가 큽니다.
    """
    segments = [
        RouteSegment(
            vehicle_type="버스", line="3412번",
            start_name="올림픽공원역", end_name="잠실역",
            time_min=12, alternative_lines=["341", "3413"],
        ),
    ]

    # 소리로 전달되는지
    message = build_user_message(
        parsed=ParsedIntent(intent="route", destination_text="잠실역", transport_mode="bus"),
        transport_result=TransportResult(
            origin="올림픽공원역", destination="잠실역", transport_mode="bus",
            bus_number="3412", total_time_min=12, route_segments=segments, source="odsay",
        ),
    )
    assert "341번, 3413번 버스를 타셔도 됩니다." in message

    # 화면으로도 전달되는지 (소리를 듣지 못하는 이용자)
    response = _build_upload_compat_response({
        "status": "success",
        "message": message,
        "data": {
            "intent": "route",
            "destination": "잠실역",
            "bus_number": "3412",
            "total_time_min": 12,
            "route_segments": [asdict(segment) for segment in segments],
        },
    })
    step = response["buses"][0]["routeDetail"]["steps"][0]
    assert step["alternativeBuses"] == ["341", "3413"]


def test_walking_steps_have_no_alternative_routes() -> None:
    segments = _extract_route_segments([{
        "trafficType": 3,
        "startName": "A",
        "endName": "B",
        "sectionTime": 3,
        "distance": 200,
        # 잘못된 상류 데이터가 섞여도 보행 단계에는 버스 대체편을 붙이지 않습니다.
        "lane": [{"busNo": "3412"}],
    }])
    assert segments is not None
    assert segments[0].vehicle_type == "도보"
    assert segments[0].alternative_lines is None
