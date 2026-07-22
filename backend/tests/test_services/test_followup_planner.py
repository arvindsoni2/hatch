"""Tests for FollowUpPlannerService — Phase C."""
from __future__ import annotations

import uuid
from datetime import datetime
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.coach_session import InterviewSession, SessionQuestion
from app.schemas.coach import RubricDimension, SessionRubric
from app.services.followup_planner import FollowUpPlannerService
from app.services.coach_service import CoachService


# ──────────────────────── Test DB setup ──────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture()
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSession() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_session(
    session_id: str | None = None,
    company: str = "Acme Corp",
    role: str = "Senior Engineer",
    coach_mode: str = "voice",
) -> InterviewSession:
    s = InterviewSession(
        id=session_id or str(uuid.uuid4()),
        company_name=company,
        role_title=role,
        config={"question_count": 5},
        status="completed",
        coach_mode=coach_mode,
        created_at=datetime.utcnow(),
        started_at=datetime.utcnow(),
    )
    return s


def _make_rubric(scores: dict[str, int]) -> SessionRubric:
    dims = {
        name: RubricDimension(score=score, score_band="needs_work", evidence=[], drill="")
        for name, score in scores.items()
    }
    return SessionRubric(dimensions=dims, focus_for_next_session="")


# ---------------------------------------------------------------------------
# test_plan_creates_child_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_creates_child_session(db_session: AsyncSession) -> None:
    """plan() should create a new session with parent_session_id set."""
    parent = _make_session()
    db_session.add(parent)
    await db_session.flush()

    # Add questions to parent
    for i in range(3):
        q = SessionQuestion(
            id=str(uuid.uuid4()),
            session_id=parent.id,
            question_num=i + 1,
            text=f"Question {i + 1}",
            category="Behavioural",
            difficulty="medium",
            requirement_id=f"requirement-{i}",
            order_in_session=i + 1,
        )
        db_session.add(q)
    await db_session.flush()

    rubric = _make_rubric({"relevance": 7, "star_structure": 5, "communication": 8})
    svc = FollowUpPlannerService()

    new_id, focus_areas = await svc.plan(parent, rubric, db_session)

    # Verify the new session was created
    from sqlalchemy import select  # noqa
    result = await db_session.execute(
        select(InterviewSession).where(InterviewSession.id == new_id)
    )
    child = result.scalar_one_or_none()

    assert child is not None
    assert child.parent_session_id == parent.id
    assert child.company_name == parent.company_name
    assert child.role_title == parent.role_title
    assert child.status == "setup"
    assert child.coach_mode == parent.coach_mode


@pytest.mark.asyncio
async def test_plan_creates_child_with_questions(db_session: AsyncSession) -> None:
    """plan() should copy questions from the parent to the child session."""
    parent = _make_session()
    db_session.add(parent)
    await db_session.flush()

    for i in range(4):
        q = SessionQuestion(
            id=str(uuid.uuid4()),
            session_id=parent.id,
            question_num=i + 1,
            text=f"Question {i + 1}",
            category="Technical",
            difficulty="medium",
            requirement_id=f"requirement-{i}",
            order_in_session=i + 1,
        )
        db_session.add(q)
    await db_session.flush()

    rubric = _make_rubric({"relevance": 6})
    svc = FollowUpPlannerService()
    new_id, _ = await svc.plan(parent, rubric, db_session)

    from sqlalchemy import select  # noqa
    result = await db_session.execute(
        select(SessionQuestion).where(SessionQuestion.session_id == new_id)
    )
    child_questions = list(result.scalars().all())
    assert len(child_questions) == 4
    assert [q.requirement_id for q in child_questions] == [
        "requirement-0",
        "requirement-1",
        "requirement-2",
        "requirement-3",
    ]


# ---------------------------------------------------------------------------
# test_plan_targets_weakest_dimensions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_targets_weakest_dimensions(db_session: AsyncSession) -> None:
    """focus_areas should contain the names of the lowest-scoring dimensions."""
    parent = _make_session()
    db_session.add(parent)
    await db_session.flush()

    rubric = _make_rubric({
        "relevance": 9,
        "star_structure": 3,       # weakest
        "technical_depth": 4,      # second weakest
        "communication": 8,
        "delivery": 7,
    })

    svc = FollowUpPlannerService()
    _, focus_areas = await svc.plan(parent, rubric, db_session)

    assert "star_structure" in focus_areas
    assert "technical_depth" in focus_areas
    assert len(focus_areas) <= 2


@pytest.mark.asyncio
async def test_plan_empty_rubric_produces_empty_focus(db_session: AsyncSession) -> None:
    """When the rubric has no dimensions, focus_areas should be empty."""
    parent = _make_session()
    db_session.add(parent)
    await db_session.flush()

    rubric = SessionRubric(dimensions={}, focus_for_next_session="")
    svc = FollowUpPlannerService()
    _, focus_areas = await svc.plan(parent, rubric, db_session)

    assert focus_areas == []


@pytest.mark.asyncio
async def test_followup_timeout_rolls_back_without_child(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = _make_session()
    parent.rubric = _make_rubric({"relevance": 5}).model_dump(mode="json")
    db_session.add(parent)
    parent_id = parent.id
    await db_session.commit()
    service = CoachService.__new__(CoachService)
    service._followup_planner = FollowUpPlannerService()

    async def timeout(awaitable, _seconds):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr("app.services.coach_service.run_with_stage_deadline", timeout)

    with pytest.raises(HTTPException) as raised:
        await service.plan_followup_session(parent_id, db_session)

    assert raised.value.status_code == 504
    children = list((await db_session.execute(
        select(InterviewSession).where(InterviewSession.parent_session_id == parent_id)
    )).scalars())
    assert children == []
