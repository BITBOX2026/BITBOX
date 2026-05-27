from dataclasses import dataclass
from typing import Literal


IntentType = Literal["route", "arrival", "unknown"]
TransportMode = Literal["bus", "subway", "transit", "unknown"]


@dataclass
class ParsedIntent:
    """STT 결과를 LLM 또는 mock parser가 구조화한 값입니다."""

    intent: IntentType = "unknown"
    origin_text: str | None = None
    destination_text: str | None = None
    stop_text: str | None = None
    transport_mode: TransportMode = "unknown"
    bus_number: str | None = None
    confidence: float = 0.0


@dataclass
class ValidationResult:
    """파이프라인을 계속 진행할 수 있는지 판단한 결과입니다."""

    is_valid: bool
    message: str


@dataclass
class RouteSegment:
    """경로 안내에 사용할 한 구간(버스 또는 지하철) 정보입니다."""

    vehicle_type: str   # "버스" | "지하철"
    line: str           # "740번" | "2호선" | "공항철도"
    start_name: str     # 탑승 정류장/역 이름
    end_name: str       # 하차 정류장/역 이름


@dataclass
class TransportResult:
    """교통 API 또는 mock 조회 결과를 백엔드 공통 구조로 맞춘 값입니다."""

    origin: str | None = None
    destination: str | None = None
    stop_name: str | None = None
    transport_mode: TransportMode = "unknown"
    bus_number: str | None = None
    arrival_time: str | None = None
    total_time_min: int | None = None
    payment: int | None = None
    bus_transit_count: int | None = None
    subway_transit_count: int | None = None
    transfer_count: int | None = None
    path_type: int | None = None
    route_summary: str | None = None
    route_segments: list[RouteSegment] | None = None
    source: str = "none"
