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
        (("needs_work",) + ("interview_ready",) * 4 + ("developing", "not_assessed"), "developing"),
        (("strong",) * 5 + ("interview_ready", "developing"), "interview_ready"),
        (("strong",) * 5 + ("interview_ready", "needs_work"), "interview_ready"),
        (("strong", "strong", "needs_work", "strong", "strong", "interview_ready", "interview_ready"), "developing"),
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
