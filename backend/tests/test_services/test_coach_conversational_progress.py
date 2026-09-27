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
        ProgressSnapshot("s-1", "job-a-v1", 1, datetime(2026, 1, 1), "needs_work", {"relevance": "needs_work"}, "app-1", "Acme", "Engineer"),
        ProgressSnapshot("s-2", "job-a-v1", 2, datetime(2026, 2, 1), "developing", {"relevance": "developing"}, "app-1", "Acme", "Engineer"),
        ProgressSnapshot("s-3", "job-b-v1", 1, datetime(2026, 3, 1), "strong", {}, "app-2", "Beta", "Analyst"),
    ]

    result = get_progress(
        ProgressSelector(mode="filtered", application_id="app-1"),
        group_limit=1,
        snapshots=snapshots,
    )

    assert result.total_groups == 1
    assert result.returned_groups == 1
    assert result.groups_truncated is False
    group = result.model_dump()["groups"][0]
    assert group["compatibility_key"] == "job-a-v1"
    assert group["trends"]["relevance"] == "improving"
    assert "percentage" not in group


def test_progress_exact_selector_conflicts_with_broad_filter():
    with pytest.raises(ValueError, match="exact selector"):
        ProgressSelector(
            mode="exact", compatibility_key="job-a-v1", application_id="app-1"
        )


def test_progress_reports_pre_truncation_group_count():
    snapshots = [
        ProgressSnapshot("s-1", "job-a-v1", 1, datetime(2026, 1, 1), "developing", {}, "app-1"),
        ProgressSnapshot("s-2", "job-b-v1", 1, datetime(2026, 2, 1), "strong", {}, "app-1"),
    ]

    result = get_progress(
        ProgressSelector(mode="filtered", application_id="app-1"), group_limit=1, snapshots=snapshots
    )

    assert result.total_groups == 2
    assert result.returned_groups == 1
    assert result.groups_truncated is True


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (["developing"], "not_enough_evidence"),
        (["developing", "strong"], "improving"),
        (["strong", "developing"], "declining"),
        (["developing", "developing"], "stable"),
        (["developing", "strong", "developing"], "mixed"),
        (["developing", "not_assessed", "strong", "not_assessed", "developing"], "mixed"),
        (["strong", "developing", "developing", "strong"], "improving"),
    ],
)
def test_group_levels_and_trends_use_each_dimensions_assessed_history(levels, expected):
    snapshots = [
        ProgressSnapshot(
            session_id=f"history-{index}", compatibility_key="key-a",
            activity_version=1, completed_at=datetime(2026, 1, index),
            session_level="developing", application_id="app-a",
            dimensions={"relevance": level, "structure": "strong"},
        )
        for index, level in enumerate(levels, start=1)
    ]
    result = get_progress(
        ProgressSelector(mode="filtered", application_id="app-a"), 20,
        snapshots=snapshots,
    ).model_dump()
    group = result["groups"][0]
    assert group["trends"]["relevance"] == expected
    assert group["trends"]["structure"] == (
        "not_enough_evidence" if len(levels) == 1 else "stable"
    )
    assert group["current_levels"]["relevance"] == levels[-1]
    assert group["current_levels"]["impact"] == "not_assessed"
    assert group["previous_levels"]["impact"] == "not_assessed"
    assert "trend" not in group


def test_different_compatibility_groups_have_independent_dimension_trajectories():
    snapshots = [
        ProgressSnapshot(
            session_id=f"{key}-{index}", compatibility_key=key,
            activity_version=1, completed_at=datetime(2026, 1, index),
            session_level="developing", application_id="app-a",
            dimensions={"relevance": level},
        )
        for key, levels in [
            ("key-a", ["developing", "strong", "developing"]),
            ("key-b", ["strong", "interview_ready", "developing"]),
        ]
        for index, level in enumerate(levels, start=1)
    ]
    groups = get_progress(
        ProgressSelector(mode="filtered", application_id="app-a"), 20,
        snapshots=snapshots,
    ).model_dump()["groups"]
    assert groups[0]["trends"]["relevance"] == "mixed"
    assert groups[1]["trends"]["relevance"] == "declining"


def test_current_and_previous_levels_skip_latest_unassessed_session():
    snapshots = [
        ProgressSnapshot(
            f"skip-{index}", "key-a", 1, datetime(2026, 1, index), "developing",
            {"relevance": level}, "app-a",
        )
        for index, level in enumerate(["developing", "strong", "not_assessed"], start=1)
    ]
    group = get_progress(
        ProgressSelector(mode="filtered", application_id="app-a"), 20,
        snapshots=snapshots,
    ).model_dump()["groups"][0]
    assert group["current_levels"]["relevance"] == "strong"
    assert group["previous_levels"]["relevance"] == "developing"
    assert group["trends"]["relevance"] == "improving"


def test_exact_key_selects_all_compatible_sessions_not_one_session():
    snapshots = [
        ProgressSnapshot("a", "key-a", 1, datetime(2026, 1, 1), "strong", {}),
        ProgressSnapshot("b", "key-a", 1, datetime(2026, 1, 2), "strong", {}),
        ProgressSnapshot("c", "key-b", 1, datetime(2026, 1, 3), "strong", {}),
    ]
    result = get_progress(
        ProgressSelector(mode="exact", compatibility_key="key-a"), 20,
        snapshots=snapshots,
    ).model_dump()
    assert result["total_groups"] == result["returned_groups"] == 1
    assert result["groups_truncated"] is False
    assert [s["session_id"] for s in result["groups"][0]["sessions"]] == ["a", "b"]
    assert result["applied_filters"] == {"compatibility_key": "key-a"}


def test_filtered_progress_requires_a_real_broad_filter():
    with pytest.raises(ValueError, match="filter"):
        ProgressSelector(mode="filtered")


def test_group_order_uses_key_ascending_when_latest_completion_ties():
    snapshots = [
        ProgressSnapshot("z", "key-z", 1, datetime(2026, 1, 1), "strong", {}, "app-a"),
        ProgressSnapshot("b", "key-a", 1, datetime(2026, 1, 1), "strong", {}, "app-a"),
        ProgressSnapshot("a", "key-a", 1, datetime(2026, 1, 1), "strong", {}, "app-a"),
    ]
    result = get_progress(
        ProgressSelector(mode="filtered", application_id="app-a"), 1,
        snapshots=snapshots,
    ).model_dump()
    assert result["total_groups"] == 2
    assert result["groups_truncated"] is True
    assert result["groups"][0]["compatibility_key"] == "key-a"
    assert [s["session_id"] for s in result["groups"][0]["sessions"]] == ["a", "b"]


def test_progress_schema_rejects_incomplete_group_projections():
    from pydantic import ValidationError
    from app.schemas.coach_conversation import ConversationalProgressRead

    with pytest.raises(ValidationError):
        ConversationalProgressRead.model_validate({
            "selector_mode": "exact", "applied_filters": {"compatibility_key": "key-a"},
            "group_limit": 20, "total_groups": 1, "returned_groups": 1,
            "groups_truncated": False, "groups": [{"compatibility_key": "key-a"}],
            "contract_version": "coach_conversational_progress_v2",
        })
