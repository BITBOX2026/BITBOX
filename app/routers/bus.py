"""Bus arrival API routes."""

from fastapi import APIRouter, Request, Response

from app.core.auth import verify_api_token
from app.core.rate_limiter import limiter
from app.schemas.bus import DefaultBusArrivalResponse
from app.services.bus_service import get_default_bus_arrivals

router = APIRouter()


@router.get(
    "/default",
    response_model=DefaultBusArrivalResponse,
    # 프론트는 도착 분 필드가 없을 때 해당 버스를 건너뜁니다. None을 JSON null로
    # 보내면 JavaScript의 `null >= 0`이 true가 되어 0분 버스로 잘못 표시됩니다.
    response_model_exclude_none=True,
)
@limiter.limit("30/minute")
async def get_default_bus_arrival(
    request: Request,
    response: Response,
) -> DefaultBusArrivalResponse:
    verify_api_token(request)
    result = await get_default_bus_arrivals()
    if not result.success:
        response.status_code = 502
    return result
