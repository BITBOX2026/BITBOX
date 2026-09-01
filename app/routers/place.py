"""Place suggestion API routes."""

import asyncio

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
    # Kakao Local 키워드 검색의 상한이 100자입니다. 여기서 막지 않으면 긴 검색어가
    # 그대로 전달돼 Kakao가 400을 돌려주고, 그 실패가 공용 회로 차단기에 쌓여
    # 정상 이용자의 장소 검색과 /ready 까지 함께 멈춥니다.
    query: str = Query(..., min_length=1, max_length=100, description="검색할 장소명"),
) -> PlaceSuggestResponse:
    """
    장소명 자동완성 후보를 반환합니다.

    이름·카테고리 적합도를 우선하고 거리를 보조 기준으로 최대 5개를 반환합니다.

    검색 결과가 없으면 빈 목록을 반환하지만, Kakao API 장애는 오류로 노출합니다.
    장애를 빈 목록으로 감추면 이용자가 "그런 장소가 없다"로 오해합니다.
    """
    verify_api_token(request)
    async with usage_slot(
        "place",
        max_concurrent=settings.PLACE_MAX_CONCURRENT_REQUESTS,
        daily_limit=settings.PLACE_DAILY_REQUEST_LIMIT,
    ):
        try:
            # 프론트의 8초 제한보다 먼저 끝내, 브라우저가 연결을 끊은 뒤에도
            # 외부 재시도만 계속되는 요청을 남기지 않습니다.
            results = await asyncio.wait_for(
                search_place_suggestions(query, max_results=5),
                timeout=settings.PLACE_REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="장소 검색이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
            ) from exc
        except TransportAPIError as exc:
            raise HTTPException(
                status_code=int(getattr(exc, "http_status", 502)),
                detail=exc.user_message,
            ) from exc
    return PlaceSuggestResponse(
        suggestions=[PlaceSuggestion(**r) for r in results]
    )
