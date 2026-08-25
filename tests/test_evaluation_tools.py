"""Tests for evidence-generation tools; no fabricated study outcomes are bundled."""

from scripts.analyze_user_study import summarize_rows
from scripts.voice_benchmark import observed_outcome, summarize_results


def test_user_study_summary_compares_observed_interfaces() -> None:
    rows = [
        {"participant_id": "P01", "interface": "bitbox", "task_id": "arrival", "success": True, "duration_seconds": 20.0, "taps": 2, "retries": 0, "satisfaction_1_to_5": 5.0},
        {"participant_id": "P01", "interface": "baseline", "task_id": "arrival", "success": True, "duration_seconds": 40.0, "taps": 4, "retries": 1, "satisfaction_1_to_5": 3.0},
    ]

    report = summarize_rows(rows)

    assert report["participants"] == 1
    assert report["comparison"]["duration_reduction_percent"] == 50.0
    assert report["comparison"]["tap_reduction_percent"] == 50.0
    assert report["comparison"]["paired"]["complete_pairs"] == 1
    assert report["comparison"]["paired"]["mean_duration_saved_seconds"] == 20.0
    assert report["comparison"]["paired"]["bitbox_faster_rate"] == 1.0
    assert "Descriptive statistics only" in report["interpretation_warning"]


def test_voice_summary_counts_dangerous_substitution_without_transcripts() -> None:
    results = [
        {"expected_bus_number": "3412", "expected_intent": "arrival", "bus_number_match": True, "intent_match": True, "outcome_match": True, "dangerous_substitution": False},
        {"expected_bus_number": "3423", "expected_intent": "arrival", "bus_number_match": False, "intent_match": True, "outcome_match": False, "dangerous_substitution": True},
    ]

    summary = summarize_results(results)

    assert summary["bus_number_accuracy"] == 0.5
    assert summary["dangerous_substitutions"] == 1
    assert "transcripts are not included" in summary["privacy"]


def test_voice_outcome_distinguishes_confirmation_and_reconfirmation() -> None:
    assert observed_outcome({"status": "success", "data": {"confirmation": {"kind": "place"}}}) == "confirmation"
    assert observed_outcome({"status": "error", "data": {"needs_confirmation": True}}) == "reconfirm"
