"""Focus-area criteria and active-slot rules (spec §7.2)."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.coach_readiness import CoachFocusArea
from app.routers.coach_readiness import (
    create_focus_area,
    patch_focus_area,
)
from app.schemas.coach_readiness import (
    FocusAreaCreate,
    FocusAreaPatch,
    FocusCriterionWrite,
    FocusGroupWrite,
)
from app.services.coach_conversational_progress import ProgressSnapshot
from app.services.coach_readiness import focus as focus_rules

GROUP = {"role_family": "Delivery Lead", "interview_type": "behavioural"}
DIMENSIONS = {"specificity": "developing"}


def _snapshot(
    session_id: str,
    completed_at: datetime,
    *,
    level: str = "developing",
    role_family: str = "Delivery Lead",
    interview_type: str = "behavioural",
) -> ProgressSnapshot:
    return ProgressSnapshot(
        session_id=session_id,
        compatibility_key=f"key-{session_id}",
        activity_version=1,
        completed_at=completed_at,
        session_level=level,
        dimensions={**DIMENSIONS, "specificity": level},
        role_family=role_family,
        interview_type=interview_type,
        evaluation_contract_version="coach_conversational_report_v1",
        difficulty="realistic",
    )


def _area(*, created_at=datetime(2026, 5, 1), criteria=None) -> CoachFocusArea:
    return CoachFocusArea(
        id="focus-1",
        version=1,
        status="active",
        active_slot=1,
        title="Make answers specific",
        dimension="specificity",
        group_json=GROUP,
        criteria_json=criteria
        or [
            {"kind": "level", "count": 2},
            {"kind": "practice", "count": 3},
        ],
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)


def _create(title: str = "Focus") -> FocusAreaCreate:
    return FocusAreaCreate(
        title=title,
        dimension="specificity",
        group=FocusGroupWrite(**GROUP),
        criteria=[FocusCriterionWrite(kind="practice", count=3)],
    )


@pytest.mark.asyncio
async def test_fourth_active_focus_area_rejected(db_session: AsyncSession) -> None:
    for index in range(3):
        await create_focus_area(_create(f"Focus {index}"), db_session)

    with pytest.raises(HTTPException) as rejected:
        await create_focus_area(_create("Fourth"), db_session)

    assert rejected.value.status_code == 409
    assert rejected.value.detail == "limit_reached"


@pytest.mark.asyncio
async def test_stale_version_conflict_keeps_state(db_session: AsyncSession) -> None:
    created = await create_focus_area(_create("Original"), db_session)

    with pytest.raises(HTTPException) as conflict:
        await patch_focus_area(
            created.id,
            FocusAreaPatch(expected_version=created.version + 1, title="Changed"),
            db_session,
        )

    assert conflict.value.status_code == 409
    assert conflict.value.detail == "version_conflict"
    stored = await db_session.get(CoachFocusArea, created.id)
    assert stored is not None
    assert stored.title == "Original"


@pytest.mark.asyncio
async def test_level_criterion_requires_group(db_session: AsyncSession) -> None:
    payload = FocusAreaCreate(
        title="No group",
        dimension="specificity",
        criteria=[FocusCriterionWrite(kind="level", count=2)],
    )
    with pytest.raises(HTTPException) as invalid:
        await create_focus_area(payload, db_session)
    assert invalid.value.status_code == 422


def test_level_criterion_counts_only_post_creation_same_group() -> None:
    area = _area(created_at=datetime(2026, 5, 1))
    snapshots = [
        _snapshot("before", datetime(2026, 4, 1), level="interview_ready"),
        _snapshot("wrong-group", datetime(2026, 5, 2), level="strong",
                  role_family="Data"),
        _snapshot("weak", datetime(2026, 5, 2), level="developing"),
        _snapshot("strong", datetime(2026, 5, 3), level="interview_ready"),
    ]

    rows = focus_rules.criterion_reads(area, snapshots, [])
    level = next(row for row in rows if row.kind == "level")

    assert level.completed == 1
    assert level.status == "in_progress"


def test_practice_items_never_satisfy_level_criterion() -> None:
    area = _area(criteria=[{"kind": "level", "count": 2}])
    plan = type(
        "Plan",
        (),
        {
            "started_at": datetime(2026, 5, 2),
            "items_json": [{"status": "done", "minutes": 15} for _ in range(3)],
        },
    )()

    rows = focus_rules.criterion_reads(area, [], [plan])

    assert rows[0].status == "no_evidence_yet"
    assert rows[0].completed == 0


def test_older_completed_items_do_not_count_for_practice_criterion() -> None:
    area = _area(
        created_at=datetime(2026, 5, 2),
        criteria=[{"kind": "practice", "count": 2}],
    )
    older = type(
        "Plan",
        (),
        {
            "started_at": datetime(2026, 4, 1),
            "items_json": [
                {"status": "done", "completed_at": "2026-05-01T10:00:00"},
                {"status": "done", "completed_at": "2026-05-03T10:00:00"},
            ],
        },
    )()

    rows = focus_rules.criterion_reads(area, [], [older])

    assert rows[0].completed == 1
    assert rows[0].status == "in_progress"
