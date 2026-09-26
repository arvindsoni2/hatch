"""Compatibility-grouped conversational progress contracts."""

from datetime import datetime

import pytest

from app.services.coach_conversational_progress import (
    ProgressSelector,
    ProgressSnapshot,
    derive_trend,
    get_progress,
)


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (("needs_work", "developing"), "improving"),
        (("needs_work", "strong"), "improving"),
        (("strong", "developing"), "declining"),
        (("developing", "developing"), "stable"),
        (("needs_work", "interview_ready", "developing"), "mixed"),
        (("interview_ready", "needs_work", "developing"), "mixed"),
        (("needs_work", "needs_work", "interview_ready"), "improving"),
        (("needs_work", "interview_ready", "interview_ready"), "stable"),
        (("not_assessed", "developing"), "not_enough_evidence"),
    ],
)
def test_trend_vectors(levels, expected):
    assert derive_trend(levels) == expected


def test_progress_partitions_compatibility_and_reports_truncation():
    snapshots = [
        ProgressSnapshot("s-1", "job-a-v1", 1, datetime(2026, 1, 1), "needs_work", {}, "app-1", "Acme", "Engineer"),
        ProgressSnapshot("s-2", "job-a-v1", 2, datetime(2026, 2, 1), "developing", {}, "app-1", "Acme", "Engineer"),
        ProgressSnapshot("s-3", "job-b-v1", 1, datetime(2026, 3, 1), "strong", {}, "app-2", "Beta", "Analyst"),
    ]

    result = get_progress(
        ProgressSelector(mode="filtered", company_name="Acme"),
        group_limit=1,
        snapshots=snapshots,
    )

    assert result.total_groups == 1
    assert result.returned_groups == 1
    assert result.groups_truncated is False
    assert result.groups[0]["compatibility_key"] == "job-a-v1"
    assert result.groups[0]["trend"] == "improving"
    assert "percentage" not in result.groups[0]


def test_progress_exact_selector_conflicts_with_broad_filter():
    with pytest.raises(ValueError, match="exact selector"):
        ProgressSelector(
            mode="exact", session_id="s-1", company_name="Acme"
        )


def test_progress_reports_pre_truncation_group_count():
    snapshots = [
        ProgressSnapshot("s-1", "job-a-v1", 1, datetime(2026, 1, 1), "developing", {}),
        ProgressSnapshot("s-2", "job-b-v1", 1, datetime(2026, 2, 1), "strong", {}),
    ]

    result = get_progress(
        ProgressSelector(mode="filtered"), group_limit=1, snapshots=snapshots
    )

    assert result.total_groups == 2
    assert result.returned_groups == 1
    assert result.groups_truncated is True
