"""Verify the public production boundary after a deployment."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _request(url: str) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("production smoke requests require HTTPS")
    request = Request(url, headers={"User-Agent": "BITBOX-production-smoke/1.0"})
    try:
        # The URL is constrained to HTTPS immediately above.
        with urlopen(request, timeout=15) as response:  # nosec B310
            return response.status, dict(response.headers.items()), response.read(1_000_000)
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read(1_000_000)


def _certificate_days_remaining(hostname: str, port: int) -> int:
    context = ssl.create_default_context()
    with (
        socket.create_connection((hostname, port), timeout=10) as raw_socket,
        context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket,
    ):
        certificate = tls_socket.getpeercert()
    expires_at = datetime.strptime(certificate["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return (expires_at - datetime.now(UTC)).days


def verify(base_url: str, minimum_certificate_days: int) -> list[str]:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/"):
        return ["base URL must be an HTTPS origin without a path"]

    origin = base_url.rstrip("/")
    errors: list[str] = []

    health_status, health_headers, health_body = _request(f"{origin}/health")
    if health_status != 200:
        errors.append(f"/health returned {health_status}")
    else:
        try:
            if json.loads(health_body).get("status") != "ok":
                errors.append("/health did not report status=ok")
        except (json.JSONDecodeError, AttributeError):
            errors.append("/health did not return the expected JSON")

    normalized_headers = {name.lower(): value for name, value in health_headers.items()}
    required_headers = {
        "content-security-policy",
        "strict-transport-security",
        "x-content-type-options",
        "x-frame-options",
        "x-request-id",
    }
    for header in sorted(required_headers - normalized_headers.keys()):
        errors.append(f"missing security header: {header}")

    ready_status, _, ready_body = _request(f"{origin}/ready")
    if ready_status != 200:
        errors.append(f"/ready returned {ready_status}")
    else:
        try:
            if json.loads(ready_body).get("status") != "ready":
                errors.append("/ready did not report status=ready")
        except (json.JSONDecodeError, AttributeError):
            errors.append("/ready did not return the expected JSON")

    internal_status, _, _ = _request(f"{origin}/internal/status")
    if internal_status != 404:
        errors.append(f"/internal/status must be hidden externally, got {internal_status}")

    certificate_days = _certificate_days_remaining(parsed.hostname, parsed.port or 443)
    if certificate_days < minimum_certificate_days:
        errors.append(
            f"TLS certificate has only {certificate_days} days remaining "
            f"(minimum {minimum_certificate_days})"
        )
    else:
        print(f"TLS certificate: {certificate_days} days remaining")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Production HTTPS origin")
    parser.add_argument("--minimum-certificate-days", type=int, default=14)
    args = parser.parse_args()

    try:
        errors = verify(args.url, args.minimum_certificate_days)
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        errors = [f"production connection failed: {exc}"]

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Production smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
