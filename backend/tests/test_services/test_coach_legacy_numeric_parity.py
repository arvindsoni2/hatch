"""AC-29: compare one legacy numeric report with its pre-Phase-1 output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services.coach_aggregation import build_deterministic_report


BASELINE_COMMIT = "52ded582babf684e90325f000233e811914f7710"
BASELINE_FILE = Path(__file__).with_name("coach_legacy_numeric_baseline.json")
SCORES_OLD = {
    "relevance": 3,
    "star_structure": 3,
    "technical_depth": 3,
    "conciseness": 3,
    "communication": 3,
    "impact_metrics": 3,
}
SCORES_BEHAVIOURAL = {
    "relevance": 9,
    "star_structure": 8,
    "technical_depth": 7,
    "conciseness": 8,
    "communication": 9,
    "impact_metrics": 7,
}
SCORES_TECHNICAL = {
    "relevance": 5,
    "star_structure": 6,
    "technical_depth": 5,
    "conciseness": 5,
    "communication": 6,
    "impact_metrics": 6,
}


def _recording(
    recording_id: str,
    question_id: str,
    minute: int,
    *,
    state: str = "completed",
    evaluation: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=recording_id,
        question_id=question_id,
        created_at=datetime(2026, 1, 15, 10, minute, tzinfo=timezone.utc),
        evaluation_state=state,
        evaluation_json=json.dumps(evaluation) if evaluation is not None else None,
    )


def legacy_report_payload() -> dict:
    """Use only the legacy builder's pre-Phase-1 input interface."""
    questions = [
        SimpleNamespace(
            id=f"synthetic-q-{index}",
            order_in_session=index,
            text=f"Synthetic interview question {index}",
            category=category,
        )
        for index, category in enumerate(
            ("Behavioural", "Technical", "Technical", "Technical", "Domain"),
            start=1,
        )
    ]
    recordings = [
        _recording(
            "synthetic-old-attempt",
            "synthetic-q-1",
            0,
            evaluation={"overall": 3.0, "scores": SCORES_OLD},
        ),
        _recording(
            "synthetic-accepted-attempt",
            "synthetic-q-1",
            5,
            evaluation={
                "overall": 8.0,
                "scores": SCORES_BEHAVIOURAL,
                "evidence_references": ["Synthetic migration handoff"],
                "rubric": {
                    "dimensions": {
                        "relevance": {
                            "score": 9,
                            "score_band": "strong",
                            "evidence": ["Synthetic migration handoff"],
                        },
                        "impact_metrics": {
                            "score": 7,
                            "score_band": "good",
                            "evidence": ["Synthetic release count"],
                        },
                    }
                },
            },
        ),
        _recording(
            "synthetic-technical-attempt",
            "synthetic-q-2",
            6,
            evaluation={
                "overall": 5.5,
                "scores": SCORES_TECHNICAL,
                "evidence_references": ["Synthetic service recovery"],
                "rubric": {
                    "dimensions": {
                        "relevance": {
                            "score": 5,
                            "score_band": "needs_work",
                            "evidence": ["Synthetic service recovery"],
                        },
                        "impact_metrics": {
                            "score": 6,
                            "score_band": "needs_work",
                            "evidence": ["Synthetic checkpoint count"],
                        },
                    }
                },
            },
        ),
        _recording("synthetic-skipped-attempt", "synthetic-q-3", 7, state="skipped"),
        _recording(
            "synthetic-unavailable-attempt", "synthetic-q-4", 8, state="unavailable"
        ),
    ]
    return build_deterministic_report(
        "synthetic-legacy-parity", questions, recordings
    ).model_dump(mode="json")


def test_legacy_numeric_report_matches_pre_phase1_baseline() -> None:
    assert BASELINE_FILE.is_file(), "AC-29 pre-Phase-1 baseline artifact is missing"
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    assert baseline["baseline_commit"] == BASELINE_COMMIT
    report = legacy_report_payload()
    assert report == baseline["report"]
    assert report["overall_score"] == 6.8
    assert report["category_scores"] == {"Behavioural": 8.0, "Technical": 5.5}
    assert (
        report["question_count_total"],
        report["question_count_evaluated"],
        report["question_count_skipped"],
        report["question_count_unavailable"],
        report["question_count_unanswered"],
    ) == (5, 2, 1, 1, 1)
    assert "session_level" not in report


if __name__ == "__main__":
    print(
        json.dumps(
            {"baseline_commit": BASELINE_COMMIT, "report": legacy_report_payload()},
            sort_keys=True,
        )
    )
