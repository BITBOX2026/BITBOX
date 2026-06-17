"""Bus arrival API routes."""

from fastapi import APIRouter, Request

from app.core.rate_limiter import limiter
from app.schemas.bus import DefaultBusArrivalResponse
from app.services.bus_service import get_default_bus_arrivals

router = APIRouter()


@router.get("/default", response_model=DefaultBusArrivalResponse)
@limiter.limit("30/minute")
async def get_default_bus_arrival(request: Request) -> DefaultBusArrivalResponse:
    return await get_default_bus_arrivals()
