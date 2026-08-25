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


def _secure_ssl_context() -> ssl.SSLContext:
    """Require TLS 1.2+ for every production verification connection."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("production smoke requests require HTTPS")
    headers = {"User-Agent": "BITBOX-production-smoke/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        # The URL is constrained to HTTPS immediately above.
        with urlopen(
            request,
            timeout=15,
            context=_secure_ssl_context(),
        ) as response:  # nosec B310
            return response.status, dict(response.headers.items()), response.read(1_000_000)
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read(1_000_000)


def _certificate_days_remaining(hostname: str, port: int) -> int:
    context = _secure_ssl_context()
    with (
        socket.create_connection((hostname, port), timeout=10) as raw_socket,
        context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket,
    ):
        certificate = tls_socket.getpeercert()
    expires_at = datetime.strptime(certificate["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return (expires_at - datetime.now(UTC)).days


def verify(
    base_url: str,
    minimum_certificate_days: int,
    expected_release_sha: str | None = None,
    check_transit: bool = False,
) -> list[str]:
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
            health_payload = json.loads(health_body)
            if health_payload.get("status") != "ok":
                errors.append("/health did not report status=ok")
            if expected_release_sha and health_payload.get("release_sha") != expected_release_sha:
                errors.append("/health release_sha does not match the deployment commit")
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
            ready_payload = json.loads(ready_body)
            if ready_payload.get("status") != "ready":
                errors.append("/ready did not report status=ready")
            if expected_release_sha and ready_payload.get("release_sha") != expected_release_sha:
                errors.append("/ready release_sha does not match the deployment commit")
        except (json.JSONDecodeError, AttributeError):
            errors.append("/ready did not return the expected JSON")

    internal_status, _, _ = _request(f"{origin}/internal/status")
    if internal_status != 404:
        errors.append(f"/internal/status must be hidden externally, got {internal_status}")

    if check_transit:
        _verify_transit_apis(origin, errors)

    certificate_days = _certificate_days_remaining(parsed.hostname, parsed.port or 443)
    if certificate_days < minimum_certificate_days:
        errors.append(
            f"TLS certificate has only {certificate_days} days remaining "
            f"(minimum {minimum_certificate_days})"
        )
    else:
        print(f"TLS certificate: {certificate_days} days remaining")

    return errors


def _verify_transit_apis(origin: str, errors: list[str]) -> None:
    """Run one bounded real-data check per deployment, never in the schedule."""
    bus_status, _, bus_body = _request(f"{origin}/api/bus/default")
    try:
        bus_payload = json.loads(bus_body)
    except json.JSONDecodeError:
        bus_payload = None
    if (
        bus_status != 200
        or not isinstance(bus_payload, dict)
        or bus_payload.get("success") is not True
    ):
        errors.append("bus arrival API did not return a successful live response")

    place_status, _, place_body = _request(
        f"{origin}/api/places/suggest?query=%EA%B0%95%EB%82%A8%EC%97%AD"
    )
    try:
        suggestions = json.loads(place_body).get("suggestions", [])
    except (json.JSONDecodeError, AttributeError):
        suggestions = []
    if (
        place_status != 200
        or not suggestions
        or suggestions[0].get("category_code") != "SW8"
    ):
        errors.append("place suggestion API did not prioritize the expected station")

    route_request = json.dumps(
        {
            "destination": "강남역 2호선",
            "destination_x": 127.0276,
            "destination_y": 37.4979,
            "transport_mode": "bus",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    route_status, _, route_body = _request(
        f"{origin}/api/route",
        method="POST",
        body=route_request,
    )
    try:
        route_payload = json.loads(route_body)
        route_option = route_payload.get("buses", [])[0]
        detail = route_option.get("routeDetail") or {}
        steps = detail.get("steps") or []
        total_minutes = detail.get("totalMin")
        segment_minutes = sum(int(step.get("durationMin") or 0) for step in steps)
        has_bus = any(step.get("type") == "bus" for step in steps)
        bus_only = all(step.get("type") in {"walk", "bus"} for step in steps)
    except (json.JSONDecodeError, AttributeError, IndexError, TypeError, ValueError):
        route_payload = {}
        total_minutes = None
        segment_minutes = -1
        has_bus = False
        bus_only = False
    if (
        route_status != 200
        or route_payload.get("success") is not True
        or not has_bus
        or not bus_only
        or segment_minutes != total_minutes
    ):
        errors.append("route API did not return a consistent bus-only route")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Production HTTPS origin")
    parser.add_argument("--minimum-certificate-days", type=int, default=14)
    parser.add_argument("--expected-release-sha")
    parser.add_argument(
        "--check-transit",
        action="store_true",
        help="Call each real transit integration once after a deployment",
    )
    args = parser.parse_args()

    try:
        errors = verify(
            args.url,
            args.minimum_certificate_days,
            args.expected_release_sha,
            args.check_transit,
        )
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
