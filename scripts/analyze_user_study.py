"""Summarize real BITBOX-versus-baseline usability task observations."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

REQUIRED_COLUMNS = {
    "participant_id",
    "interface",
    "task_id",
    "success",
    "duration_seconds",
    "taps",
    "retries",
    "satisfaction_1_to_5",
}
ALLOWED_INTERFACES = {"bitbox", "baseline"}


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid success value: {value!r}")


def load_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing columns: {', '.join(sorted(missing))}")

        rows: list[dict[str, object]] = []
        seen_observations: set[tuple[str, str, str]] = set()
        for line_number, raw in enumerate(reader, start=2):
            interface = (raw.get("interface") or "").strip().lower()
            if interface not in ALLOWED_INTERFACES:
                raise ValueError(f"line {line_number}: interface must be bitbox or baseline")
            try:
                duration = float(raw["duration_seconds"])
                taps = int(raw["taps"])
                retries = int(raw["retries"])
                satisfaction = float(raw["satisfaction_1_to_5"])
                success = _parse_bool(raw["success"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"line {line_number}: {exc}") from exc
            if duration < 0 or taps < 0 or retries < 0 or not 1 <= satisfaction <= 5:
                raise ValueError(f"line {line_number}: numeric values are outside allowed ranges")
            observation_key = (
                (raw["participant_id"] or "").strip(),
                interface,
                (raw["task_id"] or "").strip(),
            )
            if not observation_key[0] or not observation_key[2]:
                raise ValueError(f"line {line_number}: participant_id and task_id are required")
            if observation_key in seen_observations:
                raise ValueError(f"line {line_number}: duplicate participant/interface/task observation")
            seen_observations.add(observation_key)
            rows.append({
                "participant_id": observation_key[0],
                "interface": interface,
                "task_id": observation_key[2],
                "success": success,
                "duration_seconds": duration,
                "taps": taps,
                "retries": retries,
                "satisfaction_1_to_5": satisfaction,
            })
    if not rows:
        raise ValueError("study file contains no observations")
    return rows


def summarize_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    participants: set[str] = set()
    for row in rows:
        grouped[str(row["interface"])].append(row)
        participants.add(str(row["participant_id"]))

    interfaces: dict[str, dict[str, float | int]] = {}
    for name, observations in sorted(grouped.items()):
        durations = [float(row["duration_seconds"]) for row in observations]
        taps = [int(row["taps"]) for row in observations]
        retries = [int(row["retries"]) for row in observations]
        satisfaction = [float(row["satisfaction_1_to_5"]) for row in observations]
        successes = sum(bool(row["success"]) for row in observations)
        interfaces[name] = {
            "observations": len(observations),
            "success_rate": round(successes / len(observations), 4),
            "mean_duration_seconds": round(statistics.fmean(durations), 2),
            "median_duration_seconds": round(statistics.median(durations), 2),
            "mean_taps": round(statistics.fmean(taps), 2),
            "mean_retries": round(statistics.fmean(retries), 2),
            "mean_satisfaction": round(statistics.fmean(satisfaction), 2),
        }

    comparison: dict[str, object] | None = None
    if "bitbox" in interfaces and "baseline" in interfaces:
        bitbox = interfaces["bitbox"]
        baseline = interfaces["baseline"]
        baseline_duration = float(baseline["mean_duration_seconds"])
        baseline_taps = float(baseline["mean_taps"])
        paired_rows: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
        for row in rows:
            pair_key = (str(row["participant_id"]), str(row["task_id"]))
            paired_rows[pair_key][str(row["interface"])] = row
        complete_pairs = [
            pair for pair in paired_rows.values()
            if "bitbox" in pair and "baseline" in pair
        ]
        duration_differences = [
            float(pair["baseline"]["duration_seconds"])
            - float(pair["bitbox"]["duration_seconds"])
            for pair in complete_pairs
        ]
        tap_differences = [
            int(pair["baseline"]["taps"]) - int(pair["bitbox"]["taps"])
            for pair in complete_pairs
        ]
        paired = {
            "complete_pairs": len(complete_pairs),
            "mean_duration_saved_seconds": round(statistics.fmean(duration_differences), 2)
            if duration_differences else None,
            "median_duration_saved_seconds": round(statistics.median(duration_differences), 2)
            if duration_differences else None,
            "bitbox_faster_rate": round(
                sum(value > 0 for value in duration_differences) / len(duration_differences),
                4,
            ) if duration_differences else None,
            "mean_taps_saved": round(statistics.fmean(tap_differences), 2)
            if tap_differences else None,
            "bitbox_only_successes": sum(
                bool(pair["bitbox"]["success"]) and not bool(pair["baseline"]["success"])
                for pair in complete_pairs
            ),
            "baseline_only_successes": sum(
                bool(pair["baseline"]["success"]) and not bool(pair["bitbox"]["success"])
                for pair in complete_pairs
            ),
        }
        comparison = {
            "duration_reduction_percent": round(
                (baseline_duration - float(bitbox["mean_duration_seconds"]))
                / baseline_duration
                * 100,
                2,
            ) if baseline_duration else 0.0,
            "tap_reduction_percent": round(
                (baseline_taps - float(bitbox["mean_taps"])) / baseline_taps * 100,
                2,
            ) if baseline_taps else 0.0,
            "success_rate_difference_points": round(
                (float(bitbox["success_rate"]) - float(baseline["success_rate"])) * 100,
                2,
            ),
            "paired": paired,
        }

    return {
        "participants": len(participants),
        "observations": len(rows),
        "interfaces": interfaces,
        "comparison": comparison,
        "interpretation_warning": (
            "Descriptive statistics only. Do not claim statistical significance without "
            "an appropriate study design and analysis."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = summarize_rows(load_rows(args.csv_path))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
