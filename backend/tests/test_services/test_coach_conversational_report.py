"""Deterministic aggregation contracts for conversational Coach reports."""

import pytest

from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    aggregate_root_bundle,
    derive_session_level,
    lower_median,
)


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (("developing",) * 5 + ("not_assessed",) * 2, "developing"),
        (
            ("needs_work",) + ("interview_ready",) * 4 + ("developing", "not_assessed"),
            "developing",
        ),
        (("strong",) * 5 + ("interview_ready", "developing"), "interview_ready"),
        (("strong",) * 5 + ("interview_ready", "needs_work"), "interview_ready"),
        (
            (
                "strong",
                "strong",
                "needs_work",
                "strong",
                "strong",
                "interview_ready",
                "interview_ready",
            ),
            "developing",
        ),
        (("strong",) * 4 + ("not_assessed",) * 3, "not_assessed"),
    ],
)
def test_session_readiness_exact_thresholds(levels, expected):
    assert derive_session_level(dict(zip(CONTENT_DIMENSIONS, levels))) == expected


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (("developing", "strong"), "developing"),
        (("needs_work", "developing", "strong"), "developing"),
        (("needs_work", "strong", "strong", "interview_ready"), "interview_ready"),
    ],
)
def test_lower_median_uses_the_lower_middle(levels, expected):
    assert lower_median(levels) == expected


def test_root_bundle_caps_gap_repair_and_primary_evidence_wins():
    root = AcceptedAnswer(
        attempt_id="attempt-root",
        levels={"impact": "developing"},
    )
    followups = [
        AcceptedAnswer(
            attempt_id="attempt-gap",
            levels={"impact": "strong"},
            target_dimension="impact",
            aggregation_role="gap_repair",
        ),
        AcceptedAnswer(
            attempt_id="attempt-primary",
            levels={"impact": "needs_work"},
            target_dimension="impact",
            aggregation_role="primary_evidence",
        ),
    ]

    result = aggregate_root_bundle(root, followups, "impact")

    assert result.level == "needs_work"
    assert result.contributor_attempt_ids == (
        "attempt-root",
        "attempt-gap",
        "attempt-primary",
    )
    assert result.adjustment_reason == "primary_evidence_floor"


def test_builder_selects_assessed_strengths_and_evidence_backed_priorities():
    from app.services.coach_conversational_report import (
        ReportInputSnapshot,
        build_conversational_report,
    )

    levels = dict(
        zip(
            CONTENT_DIMENSIONS,
            (
                "strong",
                "developing",
                "interview_ready",
                "interview_ready",
                "not_assessed",
                "not_assessed",
                "not_assessed",
            ),
        )
    )
    counts = {
        "planned_questions_total": 2,
        "planned_questions_answered": 2,
        "planned_questions_skipped": 0,
        "follow_ups_asked": 0,
        "follow_ups_answered": 0,
        "accepted_attempts": 2,
        "retry_attempts": 0,
        "unavailable_attempts": 0,
        "hints_used": 0,
    }
    snapshot = ReportInputSnapshot(
        "analysis-session",
        2,
        0,
        (
            (AcceptedAnswer("answer-1", levels), ()),
            (AcceptedAnswer("answer-2", levels), ()),
        ),
        "analysis-key",
        counts,
    )
    report = build_conversational_report(snapshot).persisted_json()
    assert report["counts"] == counts
    assert [item["dimension"] for item in report["strengths"]] == [
        "relevance",
        "specificity",
        "impact",
    ]
    assert [item["dimension"] for item in report["improvement_priorities"]] == [
        "structure",
        "specificity",
    ]
    assert report["improvement_priorities"][0]["contributor_attempt_ids"] == [
        "answer-1",
        "answer-2",
    ]
    assert report["improvement_priorities"][0]["next_action"]
    assert report["unassessed_areas"] == ["role_depth", "clarity", "conciseness"]
    assert len(report["practice_suggestions"]) == 2
    assert report["diagnostics"]["dimension_counts"]["relevance"] == {
        "needs_work": 0,
        "developing": 0,
        "interview_ready": 0,
        "strong": 2,
        "not_assessed": 0,
    }
    assert "retention_summary" not in report
