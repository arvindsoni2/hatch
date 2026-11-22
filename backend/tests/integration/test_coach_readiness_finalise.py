"""Finalise lock and source re-check regressions (P6 review H1/H2)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database
from app.config import settings
from app.database import Base, create_sqlite_engine
from app.models.application import Application, InterviewRound
from app.models.coach_session import InterviewSession
from app.models.question_bank import QuestionBankItem
from app.repositories.interview_repository import InterviewRepository
from app.schemas.interview import InterviewRoundUpdate
from app.schemas.question_bank import QuestionBankUpdate
from app.services import coach_reconciliation, question_bank
from app.services.coach_readiness import contracts
from app.services.coach_readiness.contracts import (
    GenerationRequest,
    SourceRef,
    ValidatedOutput,
    finalise_generation,
    input_fingerprint,
)

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'finalise.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(coach_reconciliation, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(tmp_path / "media"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield session_factory, tmp_path / "finalise.db"
    finally:
        await engine.dispose()


def _request(task_id: str, cache_key: str, sources: list[SourceRef]) -> GenerationRequest:
    return GenerationRequest(
        task_id=task_id,
        kind="brief",
        cache_key=cache_key,
        input_fingerprint=input_fingerprint(task_id, sources),
        sources=tuple(sources),
    )


def _output() -> ValidatedOutput:
    return ValidatedOutput(
        text_json={"tips": ["Synthetic grounded tip."]},
        model_identity="qwen3.5-4b-q4km-primary",
        prompt_version="explain-v1",
    )


@pytest.mark.asyncio
async def test_finalise_takes_write_lock_before_source_checks(factory, monkeypatch) -> None:
    session_factory, db_path = factory
    async with session_factory() as db:
        db.add(
            InterviewSession(
                id="locked-session",
                company_name="Synthetic",
                role_title="Engineer",
                config={},
                status="completed",
                conversation_state="completed",
                experience_version="conversational_v1",
                activity_version=1,
                state_version=1,
                deletion_state="not_requested",
                completed_at=datetime(2026, 11, 1),
            )
        )
        await db.commit()
        session = await db.get(InterviewSession, "locked-session")
        request = _request(
            "coach.readiness.explain",
            "lock-case",
            [SourceRef("coach_session", "locked-session", str(session.activity_version))],
        )

    original = contracts.input_fingerprint

    def wrapped(*args, **kwargs):
        connection = sqlite3.connect(db_path, timeout=0.2)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                connection.execute(
                    "UPDATE interview_sessions SET deletion_state='deleting' "
                    "WHERE id='locked-session'"
                )
                connection.commit()
        finally:
            connection.close()
        return original(*args, **kwargs)

    monkeypatch.setattr(contracts, "input_fingerprint", wrapped)

    async with session_factory() as db:
        outcome = await finalise_generation(db, request, _output(), NOW)
        await db.commit()

    assert outcome.status == "succeeded"
    async with session_factory() as db:
        state = await db.scalar(
            text("SELECT deletion_state FROM interview_sessions WHERE id='locked-session'")
        )
        rows = await db.scalar(
            text("SELECT count(*) FROM coach_derived_text WHERE cache_key='lock-case'")
        )
    assert state == "not_requested"
    assert rows == 1


@pytest.mark.asyncio
async def test_question_bank_edit_fences_generation(factory) -> None:
    session_factory, _ = factory
    async with session_factory() as db:
        db.add(
            QuestionBankItem(
                id="fence-item", type="behavioural", title="Synthetic",
                question="Tell me about a synthetic delivery.", answer_draft="Draft",
            )
        )
        await db.commit()
        item = await db.get(QuestionBankItem, "fence-item")
        request = _request(
            "coach.readiness.brief_enhance",
            "edited-item",
            [SourceRef("question_bank_item", "fence-item", item.updated_at.isoformat())],
        )

    async with session_factory() as db:
        await question_bank.update_question_bank_item(
            db, "fence-item", QuestionBankUpdate(title="Edited")
        )
        await db.commit()
    async with session_factory() as db:
        outcome = await finalise_generation(db, request, _output(), NOW)
        await db.commit()
    assert outcome.status == "fenced"


@pytest.mark.asyncio
async def test_rescheduled_round_fences_generation(factory) -> None:
    session_factory, _ = factory
    async with session_factory() as db:
        db.add(Application(id="round-app", status="interview", priority="normal"))
        await db.flush()
        db.add(
            InterviewRound(
                id="fence-round", application_id="round-app", round_number=1,
                type="behavioural", scheduled_at=datetime(2026, 12, 1, 10, 0),
                status="scheduled",
            )
        )
        await db.commit()
        row = await db.get(InterviewRound, "fence-round")
        request = _request(
            "coach.readiness.brief_enhance",
            "rescheduled-round",
            [SourceRef("interview_round", "fence-round", row.updated_at.isoformat())],
        )

    async with session_factory() as db:
        await InterviewRepository(db).update(
            "fence-round", InterviewRoundUpdate(scheduled_at=datetime(2026, 12, 2, 10, 0))
        )
        await db.commit()
    async with session_factory() as db:
        outcome = await finalise_generation(db, request, _output(), NOW)
        await db.commit()
    assert outcome.status == "fenced"
