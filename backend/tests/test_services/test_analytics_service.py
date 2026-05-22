"""Tests for AnalyticsRepository — funnel and trend queries."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.repositories.analytics_repository import AnalyticsRepository


# ──────────────────────── Helpers ────────────────────────


async def _insert_app(
    db_session: AsyncSession,
    status: str = "discovered",
) -> Application:
    """Insert a raw Application ORM object for test setup."""
    app = Application(
        id=str(uuid.uuid4()),
        job_id=None,
        status=status,
        priority="normal",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


# ──────────────────────── Tests ────────────────────────


@pytest.mark.asyncio
async def test_funnel_empty_db(db_session: AsyncSession) -> None:
    """FunnelResponse has the correct stages with zero counts when there is no data."""
    repo = AnalyticsRepository(db_session)
    result = await repo.get_funnel()

    assert result.total_tracked == 0
    assert len(result.stages) == 6  # discovered through accepted
    for stage in result.stages:
        assert stage.count == 0
    # First stage never has a conversion rate
    assert result.stages[0].conversion_rate is None


@pytest.mark.asyncio
async def test_funnel_counts_by_status(db_session: AsyncSession) -> None:
    """Funnel counts match the number of applications inserted per status."""
    repo = AnalyticsRepository(db_session)

    # Insert 2 discovered, 1 applied, 1 interview
    await _insert_app(db_session, status="discovered")
    await _insert_app(db_session, status="discovered")
    await _insert_app(db_session, status="applied")
    await _insert_app(db_session, status="interview")

    result = await repo.get_funnel()

    counts_by_status = {s.status: s.count for s in result.stages}
    assert counts_by_status["discovered"] == 2
    assert counts_by_status["applied"] == 1
    assert counts_by_status["interview"] == 1
    assert counts_by_status["shortlisted"] == 0
    assert result.total_tracked == 4


@pytest.mark.asyncio
async def test_weekly_trends_structure(db_session: AsyncSession) -> None:
    """TrendResponse is returned with a weeks list even when the database is empty."""
    repo = AnalyticsRepository(db_session)
    result = await repo.get_weekly_trends(weeks=4)

    assert hasattr(result, "weeks")
    assert isinstance(result.weeks, list)
    # With an empty DB the list may be empty — that is valid behaviour
    for week in result.weeks:
        assert hasattr(week, "week_start")
        assert hasattr(week, "new_applications")
        assert hasattr(week, "reached_interview")
        assert isinstance(week.new_applications, int)
        assert isinstance(week.reached_interview, int)
