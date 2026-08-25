"""Small dependency-free HTTP load smoke test for liveness endpoints."""

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

import httpx

_thread_local = threading.local()


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must use http or https and include a host")
    return url


def get_http_client() -> httpx.Client:
    client = getattr(_thread_local, "http_client", None)
    if client is None:
        client = httpx.Client(follow_redirects=False)
        _thread_local.http_client = client
    return client


def request_once(url: str, timeout: float) -> tuple[bool, float]:
    started_at = time.perf_counter()
    try:
        response = get_http_client().get(url, timeout=timeout)
        success = 200 <= response.status_code < 300
    except httpx.HTTPError:
        success = False
    return success, (time.perf_counter() - started_at) * 1000


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")
    try:
        args.url = validate_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        warmup_futures = [
            executor.submit(request_once, args.url, args.timeout)
            for _ in range(args.concurrency)
        ]
        warmup_errors = sum(
            not future.result()[0] for future in as_completed(warmup_futures)
        )

        results: list[tuple[bool, float]] = []
        started_at = time.perf_counter()
        futures = [
            executor.submit(request_once, args.url, args.timeout)
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    durations = [duration for _, duration in results]
    errors = sum(not success for success, _ in results)
    error_rate = errors / len(results)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    report = {
        "url": args.url,
        "requests": len(results),
        "successes": len(results) - errors,
        "concurrency": args.concurrency,
        "warmup_errors": warmup_errors,
        "errors": errors,
        "error_rate": round(error_rate, 4),
        "mean_ms": round(statistics.fmean(durations), 2),
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "max_ms": round(max(durations), 2),
        "throughput_requests_per_second": round(
            len(results) / (elapsed_ms / 1000),
            2,
        ) if elapsed_ms else 0.0,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    serialized = json.dumps(report, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)

    return (
        1
        if warmup_errors
        or error_rate > args.max_error_rate
        or report["p95_ms"] > args.max_p95_ms
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
