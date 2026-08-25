"""Place suggestion API routes."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.auth import verify_api_token
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.core.usage_guard import usage_slot
from app.services.core.exceptions import TransportAPIError
from app.services.transit.kakao_service import search_place_suggestions

router = APIRouter()


class PlaceSuggestion(BaseModel):
    name: str
    address: str
    category: str = ""
    category_code: str = ""
    x: str | None = None
    y: str | None = None


class PlaceSuggestResponse(BaseModel):
    suggestions: list[PlaceSuggestion]


@router.get("/suggest", response_model=PlaceSuggestResponse)
@limiter.limit("60/minute")
async def suggest_places(
    request: Request,
    query: str = Query(..., min_length=1, description="검색할 장소명"),
) -> PlaceSuggestResponse:
    """
    장소명 자동완성 후보를 반환합니다.

    이름·카테고리 적합도를 우선하고 거리를 보조 기준으로 최대 5개를 반환합니다.
    Kakao API 오류 시 빈 리스트를 반환합니다.
    """
    verify_api_token(request)
    async with usage_slot(
        "place",
        max_concurrent=settings.PLACE_MAX_CONCURRENT_REQUESTS,
        daily_limit=settings.PLACE_DAILY_REQUEST_LIMIT,
    ):
        try:
            results = await search_place_suggestions(query, max_results=5)
        except TransportAPIError as exc:
            raise HTTPException(
                status_code=int(getattr(exc, "http_status", 502)),
                detail=exc.user_message,
            ) from exc
    return PlaceSuggestResponse(
        suggestions=[PlaceSuggestion(**r) for r in results]
    )
