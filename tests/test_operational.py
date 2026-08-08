"""Operational behavior tests."""

import asyncio
import re

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.request_context import request_context_middleware, request_id_for
from app.main import readiness_check


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    })


def test_request_id_accepts_safe_proxy_value() -> None:
    request = _request([(b"x-request-id", b"proxy-request-123")])
    assert request_id_for(request) == "proxy-request-123"


def test_request_id_replaces_untrusted_value() -> None:
    request = _request([(b"x-request-id", b"bad value with spaces")])
    assert re.fullmatch(r"[0-9a-f]{32}", request_id_for(request))


def test_request_context_adds_operational_headers() -> None:
    async def call_next(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    response = asyncio.run(request_context_middleware(_request(), call_next))
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert int(response.headers["x-response-time-ms"]) >= 0
    assert response.headers["cache-control"] == "no-store"


def test_readiness_contract() -> None:
    response = readiness_check()
    assert response.status == "ready"
    assert response.version
