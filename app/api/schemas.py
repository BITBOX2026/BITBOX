"""FastAPI response models for the public API."""

from typing import Literal

from pydantic import BaseModel, Field


class RouteSegmentResponse(BaseModel):
    vehicle_type: str
    line: str
    start_name: str
    end_name: str


class ProcessDataResponse(BaseModel):
    transcript: str | None = None
    intent: str | None = None
    origin: str | None = None
    destination: str | None = None
    stop_text: str | None = None
    stop_name: str | None = None
    transport_mode: str | None = None
    bus_number: str | None = None
    arrival_time: str | None = None
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


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    mock_mode: bool
    api_keys_configured: dict[str, bool] | None = None
