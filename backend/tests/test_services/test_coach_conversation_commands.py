"""Command-level contracts for the conversational Coach foundation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from app.models.async_job import AsyncJob
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import (
    ConversationCommandError,
    ConversationCommandService,
)


@pytest_asyncio.fixture
async def command_database(tmp_path: Path):
    database = tmp_path / "commands.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


def command(
    command_type: str,
    *,
    version: int,
    payload: dict[str, object] | None = None,
    command_id: str | None = None,
) -> ConversationCommandRequest:
    return ConversationCommandRequest.model_validate(
        {
            "command_id": command_id or f"cmd-{command_type}-{version}",
            "command_type": command_type,
            "expected_state_version": version,
            "payload": payload or {},
            "contract_version": "coach_conversation_command_v1",
        }
    )


async def seed_session(
    db: AsyncSession,
    *,
    state: str = "ready",
    status: str = "setup",
    version: int = 0,
    question_count: int = 2,
) -> tuple[InterviewSession, list[SessionQuestion]]:
    session = InterviewSession(
        id=f"session-{state}-{version}-{question_count}",
        company_name="Example",
        role_title="Architect",
        experience_version="conversational_v1",
        status=status,
        conversation_state=state,
        state_version=version,
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
        session_plan_json={
            "retention": {
                "audio": "delete_after_processing",
                "transcript": "retain",
            }
        },
        planning_request_json={
            "company_name": "Example",
            "role_title": "Architect",
            "jd_text": "Design secure systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "behavioural",
                "difficulty": "realistic",
                "duration_minutes": 15,
                "planned_question_count": max(3, question_count),
                "role_family": "solution_architecture",
                "role_level": "senior",
                "locale": "en-GB",
                "focus_areas": [],
                "allowed_answer_modes": ["text", "audio"],
                "evidence_selection": {
                    "application_cv": "approved_only",
                    "master_cv": "include",
                    "question_bank": "reviewed_final_only",
                    "selected_question_bank_record_ids": [],
                    "company_research": "include_if_fresh",
                    "draft_evidence_consent": False,
                },
                "retention": {
                    "audio": "delete_after_processing",
                    "transcript": "retain",
                },
            },
        },
    )
    questions = [
        SessionQuestion(
            id=f"question-{state}-{version}-{question_count}-{number}",
            session_id=session.id,
            question_num=number,
            text=f"Question {number}?",
            category="behavioural",
            difficulty="realistic",
            order_in_session=number,
            question_state="pending",
            question_kind="planned",
            follow_up_depth=0,
        )
        for number in range(1, question_count + 1)
    ]
    db.add_all([session, *questions])
    await db.commit()
    return session, questions


async def seed_command_database(
    factory: async_sessionmaker[AsyncSession], *, session_id: str
) -> None:
    async with factory() as db:
        db.add(
            InterviewSession(
                id=session_id,
                company_name="Example",
                role_title="Architect",
                experience_version="conversational_v1",
                status="setup",
                conversation_state="ready",
                state_version=0,
                retention_policy_json={
                    "audio": "delete_after_processing",
                    "transcript": "retain",
                },
                session_plan_json={
                    "retention": {
                        "audio": "delete_after_processing",
                        "transcript": "retain",
                    }
                },
            )
        )
        await db.commit()


async def seed_review_command_context(
    db: AsyncSession, *, target_state: str, version: int
) -> tuple[InterviewSession, SessionQuestion, SessionRecording]:
    session, questions = await seed_session(
        db, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db.commit()
    service = ConversationCommandService(db)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            command_id=f"seed-begin-{target_state}",
            payload={
                "recording_type": "text",
                "client_attempt_id": f"seed-attempt-{target_state}",
            },
        ),
    )
    await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "finish_answer",
            version=begun.state_version,
            command_id=f"seed-finish-{target_state}",
            payload={
                "attempt_id": begun.active_attempt_id,
                "transcript": "A bounded seed answer.",
            },
        ),
    )
    await db.refresh(session)
    session.conversation_state = target_state
    session.state_version = version
    if target_state == "recoverable_error":
        session.recoverable_error_scope = "attempt_processing"
        session.recoverable_error_code = "coach_evaluation_unavailable"
        session.recoverable_error_context_json = {"retryable": True}
    await db.commit()
    attempt = await db.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    return session, questions[0], attempt


@pytest.mark.asyncio
async def test_start_receipt_state_and_events_are_one_transaction(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(db_session)
    request = command("start", version=0)

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert (result.state, result.state_version) == ("asking", 1)
    assert result.active_question_id == questions[0].id
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session.id)
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [event.event_type for event in events] == [
        "session_started",
        "question_presented",
    ]
    receipt = await db_session.scalar(
        select(ConversationCommandResultRecord).where(
            ConversationCommandResultRecord.session_id == session.id,
            ConversationCommandResultRecord.command_id == request.command_id,
        )
    )
    assert receipt is not None
    assert receipt.result_json == result.model_dump(mode="json")


@pytest.mark.asyncio
async def test_duplicate_receipt_precedes_stale_version_and_replays_after_restart(
    db_session: AsyncSession,
) -> None:
    session, _ = await seed_session(db_session)
    request = command("start", version=0, command_id="replay-start")
    first = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert replay == first
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session.id
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_concurrent_different_commands_have_one_winner_and_fresh_conflict(
    command_database: async_sessionmaker[AsyncSession],
) -> None:
    session_id = "concurrent-different"
    await seed_command_database(command_database, session_id=session_id)
    requests = (
        command(
            "update_retention",
            version=0,
            command_id="retain-a",
            payload={"audio": "retain_until_deleted"},
        ),
        command(
            "update_retention",
            version=0,
            command_id="retain-b",
            payload={"audio": "delete_after_processing"},
        ),
    )

    async def execute(request: ConversationCommandRequest):
        async with command_database() as db:
            return await ConversationCommandService(db).execute(
                user_id="local", session_id=session_id, request=request
            )

    outcomes = await asyncio.gather(
        *(execute(request) for request in requests), return_exceptions=True
    )

    successes = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(successes) == len(failures) == 1
    assert isinstance(failures[0], ConversationCommandError)
    assert failures[0].code == "coach_conversation_version_conflict"
    assert failures[0].current_state_version == 1
    assert failures[0].current_state == "ready"
    async with command_database() as db:
        assert (
            await db.scalar(select(func.count(ConversationCommandResultRecord.id))) == 1
        )
        persisted = await db.get(InterviewSession, session_id)
        assert persisted is not None and persisted.state_version == 1


@pytest.mark.asyncio
async def test_concurrent_identical_commands_durably_replay_one_receipt(
    command_database: async_sessionmaker[AsyncSession],
) -> None:
    session_id = "concurrent-identical"
    await seed_command_database(command_database, session_id=session_id)
    request = command(
        "update_retention",
        version=0,
        command_id="retain-once",
        payload={"audio": "retain_until_deleted"},
    )

    async def execute():
        async with command_database() as db:
            return await ConversationCommandService(db).execute(
                user_id="local", session_id=session_id, request=request
            )

    first, second = await asyncio.gather(execute(), execute())

    assert first == second
    async with command_database() as db:
        assert (
            await db.scalar(select(func.count(ConversationCommandResultRecord.id))) == 1
        )
        persisted = await db.get(InterviewSession, session_id)
        assert persisted is not None
        assert (persisted.state_version, persisted.retention_version) == (1, 1)


@pytest.mark.asyncio
async def test_stale_command_does_not_mutate(db_session: AsyncSession) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=4
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command(
                "begin_answer",
                version=0,
                payload={"recording_type": "text", "client_attempt_id": "attempt-a"},
            ),
        )

    assert raised.value.code == "coach_conversation_version_conflict"
    assert await db_session.scalar(select(func.count(SessionRecording.id))) == 0


@pytest.mark.asyncio
async def test_deterministic_stub_never_emits_scores(db_session: AsyncSession) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            payload={"recording_type": "text", "client_attempt_id": "typed-1"},
        ),
    )

    finished = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "finish_answer",
            version=begun.state_version,
            payload={"attempt_id": begun.active_attempt_id, "transcript": "My answer."},
        ),
    )

    assert finished.state == "awaiting_next_action"
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    evaluation = await db_session.get(
        InterviewAttemptEvaluation, attempt.current_evaluation_version_id
    )
    assert evaluation is not None
    assert evaluation.state == "unavailable"
    assert evaluation.answer_level is None
    assert evaluation.version_number == 1
    assert evaluation.rubric_json == {
        "answer_level": "not_assessed",
        "contract_version": "coach_conversational_rubric_v1",
    }
    transcript = await db_session.get(
        InterviewTranscriptVersion, evaluation.transcript_version_id
    )
    assert transcript is not None
    assert (
        transcript.version_number,
        transcript.source,
        transcript.created_by,
        transcript.processing_generation,
    ) == (1, "candidate_text", "candidate", 1)
    stages = (
        await db_session.scalars(
            select(InterviewAttemptStage)
            .where(InterviewAttemptStage.recording_id == attempt.id)
            .order_by(InterviewAttemptStage.id)
        )
    ).all()
    assert {stage.stage_name: stage.stage_state for stage in stages} == {
        "audio_persist": "not_applicable",
        "transcription": "not_applicable",
        "speech_analysis": "not_applicable",
        "content_evaluation": "unavailable",
        "evidence_grounding": "not_applicable",
        "follow_up_decision": "not_applicable",
        "coaching_enrichment": "not_applicable",
    }
    assert "score" not in json.dumps(evaluation.rubric_json or {})


@pytest.mark.asyncio
async def test_request_hint_transfers_exact_order_to_new_attempt(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)

    first = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "request_hint", version=0, payload={"hint_type": "star_structure"}
        ),
    )
    second = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "request_hint",
            version=first.state_version,
            payload={"hint_type": "clarify_question"},
        ),
    )
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=second.state_version,
            payload={"recording_type": "text", "client_attempt_id": "hinted"},
        ),
    )

    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(questions[0])
    assert attempt is not None and attempt.hint_count == 2
    assert questions[0].pending_hint_count == 0
    assert questions[0].pending_hint_types_json is None
    capture_event = await db_session.scalar(
        select(InterviewSessionEvent).where(
            InterviewSessionEvent.recording_id == attempt.id,
            InterviewSessionEvent.event_type == "answer_capture_started",
        )
    )
    assert capture_event is not None
    assert capture_event.payload_json == {
        "hint_types": ["star_structure", "clarify_question"]
    }
    hint_events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.command_id.in_(
                    ["cmd-request_hint-0", "cmd-request_hint-1"]
                ),
            )
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [
        (
            event.event_type,
            event.actor_type,
            event.command_id,
            event.recording_id,
            event.payload_json,
        )
        for event in hint_events
    ] == [
        (
            "hint_requested",
            "candidate",
            "cmd-request_hint-0",
            None,
            {"hint_type": "star_structure"},
        ),
        (
            "hint_presented",
            "system",
            "cmd-request_hint-0",
            None,
            {"hint_type": "star_structure"},
        ),
        (
            "hint_requested",
            "candidate",
            "cmd-request_hint-1",
            None,
            {"hint_type": "clarify_question"},
        ),
        (
            "hint_presented",
            "system",
            "cmd-request_hint-1",
            None,
            {"hint_type": "clarify_question"},
        ),
    ]
    assert [event.sequence_number for event in hint_events] == list(
        range(hint_events[0].sequence_number, hint_events[0].sequence_number + 4)
    )


@pytest.mark.asyncio
async def test_retention_changes_future_attempts_only(db_session: AsyncSession) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    first = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            payload={"recording_type": "audio", "client_attempt_id": "audio-old"},
        ),
    )
    cancelled = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "cancel_attempt",
            version=first.state_version,
            payload={"attempt_id": first.active_attempt_id},
        ),
    )
    retained = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "update_retention",
            version=cancelled.state_version,
            payload={"audio": "retain_until_deleted"},
        ),
    )
    second = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=retained.state_version,
            payload={"recording_type": "audio", "client_attempt_id": "audio-new"},
        ),
    )

    old_attempt = await db_session.get(SessionRecording, first.active_attempt_id)
    new_attempt = await db_session.get(SessionRecording, second.active_attempt_id)
    await db_session.refresh(session)
    assert old_attempt is not None and new_attempt is not None
    assert old_attempt.attempt_state == "cancelled"
    assert old_attempt.audio_retention_policy == "delete_after_processing"
    assert new_attempt.audio_retention_policy == "retain_until_deleted"
    assert (session.retention_version, session.session_plan_amendment_version) == (1, 1)
    assert session.session_plan_json["retention"] == {
        "audio": "retain_until_deleted",
        "transcript": "retain",
    }
    assert session.state_version == 4
    assert session.activity_version == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "status", "scope"),
    [
        ("ready", "setup", None),
        ("asking", "active", None),
        ("listening", "active", None),
        ("awaiting_next_action", "active", None),
        ("coaching", "active", None),
        ("paused", "active", None),
        ("recoverable_error", "setup", "setup"),
        ("recoverable_error", "active", "attempt_processing"),
    ],
)
async def test_update_retention_binds_every_legal_v6_projection(
    db_session: AsyncSession, state: str, status: str, scope: str | None
) -> None:
    session, _ = await seed_session(db_session, state=state, status=status, version=6)
    session.recoverable_error_scope = scope
    if state == "paused":
        session.resume_state = "asking"
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "update_retention",
            version=6,
            payload={"audio": "retain_until_deleted"},
        ),
    )

    await db_session.refresh(session)
    assert (result.state, result.state_version) == (state, 7)
    assert session.recoverable_error_scope == scope
    assert (
        session.retention_version,
        session.session_plan_amendment_version,
        session.activity_version,
    ) == (1, 1, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["setup", "initial_report"])
async def test_pause_rejects_nonresumable_recoverable_error_scopes(
    db_session: AsyncSession, scope: str
) -> None:
    session, _ = await seed_session(
        db_session, state="recoverable_error", status="active", version=4
    )
    session.recoverable_error_scope = scope
    await db_session.commit()
    request = command("pause", version=4)

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=session.id, request=request
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    await db_session.refresh(session)
    assert (session.conversation_state, session.state_version) == (
        "recoverable_error",
        4,
    )


@pytest.mark.asyncio
async def test_pause_accepts_attempt_processing_recoverable_scope(
    db_session: AsyncSession,
) -> None:
    session, _ = await seed_session(
        db_session, state="recoverable_error", status="active", version=4
    )
    session.recoverable_error_scope = "attempt_processing"
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("pause", version=4),
    )

    assert (result.state, result.state_version) == ("paused", 5)
    await db_session.refresh(session)
    assert session.resume_state == "recoverable_error"


@pytest.mark.asyncio
async def test_pause_resume_preserves_draft_and_keep_speaking(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            payload={"recording_type": "text", "client_attempt_id": "draft"},
        ),
    )
    kept = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "keep_speaking",
            version=begun.state_version,
            payload={"attempt_id": begun.active_attempt_id},
        ),
    )
    paused = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command("pause", version=kept.state_version),
    )
    resumed = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command("resume", version=paused.state_version),
    )

    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(session)
    assert attempt is not None and attempt.attempt_state == "draft"
    assert resumed.state == "listening"
    assert session.resume_state is None and session.paused_at is None
    lifecycle_events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.command_id.in_(["cmd-pause-2", "cmd-resume-3"]),
            )
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [
        (
            event.event_type,
            event.actor_type,
            event.command_id,
            event.recording_id,
            event.state_before,
            event.state_after,
        )
        for event in lifecycle_events
    ] == [
        (
            "session_paused",
            "candidate",
            "cmd-pause-2",
            attempt.id,
            "listening",
            "paused",
        ),
        (
            "answer_capture_paused",
            "system",
            "cmd-pause-2",
            attempt.id,
            "listening",
            "paused",
        ),
        (
            "session_resumed",
            "candidate",
            "cmd-resume-3",
            attempt.id,
            "paused",
            "listening",
        ),
        (
            "answer_capture_resumed",
            "system",
            "cmd-resume-3",
            attempt.id,
            "paused",
            "listening",
        ),
    ]
    assert [event.sequence_number for event in lifecycle_events] == list(
        range(
            lifecycle_events[0].sequence_number,
            lifecycle_events[0].sequence_number + 4,
        )
    )
    assert all(event.payload_json is None for event in lifecycle_events)

    replayed_pause = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("pause", version=kept.state_version),
    )
    replayed_resume = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("resume", version=paused.state_version),
    )
    assert (replayed_pause, replayed_resume) == (paused, resumed)
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.command_id.in_(["cmd-pause-2", "cmd-resume-3"]),
            )
        )
        == 4
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_state", ["asking", "awaiting_next_action", "coaching"])
async def test_pause_persists_exact_effect_and_replays_for_each_legal_review_state(
    db_session: AsyncSession, prior_state: str
) -> None:
    if prior_state == "asking":
        session, questions = await seed_session(
            db_session, state="asking", status="active", version=7
        )
        session.active_question_id = questions[0].id
        questions[0].question_state = "asked"
        await db_session.commit()
        question = questions[0]
        active_attempt_id = None
    else:
        session, question, attempt = await seed_review_command_context(
            db_session, target_state=prior_state, version=7
        )
        active_attempt_id = attempt.id
    request = command("pause", version=7, command_id=f"pause-{prior_state}")
    activity_version = session.activity_version
    retention_version = session.retention_version

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert replay == result
    assert (result.state, result.state_version) == ("paused", 8)
    await db_session.refresh(session)
    assert (session.status, session.resume_state) == ("active", prior_state)
    assert session.paused_at is not None
    assert session.active_question_id == question.id
    assert session.active_recording_id == active_attempt_id
    assert (session.activity_version, session.retention_version) == (
        activity_version,
        retention_version,
    )
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent).where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.command_id == request.command_id,
            )
        )
    ).all()
    assert len(events) == 1
    assert (
        events[0].event_type,
        events[0].actor_type,
        events[0].state_before,
        events[0].state_after,
        events[0].state_version,
        events[0].command_id,
    ) == (
        "session_paused",
        "candidate",
        prior_state,
        "paused",
        8,
        request.command_id,
    )
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session.id,
                ConversationCommandResultRecord.command_id == request.command_id,
            )
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resume_state",
    ["asking", "awaiting_next_action", "coaching", "recoverable_error"],
)
async def test_resume_restores_exact_state_and_replays_for_each_legal_target(
    db_session: AsyncSession, resume_state: str
) -> None:
    if resume_state == "asking":
        session, questions = await seed_session(
            db_session, state="paused", status="active", version=10
        )
        session.active_question_id = questions[0].id
        questions[0].question_state = "asked"
        question = questions[0]
        active_attempt_id = None
    else:
        session, question, attempt = await seed_review_command_context(
            db_session, target_state=resume_state, version=10
        )
        session.conversation_state = "paused"
        active_attempt_id = attempt.id
    session.resume_state = resume_state
    session.paused_at = datetime.utcnow()
    await db_session.commit()
    request = command("resume", version=10, command_id=f"resume-{resume_state}")
    activity_version = session.activity_version

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert replay == result
    assert (result.state, result.state_version) == (resume_state, 11)
    await db_session.refresh(session)
    assert session.status == "active"
    assert session.resume_state is None and session.paused_at is None
    assert session.active_question_id == question.id
    assert session.active_recording_id == active_attempt_id
    assert session.activity_version == activity_version
    if resume_state == "recoverable_error":
        assert session.recoverable_error_scope == "attempt_processing"
        assert session.recoverable_error_code == "coach_evaluation_unavailable"
        assert session.recoverable_error_context_json == {"retryable": True}
    event = await db_session.scalar(
        select(InterviewSessionEvent).where(
            InterviewSessionEvent.session_id == session.id,
            InterviewSessionEvent.command_id == request.command_id,
        )
    )
    assert event is not None
    assert (
        event.event_type,
        event.actor_type,
        event.state_before,
        event.state_after,
        event.state_version,
        event.command_id,
    ) == (
        "session_resumed",
        "candidate",
        "paused",
        resume_state,
        11,
        request.command_id,
    )
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session.id,
                ConversationCommandResultRecord.command_id == request.command_id,
            )
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_state", ["coaching", "recoverable_error"])
async def test_retry_answer_from_each_remaining_legal_state_has_exact_effect(
    db_session: AsyncSession, prior_state: str
) -> None:
    session, question, attempt = await seed_review_command_context(
        db_session, target_state=prior_state, version=12
    )
    request = command(
        "retry_answer",
        version=12,
        command_id=f"retry-{prior_state}",
        payload={"question_id": question.id},
    )
    attempt_version = attempt.attempt_version
    attempts_created_count = question.attempts_created_count
    activity_version = session.activity_version

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert replay == result
    assert (result.state, result.state_version, result.active_attempt_id) == (
        "asking",
        13,
        None,
    )
    await db_session.refresh(session)
    await db_session.refresh(question)
    await db_session.refresh(attempt)
    assert session.status == "active"
    assert session.active_question_id == question.id
    assert session.active_recording_id is None
    assert (
        session.recoverable_error_scope,
        session.recoverable_error_code,
        session.recoverable_error_context_json,
    ) == (None, None, None)
    assert session.activity_version == activity_version
    assert question.question_state == "asked"
    assert question.attempts_created_count == attempts_created_count
    assert (attempt.attempt_state, attempt.attempt_version) == (
        "unavailable",
        attempt_version,
    )
    event = await db_session.scalar(
        select(InterviewSessionEvent).where(
            InterviewSessionEvent.session_id == session.id,
            InterviewSessionEvent.command_id == request.command_id,
        )
    )
    assert event is not None
    assert (
        event.event_type,
        event.actor_type,
        event.state_before,
        event.state_after,
        event.state_version,
        event.recording_id,
        event.command_id,
    ) == (
        "attempt_retried",
        "candidate",
        prior_state,
        "asking",
        13,
        attempt.id,
        request.command_id,
    )
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session.id,
                ConversationCommandResultRecord.command_id == request.command_id,
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_request_hint_while_listening_updates_only_active_attempt_and_replays(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            command_id="seed-listening-hint",
            payload={
                "recording_type": "text",
                "client_attempt_id": "listening-hint-attempt",
            },
        ),
    )
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    question_pending_count = questions[0].pending_hint_count
    request = command(
        "request_hint",
        version=begun.state_version,
        command_id="hint-while-listening",
        payload={"hint_type": "clarify_question"},
    )

    result = await service.execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert replay == result
    assert (result.state, result.state_version, result.active_attempt_id) == (
        "listening",
        2,
        attempt.id,
    )
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    await db_session.refresh(questions[0])
    assert session.status == "active"
    assert attempt.hint_count == 1
    assert questions[0].pending_hint_count == question_pending_count
    assert questions[0].pending_hint_types_json is None
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.command_id == request.command_id,
            )
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [
        (
            event.event_type,
            event.actor_type,
            event.state_before,
            event.state_after,
            event.state_version,
            event.recording_id,
            event.command_id,
            event.payload_json,
        )
        for event in events
    ] == [
        (
            "hint_requested",
            "candidate",
            "listening",
            "listening",
            2,
            attempt.id,
            request.command_id,
            {"hint_type": "clarify_question"},
        ),
        (
            "hint_presented",
            "system",
            "listening",
            "listening",
            2,
            attempt.id,
            request.command_id,
            {"hint_type": "clarify_question"},
        ),
    ]
    assert events[1].sequence_number == events[0].sequence_number + 1
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session.id,
                ConversationCommandResultRecord.command_id == request.command_id,
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_retry_preserves_terminal_attempt_and_budget(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            payload={"recording_type": "text", "client_attempt_id": "first"},
        ),
    )
    finished = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "finish_answer",
            version=begun.state_version,
            payload={"attempt_id": begun.active_attempt_id, "transcript": "Answer"},
        ),
    )
    retried = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "retry_answer",
            version=finished.state_version,
            payload={"question_id": questions[0].id},
        ),
    )

    prior = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(questions[0])
    assert prior is not None and prior.attempt_state == "unavailable"
    assert retried.state == "asking" and retried.active_attempt_id is None
    assert questions[0].attempts_created_count == 1


@pytest.mark.asyncio
async def test_skip_marks_question_and_presents_next_once(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=3
    )
    session.active_question_id = questions[0].id
    session.active_root_question_id = questions[0].id
    questions[0].question_state = "asked"
    questions[0].asked_sequence = 1
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("skip_question", version=3),
    )

    await db_session.refresh(questions[0])
    await db_session.refresh(questions[1])
    assert questions[0].question_state == "skipped"
    assert (questions[1].question_state, questions[1].asked_sequence) == ("asked", 2)
    assert result.state == "asking" and result.active_question_id == questions[1].id
    await db_session.refresh(session)
    assert session.activity_version == 1


@pytest.mark.asyncio
async def test_retry_setup_claim_dispatches_only_after_commit(
    db_session: AsyncSession,
) -> None:
    session, _ = await seed_session(
        db_session, state="recoverable_error", status="setup", version=2
    )
    session.recoverable_error_scope = "setup"
    session.recoverable_error_code = "coach_setup_claim_expired"
    session.setup_attempt_count = 1
    await db_session.commit()
    observed: list[tuple[str, str | None]] = []

    async def after_commit(job_id: str) -> None:
        job = await db_session.get(AsyncJob, job_id)
        observed.append((job_id, job.status if job is not None else None))

    result = await ConversationCommandService(
        db_session, after_commit=after_commit
    ).execute(
        user_id="local",
        session_id=session.id,
        request=command("retry_setup", version=2),
    )

    assert result.state == "planning"
    assert result.result == "accepted_processing"
    assert observed == [(result.async_job_id, "pending")]
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session.id)
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [
        (event.event_type, event.actor_type, event.command_id) for event in events
    ] == [
        ("session_plan_retry_requested", "candidate", "cmd-retry_setup-2"),
        ("session_plan_started", "system", None),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [RuntimeError, ValueError])
async def test_setup_dispatch_failure_preserves_durable_accepted_result(
    db_session: AsyncSession, failure_type: type[Exception]
) -> None:
    session, _ = await seed_session(
        db_session, state="recoverable_error", status="setup", version=2
    )
    session.recoverable_error_scope = "setup"
    session.recoverable_error_code = "coach_setup_claim_expired"
    session.setup_attempt_count = 1
    await db_session.commit()
    dispatched = 0

    async def fail_dispatch(_job_id: str) -> None:
        nonlocal dispatched
        dispatched += 1
        raise failure_type("secret dispatcher detail")

    request = command("retry_setup", version=2, command_id="durable-setup")
    result = await ConversationCommandService(
        db_session, after_commit=fail_dispatch
    ).execute(user_id="local", session_id=session.id, request=request)
    replay = await ConversationCommandService(
        db_session, after_commit=fail_dispatch
    ).execute(user_id="local", session_id=session.id, request=request)

    assert result == replay
    assert result.result == "accepted_processing"
    assert dispatched == 1
    job = await db_session.get(AsyncJob, result.async_job_id)
    assert job is not None and job.status == "pending"
    receipt = await db_session.scalar(
        select(ConversationCommandResultRecord).where(
            ConversationCommandResultRecord.session_id == session.id,
            ConversationCommandResultRecord.command_id == request.command_id,
        )
    )
    assert receipt is not None and receipt.result_state == "accepted_processing"


@pytest.mark.asyncio
async def test_later_command_fails_without_receipt_or_partial_mutation(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="awaiting_next_action", status="active", version=5
    )
    session.active_question_id = questions[0].id
    await db_session.commit()
    request = command(
        "request_coaching", version=5, payload={"attempt_id": "foreign-attempt"}
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=session.id, request=request
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.command_id == request.command_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_event_failure_rolls_back_state_and_receipt(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = await seed_session(db_session)
    session_id = session.id
    service = ConversationCommandService(db_session)

    async def fail_events(**_: object) -> None:
        raise ValueError("event payload must be content-free and bounded")

    monkeypatch.setattr(service.repository, "append_session_events", fail_events)
    request = command("start", version=0)
    with pytest.raises(ConversationCommandError):
        await service.execute(user_id="local", session_id=session.id, request=request)

    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None and persisted.conversation_state == "ready"
    assert await db_session.scalar(select(func.count(InterviewSessionEvent.id))) == 0
    assert (
        await db_session.scalar(select(func.count(ConversationCommandResultRecord.id)))
        == 0
    )


@pytest.mark.asyncio
async def test_shared_state_change_event_failure_rolls_back_pause_and_receipt(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=3
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    session_id = session.id
    service = ConversationCommandService(db_session)

    async def fail_events(**_: object) -> None:
        raise ValueError("event payload must be content-free and bounded")

    monkeypatch.setattr(service.repository, "append_session_events", fail_events)
    request = command("pause", version=3, command_id="rollback-pause")
    with pytest.raises(ConversationCommandError):
        await service.execute(user_id="local", session_id=session_id, request=request)

    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (persisted.conversation_state, persisted.state_version) == ("asking", 3)
    assert persisted.resume_state is None and persisted.paused_at is None
    assert await db_session.scalar(select(func.count(InterviewSessionEvent.id))) == 0
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.command_id == request.command_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_command_result_uses_contextual_allowed_command_projection(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=3
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("pause", version=3, command_id="contextual-pause"),
    )

    assert result.allowed_commands == ["resume", "update_retention", "end_session"]


@pytest.mark.asyncio
async def test_paused_result_and_live_view_advertise_any_eligible_audio_target(
    db_session: AsyncSession,
) -> None:
    from app.services.coach_live_view import CoachLiveViewService

    session, questions = await seed_session(
        db_session, state="asking", status="active", version=3
    )
    session.active_question_id = questions[0].id
    session.active_root_question_id = questions[0].id
    questions[0].question_state = "asked"
    historical = SessionQuestion(
        session_id=session.id,
        question_num=3,
        text="Historical question",
        category="technical",
        difficulty="realistic",
        order_in_session=3,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    db_session.add(historical)
    await db_session.flush()
    db_session.add(
        SessionRecording(
            session_id=session.id,
            question_id=historical.id,
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="completed",
            evaluation_state="completed",
            processing_generation=1,
            processing_retry_count=0,
            processing_retry_limit=2,
            audio_retention_policy="retain_until_deleted",
            audio_retention_state="retained",
        )
    )
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("pause", version=3, command_id="pause-with-historical-audio"),
    )
    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert "delete_audio" in result.allowed_commands
    assert result.allowed_commands == view.allowed_commands


@pytest.mark.asyncio
async def test_command_service_fails_closed_before_scope_incompatible_dispatch(
    db_session: AsyncSession,
) -> None:
    session, _ = await seed_session(
        db_session, state="recoverable_error", status="active", version=3
    )
    session.recoverable_error_scope = "initial_report"
    session.recoverable_error_code = "coach_report_conversational_snapshot_stale"
    await db_session.commit()
    request = command("pause", version=3, command_id="scope-mismatch")

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=session.id, request=request
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.command_id == request.command_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("command_type", ["pause", "resume", "request_hint"])
async def test_listening_lifecycle_event_failure_rolls_back_all_command_effects(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    command_type: str,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            command_id=f"seed-{command_type}-rollback",
            payload={
                "recording_type": "text",
                "client_attempt_id": f"attempt-{command_type}-rollback",
            },
        ),
    )
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    version = begun.state_version
    expected_state = "listening"
    expected_resume_state = None
    if command_type == "resume":
        session.conversation_state = "paused"
        session.resume_state = "listening"
        session.paused_at = datetime.utcnow()
        session.state_version = 5
        version = 5
        expected_state = "paused"
        expected_resume_state = "listening"
        await db_session.commit()
    baseline_events = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id)).where(
            InterviewSessionEvent.session_id == session.id
        )
    )

    async def fail_events(**_: object) -> None:
        raise ValueError("event payload must be content-free and bounded")

    monkeypatch.setattr(service.repository, "append_session_events", fail_events)
    request = command(
        command_type,
        version=version,
        command_id=f"rollback-{command_type}-events",
        payload=(
            {"hint_type": "clarify_question"}
            if command_type == "request_hint"
            else None
        ),
    )
    with pytest.raises(ConversationCommandError):
        await service.execute(user_id="local", session_id=session.id, request=request)

    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (session.conversation_state, session.state_version) == (
        expected_state,
        version,
    )
    assert session.resume_state == expected_resume_state
    assert (attempt.attempt_state, attempt.hint_count) == ("draft", 0)
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session.id
            )
        )
        == baseline_events
    )
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.command_id == request.command_id
            )
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.command_id == request.command_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_receipt_completion_failure_rolls_back_whole_command(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = await seed_session(db_session)
    session_id = session.id
    service = ConversationCommandService(db_session)

    async def fail_completion(**_: object) -> bool:
        return False

    monkeypatch.setattr(
        service.repository, "complete_conversation_command", fail_completion
    )
    with pytest.raises(ConversationCommandError) as raised:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command("start", version=0),
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (persisted.conversation_state, persisted.state_version) == ("ready", 0)
    assert await db_session.scalar(select(func.count(InterviewSessionEvent.id))) == 0
    assert (
        await db_session.scalar(select(func.count(ConversationCommandResultRecord.id)))
        == 0
    )


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_misreported_as_idempotency_conflict(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = await seed_session(db_session)
    session_id = session.id
    service = ConversationCommandService(db_session)
    database_error = IntegrityError("insert event", {}, RuntimeError("constraint"))

    async def fail_events(**_: object) -> None:
        raise database_error

    monkeypatch.setattr(service.repository, "append_session_events", fail_events)
    with pytest.raises(IntegrityError) as raised:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command("start", version=0),
        )

    assert raised.value is database_error
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (persisted.conversation_state, persisted.state_version) == ("ready", 0)
    assert (
        await db_session.scalar(select(func.count(ConversationCommandResultRecord.id)))
        == 0
    )


@pytest.mark.asyncio
async def test_duplicate_client_attempt_precedes_listening_state_validation(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    payload = {"recording_type": "text", "client_attempt_id": "network-retry"}
    first = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command("begin_answer", version=0, payload=payload),
    )

    replay = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=first.state_version,
            payload=payload,
            command_id="new-command-same-client-attempt",
        ),
    )

    assert replay.result == "duplicate"
    assert replay.active_attempt_id == first.active_attempt_id
    assert await db_session.scalar(select(func.count(SessionRecording.id))) == 1


@pytest.mark.asyncio
async def test_same_command_id_different_semantics_conflicts_before_version(
    db_session: AsyncSession,
) -> None:
    session, _ = await seed_session(db_session)
    first = command("start", version=0, command_id="semantic-id")
    await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=first
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=first.model_copy(update={"expected_state_version": 99}),
        )

    assert raised.value.code == "coach_command_idempotency_conflict"


@pytest.mark.asyncio
async def test_finish_rejects_cross_session_attempt_without_receipt(
    db_session: AsyncSession,
) -> None:
    first, first_questions = await seed_session(
        db_session, state="listening", status="active", version=1
    )
    second, second_questions = await seed_session(
        db_session, state="listening", status="active", version=1, question_count=3
    )
    foreign_attempt = SessionRecording(
        id="foreign-attempt",
        session_id=second.id,
        question_id=second_questions[0].id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="draft",
        processing_retry_limit=2,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
        client_attempt_id="foreign-client",
    )
    first.active_question_id = first_questions[0].id
    first.active_recording_id = foreign_attempt.id
    first_questions[0].question_state = "asked"
    second.active_question_id = second_questions[0].id
    second.active_recording_id = foreign_attempt.id
    second_questions[0].question_state = "asked"
    db_session.add(foreign_attempt)
    await db_session.commit()
    first_id = first.id
    request = command(
        "finish_answer",
        version=1,
        payload={"attempt_id": foreign_attempt.id, "transcript": "Unsafe"},
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=first_id, request=request
        )

    assert raised.value.code == "coach_attempt_not_active"
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == first_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_rebuild_plan_reuses_fenced_setup_claim(db_session: AsyncSession) -> None:
    session, _ = await seed_session(
        db_session, state="ready", status="setup", version=7
    )
    session.setup_attempt_count = 1
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("rebuild_plan", version=7, payload={"refresh_sources": True}),
    )

    await db_session.refresh(session)
    assert result.state == "planning" and result.async_job_id == session.setup_job_id
    assert result.result == "accepted_processing"
    assert (session.setup_generation, session.setup_attempt_count) == (1, 2)
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session.id)
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()
    assert [
        (event.event_type, event.actor_type, event.command_id) for event in events
    ] == [
        ("session_plan_rebuild_requested", "candidate", "cmd-rebuild_plan-7"),
        ("session_plan_started", "system", None),
    ]


@pytest.mark.asyncio
async def test_retry_at_attempt_limit_is_no_mutation(db_session: AsyncSession) -> None:
    session, questions = await seed_session(
        db_session, state="awaiting_next_action", status="active", version=9
    )
    session.active_question_id = questions[0].id
    session.active_recording_id = "preserved-attempt"
    questions[0].question_state = "asked"
    questions[0].attempts_created_count = 5
    attempt = SessionRecording(
        id="preserved-attempt",
        session_id=session.id,
        question_id=questions[0].id,
        recording_type="text",
        attempt_number=5,
        attempt_kind="retry",
        attempt_state="unavailable",
        processing_retry_limit=2,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
        client_attempt_id="preserved-client",
    )
    db_session.add(attempt)
    await db_session.commit()
    session_id = session.id
    request = command(
        "retry_answer", version=9, payload={"question_id": questions[0].id}
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=session_id, request=request
        )

    assert raised.value.code == "coach_attempt_limit_exhausted"
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (persisted.conversation_state, persisted.state_version) == (
        "awaiting_next_action",
        9,
    )


@pytest.mark.asyncio
async def test_terminal_skip_fails_closed_without_partial_mutation(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session,
        state="asking",
        status="active",
        version=4,
        question_count=1,
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    questions[0].asked_sequence = 1
    await db_session.commit()
    session_id = session.id
    question_id = questions[0].id
    request = command("skip_question", version=4)

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local", session_id=session_id, request=request
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    persisted_session = await db_session.get(InterviewSession, session_id)
    persisted_question = await db_session.get(SessionQuestion, question_id)
    assert persisted_session is not None and persisted_question is not None
    assert (persisted_session.conversation_state, persisted_session.state_version) == (
        "asking",
        4,
    )
    assert persisted_question.question_state == "asked"
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session_id
            )
        )
        == 0
    )
