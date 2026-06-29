"""FastAPI response models for the public API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    subway_transit_count: int | None = None
    transfer_count: int | None = None
    path_type: int | None = None
    route_segments: list[RouteSegmentResponse] | None = None
    confidence: float | None = None
    source: str | None = None
    needs_confirmation: bool | None = None


class ProcessResponse(BaseModel):
    status: Literal["success", "error"]
    message: str
    data: ProcessDataResponse = Field(default_factory=ProcessDataResponse)
    audio_base64: str | None = None
    request_id: str | None = None


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
    buses: list[dict[str, Any]] = Field(default_factory=list)
    audio_base64: str | None = None
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    mock_mode: bool
    api_keys_configured: dict[str, bool] | None = None
