from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.application import Application
from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, SessionQuestion
from app.schemas.coach import (
    CreateSessionRequest,
    ModelAnswerResult,
    QuestionPresentation,
)
from app.services.coach_contracts import CoachDiagnostic
from app.services.coach_service import CoachService
from app.services.coach_session_queue import queue_coach_session
from app.services.coach_session_plan import SessionPlanError
from app.observability import TraceContextToken


async def _timeout(awaitable, _seconds):
    awaitable.close()
    raise TimeoutError


@pytest.mark.asyncio
async def test_queue_creates_visible_stub_and_async_job(db_session):
    request = CreateSessionRequest(
        application_id=None,
        company_name="Iron Mountain",
        role_title="Solutions Architect",
        jd_text="Design customer solutions.",
    )

    with patch("app.services.coach_session_queue.AsyncJobService.run") as run:
        result = await queue_coach_session(request, db_session, MagicMock())

    session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == result["session_id"])
        )
    ).scalar_one()
    async_job = (
        await db_session.execute(
            select(AsyncJob).where(AsyncJob.id == result["job_id"])
        )
    ).scalar_one()
    assert session.status == "setup"
    assert session.company_name == "Iron Mountain"
    assert async_job.type == "coach_session"
    run.assert_called_once()
    assert isinstance(run.call_args.kwargs["trace_context"], TraceContextToken)
    assert run.call_args.kwargs["trace_attributes"] == {
        "hatch.coach.session_id": result["session_id"],
        "hatch.async_job_id": result["job_id"],
    }
    assert run.call_args.kwargs["telemetry_operation"] == "session_create"
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_queue_deduplicates_linked_application(db_session):
    existing = InterviewSession(
        application_id="app-1",
        company_name="Iron Mountain",
        role_title="Solutions Architect",
        config={},
        status="setup",
    )
    db_session.add(existing)
    await db_session.commit()

    result = await queue_coach_session(
        CreateSessionRequest(
            application_id="app-1",
            company_name="Iron Mountain",
            role_title="Solutions Architect",
        ),
        db_session,
        MagicMock(),
        deduplicate_application=True,
    )

    assert result["session_id"] == existing.id
    assert result["created"] is False
    sessions = (await db_session.execute(select(InterviewSession))).scalars().all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_default_session_list_hides_user_abandoned_but_keeps_failed(db_session):
    db_session.add_all(
        [
            InterviewSession(
                application_id="app-deleted",
                company_name="Veovo",
                role_title="Agile Delivery Lead",
                config={},
                status="abandoned",
            ),
            InterviewSession(
                application_id="app-failed",
                company_name="Acme",
                role_title="Delivery Lead",
                config={},
                status="failed",
            ),
        ]
    )
    await db_session.commit()

    from app.repositories.session_repository import SessionRepository

    visible = await SessionRepository(db_session).list_sessions(
        exclude_abandoned=True,
    )

    assert [session.status for session in visible] == ["failed"]


@pytest.mark.asyncio
async def test_create_job_timeout_fails_stub_with_diagnostic(db_session):
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    request = CreateSessionRequest(
        company_name="Timeout Ltd",
        role_title="Engineer",
    )
    with (
        patch("app.services.coach_session_queue.AsyncJobService.run") as run,
        patch(
            "app.services.coach_session_queue.run_with_stage_deadline",
            new=AsyncMock(side_effect=_timeout),
        ),
        patch("app.database.AsyncSessionLocal", session_factory),
    ):
        result = await queue_coach_session(request, db_session)
        await run.call_args.args[1]

    db_session.expire_all()
    session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == result["session_id"])
        )
    ).scalar_one()
    job = (
        await db_session.execute(
            select(AsyncJob).where(AsyncJob.id == result["job_id"])
        )
    ).scalar_one()
    assert session.status == "failed"
    assert session.diagnostics["stages"]["question_generation"]["final"][
        "gate_codes"
    ] == ["coach_job_timeout"]
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_create_cancellation_during_drills_rolls_back_questions_and_activation(
    db_session,
):
    stub = InterviewSession(
        company_name="Timeout Ltd",
        role_title="Engineer",
        config={"question_count": 1},
        status="setup",
    )
    db_session.add(stub)
    await db_session.commit()
    stub_id = stub.id

    diagnostic = CoachDiagnostic(
        stage="model_answer",
        outcome="completed",
        execution_mode="llm",
        prompt_id="model_answer",
        prompt_version="2.0.0",
        output_schema_version="1.0.0",
        model_id="test-model",
        attempt_count=1,
        repair_count=0,
        gate_codes=[],
        duration_ms=1,
    )
    service = CoachService.__new__(CoachService)
    service.research_company = AsyncMock(return_value=None)
    service._researcher = MagicMock(last_diagnostic=None)
    service._question_gen = MagicMock()
    service._question_gen.generate = AsyncMock(
        return_value=[
            QuestionPresentation(
                id="generated-1",
                text="Explain a migration.",
                category="Technical",
                difficulty="medium",
                requirement_id="requirement-1",
                num=1,
                total=1,
            )
        ]
    )
    service._model_answer_gen = MagicMock()
    service._model_answer_gen.generate = AsyncMock(
        return_value=ModelAnswerResult(
            model_answer="",
            star_breakdown={},
            evidence_references=[],
            diagnostic=diagnostic,
        )
    )

    service._drills = MagicMock()
    service._drills.build_drills = AsyncMock(
        side_effect=asyncio.CancelledError("cancelled")
    )

    request = CreateSessionRequest(
        company_name="Timeout Ltd",
        role_title="Engineer",
        config={"question_count": 1},
    )
    with patch(
        "app.services.coach_service._load_candidate_summary", return_value="Evidence"
    ):
        with pytest.raises(asyncio.CancelledError, match="cancelled"):
            await service.create_session(request, db_session, session_id=stub_id)
    await db_session.rollback()

    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, stub_id)
    questions = (await db_session.execute(select(SessionQuestion))).scalars().all()
    assert persisted is not None
    assert persisted.status == "setup"
    assert questions == []


def _conversation_request() -> CreateSessionRequest:
    return CreateSessionRequest.model_validate(
        {
            "company_name": "Example Ltd",
            "role_title": "Architect",
            "jd_text": "Design secure systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "mixed",
                "difficulty": "realistic",
                "duration_minutes": 15,
                "planned_question_count": 3,
                "role_family": "solution_architecture",
                "role_level": "senior",
                "locale": "en-GB",
                "focus_areas": ["architecture"],
                "allowed_answer_modes": ["audio", "text"],
                "evidence_selection": {
                    "application_cv": "none",
                    "master_cv": "exclude",
                    "question_bank": "exclude",
                    "selected_question_bank_record_ids": [],
                    "company_research": "exclude",
                    "draft_evidence_consent": False,
                },
                "retention": {
                    "audio": "delete_after_processing",
                    "transcript": "retain",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_conversational_queue_is_fail_closed_while_flag_is_off(
    db_session,
) -> None:
    with (
        patch(
            "app.services.coach_session_queue.settings.HATCH_COACH_CONVERSATIONAL_ENABLED",
            False,
        ),
        pytest.raises(SessionPlanError, match="coach_conversation_not_enabled"),
    ):
        await queue_coach_session(_conversation_request(), db_session)

    assert (
        not (
            await db_session.execute(
                select(InterviewSession).where(
                    InterviewSession.experience_version == "conversational_v1"
                )
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_conversational_deduplication_never_reuses_a_legacy_session(
    db_session,
) -> None:
    legacy = InterviewSession(
        application_id="application_1",
        company_name="Example Ltd",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="legacy_v1",
    )
    db_session.add(legacy)
    await db_session.commit()
    payload = _conversation_request().model_dump(mode="json")
    payload["application_id"] = "application_1"
    request = CreateSessionRequest.model_validate(payload)

    with (
        patch(
            "app.services.coach_session_queue.settings.HATCH_COACH_CONVERSATIONAL_ENABLED",
            True,
        ),
        patch("app.services.coach_session_queue.AsyncJobService.run") as run,
    ):
        result = await queue_coach_session(
            request,
            db_session,
            deduplicate_application=True,
        )

    assert result["created"] is True
    assert result["session_id"] != legacy.id
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_conversational_application_dedup_is_atomic_across_sqlite_connections(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'dedup-race.db'}",
        connect_args={"timeout": 10},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as seed_db:
            seed_db.add(
                Application(
                    id="application_race",
                    status="discovered",
                    priority="normal",
                )
            )
            await seed_db.commit()

        payload = _conversation_request().model_dump(mode="json")
        payload["application_id"] = "application_race"
        request = CreateSessionRequest.model_validate(payload)

        async def create() -> dict:
            async with session_factory() as request_db:
                return await queue_coach_session(
                    request,
                    request_db,
                    deduplicate_application=True,
                )

        with (
            patch(
                "app.services.coach_session_queue.settings.HATCH_COACH_CONVERSATIONAL_ENABLED",
                True,
            ),
            patch("app.services.coach_session_queue.AsyncJobService.run") as run,
        ):
            first, second = await asyncio.gather(create(), create())

        assert sorted((first["created"], second["created"])) == [False, True]
        assert first["session_id"] == second["session_id"]
        run.assert_called_once()
        run.call_args.args[1].close()
        async with session_factory() as inspection_db:
            assert (
                await inspection_db.scalar(
                    select(func.count(InterviewSession.id)).where(
                        InterviewSession.application_id == "application_race",
                        InterviewSession.experience_version == "conversational_v1",
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_conversational_queue_claims_before_dispatch_and_worker_uses_fresh_session(
    db_session,
) -> None:
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    with (
        patch(
            "app.services.coach_session_queue.settings.HATCH_COACH_CONVERSATIONAL_ENABLED",
            True,
        ),
        patch("app.services.coach_session_queue.AsyncJobService.run") as run,
        patch("app.database.AsyncSessionLocal", session_factory),
    ):
        result = await queue_coach_session(_conversation_request(), db_session)
        db_session.expire_all()
        claimed = await db_session.get(InterviewSession, result["session_id"])
        assert claimed is not None
        assert (claimed.status, claimed.conversation_state) == ("setup", "planning")
        assert claimed.setup_generation == claimed.setup_attempt_count == 1
        assert claimed.setup_job_id == result["job_id"]
        assert claimed.setup_claim_token is not None
        assert claimed.session_plan_json is None

        await run.call_args.args[1]

    db_session.expire_all()
    completed = await db_session.get(InterviewSession, result["session_id"])
    assert completed is not None
    assert (completed.status, completed.conversation_state) == ("setup", "ready")
    assert completed.session_plan_json is not None
    assert (
        await db_session.scalar(
            select(func.count(SessionQuestion.id)).where(
                SessionQuestion.session_id == result["session_id"]
            )
        )
        == 3
    )
    assert result["experience_version"] == "conversational_v1"


@pytest.mark.asyncio
async def test_conversational_worker_cancellation_releases_setup_claim(
    db_session,
) -> None:
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    with (
        patch(
            "app.services.coach_session_queue.settings.HATCH_COACH_CONVERSATIONAL_ENABLED",
            True,
        ),
        patch("app.services.coach_session_queue.AsyncJobService.run") as run,
        patch("app.database.AsyncSessionLocal", session_factory),
        patch(
            "app.services.coach_session_queue.SessionPlanBuilder.build",
            side_effect=asyncio.CancelledError("shutdown"),
        ),
    ):
        result = await queue_coach_session(_conversation_request(), db_session)
        with pytest.raises(asyncio.CancelledError, match="shutdown"):
            await run.call_args.args[1]

    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, result["session_id"])
    assert persisted is not None
    assert (persisted.status, persisted.conversation_state) == (
        "setup",
        "recoverable_error",
    )
    assert persisted.recoverable_error_scope == "setup"
    assert persisted.setup_job_id is None
    assert persisted.setup_claim_token is None
