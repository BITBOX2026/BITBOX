"""Shared API token verification for endpoints that consume external services."""

import secrets

from fastapi import HTTPException, Request

from app.services.core.settings_helper import get_setting


def verify_api_token(request: Request) -> None:
    """Validate the configured kiosk token; disabled when no token is configured."""
    expected_token = str(get_setting("API_AUTH_TOKEN") or "").strip()
    if not expected_token:
        return

    provided = (request.headers.get("x-bitbox-token") or "").strip()
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()

    if not provided or not secrets.compare_digest(expected_token, provided):
        raise HTTPException(status_code=401, detail="인증 토큰이 올바르지 않습니다.")
