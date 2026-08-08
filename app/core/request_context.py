"""Request correlation and privacy-safe access logging."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.logger import get_logger

logger = get_logger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def request_id_for(request: Request) -> str:
    """Return the trusted request ID assigned by the proxy or application."""
    existing = getattr(request.state, "request_id", None)
    if existing:
        return str(existing)

    supplied = (request.headers.get("x-request-id") or "").strip()
    request_id = supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    return request_id


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a correlation ID and log request metadata without user input."""
    request_id = request_id_for(request)
    started_at = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        logger.exception(
            "[%s] request failed method=%s path=%s duration_ms=%d",
            request_id,
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = round((time.monotonic() - started_at) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    if request.url.path.startswith("/api/") or request.url.path in {"/health", "/ready"}:
        response.headers["Cache-Control"] = "no-store"
    logger.info(
        "[%s] request method=%s path=%s status=%d duration_ms=%d",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response
