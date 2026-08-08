"""Small dependency-free HTTP load smoke test for liveness endpoints."""

import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def request_once(url: str, timeout: float) -> tuple[bool, float]:
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            success = 200 <= response.status < 300
    except Exception:
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
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")

    results: list[tuple[bool, float]] = []
    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(request_once, args.url, args.timeout) for _ in range(args.requests)]
        for future in as_completed(futures):
            results.append(future.result())

    durations = [duration for _, duration in results]
    errors = sum(not success for success, _ in results)
    error_rate = errors / len(results)
    report = {
        "url": args.url,
        "requests": len(results),
        "concurrency": args.concurrency,
        "errors": errors,
        "error_rate": round(error_rate, 4),
        "mean_ms": round(statistics.fmean(durations), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    print(json.dumps(report, ensure_ascii=False))

    return 1 if error_rate > args.max_error_rate or report["p95_ms"] > args.max_p95_ms else 0


if __name__ == "__main__":
    raise SystemExit(main())
