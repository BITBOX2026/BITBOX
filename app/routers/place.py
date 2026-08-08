"""Place suggestion API routes."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.core.auth import verify_api_token
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.core.usage_guard import usage_slot
from app.services.transit.kakao_service import search_place_suggestions

router = APIRouter()


class PlaceSuggestion(BaseModel):
    name: str
    address: str
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

    기기 위치 기준으로 가장 가까운 순서로 최대 5개 결과를 반환합니다.
    Kakao API 오류 시 빈 리스트를 반환합니다.
    """
    verify_api_token(request)
    async with usage_slot(
        "place",
        max_concurrent=settings.PLACE_MAX_CONCURRENT_REQUESTS,
        daily_limit=settings.PLACE_DAILY_REQUEST_LIMIT,
    ):
        results = await search_place_suggestions(query, max_results=5)
    return PlaceSuggestResponse(
        suggestions=[PlaceSuggestion(**r) for r in results]
    )
