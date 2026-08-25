"""Compatibility routes for the existing React station API."""

from fastapi import APIRouter, Query, Request

from app.core.auth import verify_api_token
from app.core.rate_limiter import limiter
from app.schemas.bus import SeoulStationArrivalResponse
from app.services.bus_service import get_seoul_station_arrival_response

router = APIRouter()


@router.get("/getStationByUid", response_model=SeoulStationArrivalResponse)
@limiter.limit("30/minute")
async def get_station_by_uid(
    request: Request,
    ars_id: str = Query(..., alias="arsId"),
    result_type: str = Query("json", alias="resultType"),
) -> SeoulStationArrivalResponse:
    _ = result_type
    verify_api_token(request)
    return await get_seoul_station_arrival_response(ars_id)
