"""Run real, locally stored voice samples through the BITBOX safety pipeline."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.pipeline import _run_pipeline_core

REQUIRED_COLUMNS = {
    "sample_id",
    "audio_path",
    "expected_intent",
    "expected_bus_number",
    "expected_outcome",
    "environment",
    "speaker_group",
}
ALLOWED_OUTCOMES = {"success", "reconfirm", "confirmation", "error"}
MAX_SAMPLE_BYTES = 20 * 1024 * 1024


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing columns: {', '.join(sorted(missing))}")
        samples: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            sample = {key: (row.get(key) or "").strip() for key in REQUIRED_COLUMNS}
            if not sample["sample_id"] or sample["sample_id"] in seen_ids:
                raise ValueError(f"line {line_number}: sample_id must be unique and non-empty")
            if sample["expected_outcome"] not in ALLOWED_OUTCOMES:
                raise ValueError(f"line {line_number}: unsupported expected_outcome")
            if not sample["audio_path"]:
                raise ValueError(f"line {line_number}: audio_path is required")
            seen_ids.add(sample["sample_id"])
            samples.append(sample)
    if not samples:
        raise ValueError("manifest contains no samples")
    return samples


def observed_outcome(result: dict) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if result.get("status") == "success" and data.get("confirmation"):
        return "confirmation"
    if result.get("status") == "error" and data.get("needs_confirmation"):
        return "reconfirm"
    return "success" if result.get("status") == "success" else "error"


def summarize_results(results: list[dict[str, object]]) -> dict[str, object]:
    bus_cases = [row for row in results if row["expected_bus_number"]]
    intent_cases = [row for row in results if row["expected_intent"]]
    exact_bus = sum(row["bus_number_match"] is True for row in bus_cases)
    exact_intent = sum(row["intent_match"] is True for row in intent_cases)
    outcome_matches = sum(row["outcome_match"] is True for row in results)
    dangerous = sum(row["dangerous_substitution"] is True for row in results)
    return {
        "samples": len(results),
        "bus_number_cases": len(bus_cases),
        "bus_number_accuracy": round(exact_bus / len(bus_cases), 4) if bus_cases else None,
        "intent_cases": len(intent_cases),
        "intent_accuracy": round(exact_intent / len(intent_cases), 4) if intent_cases else None,
        "outcome_accuracy": round(outcome_matches / len(results), 4),
        "dangerous_substitutions": dangerous,
        "privacy": "Audio and transcripts are not included in this report.",
    }


async def run_benchmark(samples: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    results: list[dict[str, object]] = []
    for sample in samples:
        audio_path = Path(sample["audio_path"]).expanduser().resolve()
        if not audio_path.is_file():
            raise ValueError(f"audio file not found for {sample['sample_id']}: {audio_path}")
        if audio_path.stat().st_size > MAX_SAMPLE_BYTES:
            raise ValueError(f"audio file exceeds 20 MiB for {sample['sample_id']}")
        pipeline_result = await _run_pipeline_core(
            audio_path.read_bytes(),
            audio_path.name,
            f"benchmark-{sample['sample_id']}",
        )
        data = pipeline_result.get("data") if isinstance(pipeline_result.get("data"), dict) else {}
        recognized_bus = str(data.get("bus_number") or "")
        recognized_intent = str(data.get("intent") or "")
        expected_bus = sample["expected_bus_number"]
        expected_intent = sample["expected_intent"]
        outcome = observed_outcome(pipeline_result)
        dangerous_substitution = bool(
            pipeline_result.get("status") == "success"
            and expected_bus
            and recognized_bus
            and recognized_bus != expected_bus
        )
        results.append({
            "sample_id": sample["sample_id"],
            "environment": sample["environment"],
            "speaker_group": sample["speaker_group"],
            "expected_intent": expected_intent,
            "recognized_intent": recognized_intent,
            "intent_match": recognized_intent == expected_intent if expected_intent else None,
            "expected_bus_number": expected_bus,
            "recognized_bus_number": recognized_bus,
            "bus_number_match": recognized_bus == expected_bus if expected_bus else None,
            "expected_outcome": sample["expected_outcome"],
            "observed_outcome": outcome,
            "outcome_match": outcome == sample["expected_outcome"],
            "dangerous_substitution": dangerous_substitution,
        })
    return results, summarize_results(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-dangerous-substitutions", type=int, default=0)
    parser.add_argument("--min-number-accuracy", type=float, default=0.0)
    args = parser.parse_args()
    if args.max_dangerous_substitutions < 0 or not 0 <= args.min_number_accuracy <= 1:
        parser.error("thresholds must be non-negative and accuracy must be between 0 and 1")
    try:
        samples = load_manifest(args.manifest)
        results, summary = asyncio.run(run_benchmark(samples))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    report = {"summary": summary, "results": results}
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    number_accuracy = summary["bus_number_accuracy"]
    return int(
        int(summary["dangerous_substitutions"]) > args.max_dangerous_substitutions
        or (number_accuracy is not None and float(number_accuracy) < args.min_number_accuracy)
    )


if __name__ == "__main__":
    raise SystemExit(main())
