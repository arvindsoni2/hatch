"""Concurrent focus activation and the single-active-plan index (AC31, §8.3)."""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.coach_readiness import CoachFocusArea, CoachPracticePlan
from app.routers.coach_readiness import patch_focus_area
from app.schemas.coach_readiness import FocusAreaPatch


def _focus(area_id: str, status: str, slot: int | None) -> CoachFocusArea:
    return CoachFocusArea(
        id=area_id,
        version=1,
        status=status,
        active_slot=slot,
        title=area_id,
        dimension="specificity",
        group_json={"role_family": "Delivery Lead", "interview_type": "behavioural"},
        criteria_json=[{"kind": "practice", "count": 3}],
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
    )


@pytest.mark.asyncio
async def test_concurrent_activation_one_wins(coach_database) -> None:
    async with coach_database() as db:
        db.add_all(
            [
                _focus("one", "active", 1),
                _focus("two", "active", 2),
                _focus("three", "paused", None),
                _focus("four", "paused", None),
            ]
        )
        await db.commit()

    async def activate(area_id: str):
        async with coach_database() as db:
            return await patch_focus_area(
                area_id, FocusAreaPatch(expected_version=1, status="active"), db
            )

    results = await asyncio.gather(
        activate("three"), activate("four"), return_exceptions=True
    )

    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == 409
    assert failures[0].detail == "limit_reached"

    async with coach_database() as db:
        rows = (await db.execute(
            text("SELECT status, active_slot FROM coach_focus_areas")
        )).all()
        assert sum(row[0] == "active" for row in rows) == 3
        assert sorted(row[1] for row in rows if row[0] == "active") == [1, 2, 3]


@pytest.mark.asyncio
async def test_single_active_plan_enforced_by_index(coach_database) -> None:
    async with coach_database() as db:
        index_sql = await db.scalar(
            text(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND name='uq_coach_practice_plans_one_active'"
            )
        )
        assert index_sql is not None
        assert "WHERE status = 'active'" in index_sql

        db.add(CoachPracticePlan(id="plan-one", status="active", items_json=[]))
        await db.commit()
        db.add(CoachPracticePlan(id="plan-two", status="active", items_json=[]))
        with pytest.raises(IntegrityError):
            await db.commit()
