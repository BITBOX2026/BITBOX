"""FastAPI response models for the public API."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RouteSegmentResponse(BaseModel):
    vehicle_type: str
    line: str
    start_name: str
    end_name: str
    time_min: int | None = None
    start_x: float | None = None  # 탑승 정류장 경도
    start_y: float | None = None  # 탑승 정류장 위도
    end_x: float | None = None    # 하차 정류장 경도
    end_y: float | None = None    # 하차 정류장 위도
    path_points: list[dict[str, float]] | None = None


class PlaceCandidateResponse(BaseModel):
    name: str
    address: str
    category: str = ""
    category_code: str = ""
    x: str
    y: str


class PlaceConfirmationResponse(BaseModel):
    kind: Literal["place"]
    prompt: str
    candidate: PlaceCandidateResponse
    alternatives: list[PlaceCandidateResponse] = Field(default_factory=list)


class SafetyDecisionResponse(BaseModel):
    level: Literal["verified", "confirm", "retry"]
    title: str
    reasons: list[str] = Field(default_factory=list)
    auto_corrected: bool = False
    checked_at: str | None = None


class ProcessDataResponse(BaseModel):
    transcript: str | None = None
    intent: str | None = None
    origin: str | None = None
    origin_x: float | None = None       # 출발지 경도
    origin_y: float | None = None       # 출발지 위도
    destination: str | None = None
    destination_x: float | None = None  # 목적지 경도
    destination_y: float | None = None  # 목적지 위도
    stop_text: str | None = None
    stop_name: str | None = None
    transport_mode: str | None = None
    bus_number: str | None = None
    arrival_time: str | None = None
    arrival_time_2: str | None = None
    first_bus_time: str | None = None
    total_time_min: int | None = None
    payment: int | None = None
    bus_transit_count: int | None = None
    transfer_count: int | None = None
    path_type: int | None = None
    route_segments: list[RouteSegmentResponse] | None = None
    confidence: float | None = None
    source: str | None = None
    needs_confirmation: bool | None = None
    confirmation: PlaceConfirmationResponse | None = None
    safety_decision: SafetyDecisionResponse | None = None


class ProcessResponse(BaseModel):
    status: Literal["success", "error"]
    message: str
    data: ProcessDataResponse = Field(default_factory=ProcessDataResponse)
    audio_base64: str | None = None
    request_id: str | None = None
    error_kind: str | None = None


class FrontendRouteStep(BaseModel):
    type: Literal["walk", "bus"]
    durationMin: int
    description: str | None = None
    fromStop: str | None = None
    toStop: str | None = None
    busNumber: str | None = None


class FrontendRouteDetail(BaseModel):
    busNumber: str
    totalMin: int
    steps: list[FrontendRouteStep] = Field(default_factory=list)
    origin: str | None = None
    origin_x: float | None = None
    origin_y: float | None = None
    destination_x: float | None = None
    destination_y: float | None = None
    route_segments: list[RouteSegmentResponse] | None = None


# 도착 상태 — 백엔드와 프론트가 같은 낱말로 해석하도록 명시합니다.
#   live     실시간 도착 예정 시간이 있음
#   standby  차고지 출발대기 (아직 출발 전)
#   terminal 오늘 운행 종료
#   unknown  제공기관이 도착정보를 주지 않음
BusArrivalStatus = Literal["live", "standby", "terminal", "unknown"]


class FrontendBusOption(BaseModel):
    id: str
    busNumber: str
    status: BusArrivalStatus = "live"
    arrivalMin: int
    traTimeSec: int
    arrivalMsg: str
    currentStationName: str
    remainingStops: int
    busType: int
    congestion: Literal[0, 3, 4, 5]
    isFullFlag: bool
    isLastBus: bool
    plainNo: str
    isSecond: bool
    totalMin: int | None = None
    steps: list[FrontendRouteStep] | None = None
    routeDetail: FrontendRouteDetail | None = None


class UploadCompatResponse(BaseModel):
    success: bool
    text: str | None = None
    intent: str | None = None
    destination: str | None = None
    destination_text: str | None = None
    bus_number: str | None = None
    arrival_time: str | None = None
    arrival_time_2: str | None = None
    first_bus_time: str | None = None
    message: str
    buses: list[FrontendBusOption] = Field(default_factory=list)
    audio_base64: str | None = None
    request_id: str | None = None
    needs_confirmation: bool = False
    confirmation: PlaceConfirmationResponse | None = None
    safety_decision: SafetyDecisionResponse | None = None
    error_kind: str | None = None


class TextRouteRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=100)
    destination_address: str | None = Field(default=None, max_length=200)
    destination_x: float | None = Field(default=None, ge=124.0, le=132.0)
    destination_y: float | None = Field(default=None, ge=33.0, le=39.5)
    origin: str | None = Field(default=None, max_length=100)
    transport_mode: Literal["bus"] = "bus"

    @model_validator(mode="after")
    def validate_destination_coordinates(self) -> "TextRouteRequest":
        if (self.destination_x is None) != (self.destination_y is None):
            raise ValueError("destination_x와 destination_y는 함께 전달해야 합니다.")
        return self


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    mock_mode: bool
    version: str
    release_sha: str | None = None
    capabilities: list[str]
    api_keys_configured: dict[str, bool] | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    version: str
    release_sha: str | None = None
