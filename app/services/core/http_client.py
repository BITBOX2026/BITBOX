"""Shared async HTTP client for external API calls."""

import httpx

from app.core.config import settings

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        total_timeout = float(settings.EXTERNAL_HTTP_TIMEOUT_SECONDS)
        _client = httpx.AsyncClient(
            # 3회 시도와 0.5/1초 백오프를 합쳐도 30초 파이프라인 예산 안에
            # 끝나도록 단일 시도를 8초로 제한합니다.
            timeout=httpx.Timeout(total_timeout, connect=min(5.0, total_timeout)),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
