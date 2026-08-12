"""Command-level contracts for the conversational Coach foundation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
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
from app.config import settings
from app.models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewAttemptUpload,
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
from app.services.coach_media_storage import CoachMediaError
from app.services.coach_live_view import CoachLiveViewService
from app.services.coach_reconciliation import (
    reconcile_conversational_session,
    reconcile_stale_coach_state,
)
from app.services.coach_retention import (
    CancelledUploadCleanupClaim,
    CoachRetentionService,
    _process_audio_cleanup_claim,
    _safe_process_audio_cleanup_claim,
)


@pytest.fixture(autouse=True)
def disable_real_attempt_worker_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Command tests assert durable hand-off; focused tests own worker execution."""
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        lambda _claim: None,
    )
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_audio_cleanup",
        lambda _claim: None,
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


async def _seed_uploaded_cancellable_attempt(
    db: AsyncSession, media_root: Path
) -> tuple[InterviewSession, SessionRecording, ConversationCommandRequest, Path]:
    """Build a real uploaded attempt and its completed ownership receipt."""
    session, questions = await seed_session(
        db, state="asking", status="active", version=0, question_count=1
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db.commit()
    begun = await ConversationCommandService(db).execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            command_id="uploaded-cancel-begin",
            payload={
                "recording_type": "audio",
                "client_attempt_id": "uploaded-cancel-attempt",
            },
        ),
    )
    attempt = await db.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    body = b"uploaded cancellation audio"
    source = media_root / session.id / "uploaded-cancel.webm"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    attempt.attempt_state = "uploaded"
    attempt.attempt_version = 1
    attempt.audio_uri = str(source)
    attempt.audio_content_hash = digest
    attempt.audio_retention_state = "temporary"
    db.add(
        InterviewAttemptUpload(
            attempt_id=attempt.id,
            upload_id="uploaded-cancel-upload",
            request_hash="a" * 64,
            content_sha256=digest,
            byte_size=len(body),
            mime_type="audio/webm",
            storage_uri=str(source),
            result_state="completed",
            completed_at=datetime.utcnow(),
        )
    )
    await db.commit()
    return (
        session,
        attempt,
        command(
            "cancel_attempt",
            version=begun.state_version,
            command_id="uploaded-cancel-command",
            payload={"attempt_id": attempt.id},
        ),
        source,
    )


@pytest.fixture
def isolated_cancel_media_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cancelled-upload-media"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", root)
    return root


def _capture_cancelled_cleanup_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> list[CancelledUploadCleanupClaim]:
    claims: list[CancelledUploadCleanupClaim] = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_audio_cleanup",
        claims.append,
    )
    return claims


async def _run_cancelled_cleanup_worker(
    db: AsyncSession, claim: CancelledUploadCleanupClaim
) -> None:
    worker_sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    await _process_audio_cleanup_claim(claim, session_factory=worker_sessions)


async def _seed_terminal_cancelled_cleanup_failure(
    db: AsyncSession,
    media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    InterviewSession,
    SessionRecording,
    Path,
    CancelledUploadCleanupClaim,
    str,
]:
    """Create one terminal cancelled-upload failure using its real worker fences."""
    from app.services import coach_retention

    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db, media_root
    )

    def _media_boundary_failure(*_args, **_kwargs):
        raise CoachMediaError("coach_attempt_upload_conflict")

    monkeypatch.setattr(
        coach_retention,
        "open_verified_audio_deletion_lease",
        _media_boundary_failure,
    )
    claims = _capture_cancelled_cleanup_dispatch(monkeypatch)
    accepted = await ConversationCommandService(db).execute(
        user_id="local", session_id=session.id, request=request
    )
    assert accepted.result == "accepted_processing"
    assert len(claims) == 1
    await _run_cancelled_cleanup_worker(db, claims[0])
    await db.refresh(attempt)
    await db.refresh(session)
    job = await db.get(AsyncJob, accepted.async_job_id)
    assert job is not None
    assert (attempt.attempt_state, attempt.audio_retention_state) == (
        "cancelled",
        "delete_failed",
    )
    return session, attempt, source, claims[0], job.id


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
    attempt = await db.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    attempt.attempt_state = "unavailable"
    attempt.evaluation_state = "unavailable"
    attempt.async_job_id = None
    evaluation = await db.scalar(select(InterviewAttemptEvaluation).where(
        InterviewAttemptEvaluation.recording_id == attempt.id
    ))
    assert evaluation is not None
    evaluation.state = "unavailable"
    evaluation.async_job_id = None
    await db.refresh(session)
    session.conversation_state = target_state
    session.state_version = version
    if target_state == "recoverable_error":
        session.recoverable_error_scope = "attempt_processing"
        session.recoverable_error_code = "coach_evaluation_unavailable"
        session.recoverable_error_context_json = {"retryable": True}
    await db.commit()
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

    assert (finished.state, finished.result) == ("processing_answer", "accepted_processing")
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    evaluation = await db_session.scalar(select(InterviewAttemptEvaluation).where(
        InterviewAttemptEvaluation.recording_id == attempt.id,
        InterviewAttemptEvaluation.async_job_id == finished.async_job_id,
    ))
    assert evaluation is not None
    assert evaluation.state == "pending"
    assert evaluation.answer_level is None
    assert evaluation.version_number == 1
    assert evaluation.rubric_json is None
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
        "content_evaluation": "pending",
        "evidence_grounding": "pending",
        "follow_up_decision": "pending",
        "coaching_enrichment": "pending",
        "audio_cleanup": "pending",
    }
    assert "score" not in json.dumps(evaluation.rubric_json or {})


@pytest.mark.asyncio
async def test_finish_parent_deletion_race_stops_before_stage_persistence(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
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
            payload={
                "recording_type": "text",
                "client_attempt_id": "finish-parent-deletion-race",
            },
        ),
    )
    original_claim = service.repository.claim_attempt_processing

    async def claim_then_mark_deleting(**kwargs):
        claim = await original_claim(**kwargs)
        assert claim is not None
        parent = await service.db.get(InterviewSession, session.id)
        assert parent is not None
        parent.deletion_state = "deleting"
        await service.db.flush()
        return claim

    monkeypatch.setattr(
        service.repository, "claim_attempt_processing", claim_then_mark_deleting
    )
    stage_inserts: list[str] = []
    async_engine = db_session.bind
    assert async_engine is not None

    def capture_stage_insert(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        normalised = " ".join(statement.lower().split())
        if normalised.startswith("insert into interview_attempt_stages"):
            stage_inserts.append(normalised)

    event.listen(
        async_engine.sync_engine, "before_cursor_execute", capture_stage_insert
    )
    try:
        with pytest.raises(ConversationCommandError) as raised:
            await service.execute(
                user_id="local",
                session_id=session.id,
                request=command(
                    "finish_answer",
                    version=begun.state_version,
                    payload={
                        "attempt_id": begun.active_attempt_id,
                        "transcript": "A bounded answer.",
                    },
                ),
            )
    finally:
        event.remove(
            async_engine.sync_engine, "before_cursor_execute", capture_stage_insert
        )

    assert raised.value.code == "coach_attempt_stale_claim"
    assert stage_inserts == []


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
    assert old_attempt.audio_uri is None
    assert old_attempt.audio_retention_state == "pending"
    assert new_attempt.audio_retention_policy == "retain_until_deleted"
    assert (session.retention_version, session.session_plan_amendment_version) == (1, 1)
    assert session.session_plan_json["retention"] == {
        "audio": "retain_until_deleted",
        "transcript": "retain",
    }
    assert session.state_version == 4
    assert session.activity_version == 0


@pytest.mark.asyncio
async def test_uploaded_cancel_commits_durable_authority_before_post_commit_deletion(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving deletion before commit would make the independent receipt check fail."""
    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    real_delete = CoachRetentionService.delete_cancelled_upload_audio
    independent_session = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False
    )
    observed_committed_receipt = []
    cleanup_claims: list[CancelledUploadCleanupClaim] = []

    async def _delete_after_asserting_commit(service, claim):
        async with independent_session() as inspector:
            persisted_attempt = await inspector.get(SessionRecording, attempt.id)
            persisted_receipt = await inspector.scalar(
                select(InterviewAttemptUpload).where(
                    InterviewAttemptUpload.attempt_id == attempt.id,
                    InterviewAttemptUpload.upload_id == "uploaded-cancel-upload",
                )
            )
            persisted_command = await inspector.scalar(
                select(ConversationCommandResultRecord).where(
                    ConversationCommandResultRecord.session_id == session.id,
                    ConversationCommandResultRecord.command_id == request.command_id,
                )
            )
            persisted_job = await inspector.get(AsyncJob, claim.job_id)
        observed_committed_receipt.append(
            {
                "outside_command_transaction": not db_session.in_transaction(),
                "attempt": (
                    persisted_attempt.attempt_state,
                    persisted_attempt.audio_retention_state,
                    persisted_attempt.async_job_id,
                )
                if persisted_attempt
                else None,
                "receipt_result": persisted_receipt.result_state
                if persisted_receipt
                else None,
                "command_result": persisted_command.result_json
                if persisted_command
                else None,
                "command_result_state": persisted_command.result_state
                if persisted_command
                else None,
                "job_claim": persisted_job.result_json if persisted_job else None,
            }
        )
        return await real_delete(service, claim)

    monkeypatch.setattr(
        CoachRetentionService,
        "delete_cancelled_upload_audio",
        _delete_after_asserting_commit,
    )
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_audio_cleanup",
        cleanup_claims.append,
    )
    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert result.result == "accepted_processing"
    assert result.async_job_id is not None
    assert len(cleanup_claims) == 1
    await _process_audio_cleanup_claim(
        cleanup_claims[0], session_factory=independent_session
    )
    assert len(observed_committed_receipt) == 1
    committed = observed_committed_receipt[0]
    assert committed["outside_command_transaction"] is True
    assert committed["attempt"] == (
        "cancelled",
        "delete_pending",
        result.async_job_id,
    )
    assert committed["receipt_result"] == "completed"
    assert committed["command_result"] == result.model_dump(mode="json")
    assert committed["command_result_state"] == "accepted_processing"
    assert isinstance(committed["job_claim"], str)
    assert set(json.loads(committed["job_claim"])) == {
        "claim_token",
        "deadline_at",
        "fence_hash",
    }
    assert str(source) not in committed["job_claim"]
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    receipt = await db_session.scalar(
        select(InterviewAttemptUpload).where(
            InterviewAttemptUpload.attempt_id == attempt.id,
            InterviewAttemptUpload.upload_id == "uploaded-cancel-upload",
        )
    )
    command_receipt = await db_session.scalar(
        select(ConversationCommandResultRecord).where(
            ConversationCommandResultRecord.session_id == session.id,
            ConversationCommandResultRecord.command_id == request.command_id,
        )
    )
    job = await db_session.get(AsyncJob, result.async_job_id)
    assert (session.conversation_state, session.active_recording_id) == (
        "asking",
        None,
    )
    assert (session.state_version, session.retention_version) == (3, 1)
    assert (
        attempt.attempt_state,
        attempt.audio_retention_state,
        attempt.audio_uri,
        attempt.async_job_id,
    ) == ("cancelled", "deleted", None, None)
    assert receipt is not None and receipt.result_state == "deleted"
    assert command_receipt is not None
    assert command_receipt.result_state == "accepted_processing"
    assert command_receipt.result_json == result.model_dump(mode="json")
    assert job is not None
    assert (job.type, job.status, job.result_json, job.error) == (
        "coach_cancelled_upload_cleanup",
        "done",
        '{"result":"deleted"}',
        None,
    )
    events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent)
                .where(
                    InterviewSessionEvent.session_id == session.id,
                    InterviewSessionEvent.recording_id == attempt.id,
                    InterviewSessionEvent.event_type.in_(
                        (
                            "answer_capture_cancelled",
                            "audio_cleanup_claimed",
                            "audio_deleted",
                        )
                    ),
                )
                .order_by(InterviewSessionEvent.sequence_number)
            )
        ).all()
    )
    assert [(event.event_type, event.payload_json) for event in events] == [
        ("answer_capture_cancelled", None),
        ("audio_cleanup_claimed", {"reason": "cancelled_attempt"}),
        ("audio_deleted", {"reason": "cancelled_attempt"}),
    ]
    assert not source.exists()


@pytest.mark.asyncio
async def test_uploaded_cancel_returns_committed_receipt_before_blocked_cleanup(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow post-commit deletion must not hold the accepted command response."""
    session, _attempt, request, _source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    deletion_started = asyncio.Event()
    release_deletion = asyncio.Event()
    workers: list[asyncio.Task[None]] = []

    async def _blocked_worker() -> None:
        deletion_started.set()
        await release_deletion.wait()

    def _queue_blocked_cleanup(_claim: object) -> None:
        workers.append(asyncio.create_task(_blocked_worker()))

    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_audio_cleanup",
        _queue_blocked_cleanup,
    )
    execution = asyncio.create_task(
        ConversationCommandService(db_session).execute(
            user_id="local", session_id=session.id, request=request
        )
    )
    try:
        await asyncio.wait_for(deletion_started.wait(), timeout=1)
        assert execution.done(), "accepted command waited for filesystem cleanup"
        result = execution.result()
        receipt = await db_session.scalar(
            select(ConversationCommandResultRecord).where(
                ConversationCommandResultRecord.session_id == session.id,
                ConversationCommandResultRecord.command_id == request.command_id,
            )
        )
        assert result.result == "accepted_processing"
        assert receipt is not None
        assert receipt.result_json == result.model_dump(mode="json")
    finally:
        release_deletion.set()
        await execution
        await asyncio.gather(*workers)


@pytest.mark.asyncio
async def test_uploaded_cancel_queues_cleanup_after_yielding_post_commit_callback(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A yielding callback must not let cleanup start before the response boundary."""
    session, _attempt, request, _source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    workers: list[asyncio.Task[None]] = []
    callback_saw_cleanup: list[bool] = []

    async def _blocked_worker() -> None:
        cleanup_started.set()
        await release_cleanup.wait()

    def _queue_blocked_cleanup(_claim: object) -> None:
        workers.append(asyncio.create_task(_blocked_worker()))

    async def _yielding_after_commit(_work: object) -> None:
        await asyncio.sleep(0)
        callback_saw_cleanup.append(cleanup_started.is_set())

    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_audio_cleanup",
        _queue_blocked_cleanup,
    )
    try:
        result = await ConversationCommandService(
            db_session, after_commit=_yielding_after_commit
        ).execute(user_id="local", session_id=session.id, request=request)
        assert result.result == "accepted_processing"
        assert callback_saw_cleanup == [False]
    finally:
        release_cleanup.set()
        await asyncio.gather(*workers)


@pytest.mark.asyncio
async def test_cancelled_cleanup_worker_contains_failure_for_deadline_recovery(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker crashes leave only the durable pending claim for bounded recovery."""
    session, attempt, request, _source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    cleanup_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)

    async def _crash_delete(
        _retention: CoachRetentionService,
        _claim: CancelledUploadCleanupClaim,
    ) -> str:
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr(
        CoachRetentionService,
        "delete_cancelled_upload_audio",
        _crash_delete,
    )
    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    assert len(cleanup_claims) == 1

    worker_sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    await _safe_process_audio_cleanup_claim(
        cleanup_claims[0], session_factory=worker_sessions
    )

    await db_session.refresh(attempt)
    job = await db_session.get(AsyncJob, result.async_job_id)
    assert result.result == "accepted_processing"
    assert (attempt.audio_retention_state, attempt.async_job_id) == (
        "delete_pending",
        result.async_job_id,
    )
    assert job is not None and job.status == "running"


@pytest.mark.asyncio
async def test_uploaded_cancel_duplicate_replay_does_not_reclaim_or_repeat_events(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing command-receipt replay would create another cleanup job/event."""
    session, attempt, request, _source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    cleanup_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)
    service = ConversationCommandService(db_session)
    first = await service.execute(
        user_id="local", session_id=session.id, request=request
    )
    event_count = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id)).where(
            InterviewSessionEvent.session_id == session.id
        )
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    assert first.result == "accepted_processing"
    assert replay == first
    assert len(cleanup_claims) == 1
    assert (
        await db_session.scalar(
            select(func.count(AsyncJob.id)).where(
                AsyncJob.type == "coach_cancelled_upload_cleanup"
            )
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session.id
            )
        )
        == event_count
    )
    await db_session.refresh(attempt)
    assert attempt.attempt_state == "cancelled"


@pytest.mark.asyncio
async def test_uploaded_cancel_records_a_retryable_cleanup_failure_without_unlinking(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treating a media-boundary failure as success would erase its retry signal."""
    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    from app.services import coach_retention

    def _media_boundary_failure(*_args, **_kwargs):
        raise CoachMediaError("coach_attempt_upload_conflict")

    monkeypatch.setattr(
        coach_retention,
        "open_verified_audio_deletion_lease",
        _media_boundary_failure,
    )
    cleanup_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)
    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    assert len(cleanup_claims) == 1
    await _run_cancelled_cleanup_worker(db_session, cleanup_claims[0])

    await db_session.refresh(attempt)
    job = await db_session.get(AsyncJob, result.async_job_id)
    receipt = await db_session.scalar(
        select(InterviewAttemptUpload).where(
            InterviewAttemptUpload.attempt_id == attempt.id,
            InterviewAttemptUpload.upload_id == "uploaded-cancel-upload",
        )
    )
    assert result.result == "accepted_processing"
    assert source.exists()
    assert (
        attempt.attempt_state,
        attempt.audio_retention_state,
        attempt.audio_uri,
        attempt.async_job_id,
    ) == ("cancelled", "delete_failed", str(source), None)
    assert receipt is not None and receipt.result_state == "completed"
    assert job is not None and (job.status, job.error) == (
        "failed",
        "coach_audio_deletion_failed",
    )


@pytest.mark.asyncio
async def test_cancelled_delete_failure_projects_one_exact_retry_and_replays_it(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new command must create one fresh cancelled-cleanup generation only."""
    session, attempt, _source, initial_claim, initial_job_id = (
        await _seed_terminal_cancelled_cleanup_failure(
            db_session, isolated_cancel_media_root, monkeypatch
        )
    )
    retry_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)

    live = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )
    assert live.retention.retryable_audio_cleanup_attempt_id == attempt.id
    assert "delete_audio" in live.allowed_commands

    retry_request = command(
        "delete_audio",
        version=live.state_version,
        command_id="cancelled-cleanup-retry",
        payload={"attempt_id": attempt.id},
    )
    first = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=retry_request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=retry_request
    )

    assert first.result == "accepted_processing"
    assert replay == first
    assert len(retry_claims) == 1
    retry_claim = retry_claims[0]
    assert retry_claim.recording_id == attempt.id
    assert retry_claim.job_id == first.async_job_id
    assert retry_claim.job_id != initial_job_id
    assert retry_claim.claim_token != initial_claim.claim_token
    assert (
        await db_session.scalar(
            select(func.count(AsyncJob.id)).where(
                AsyncJob.type == "coach_cancelled_upload_cleanup"
            )
        )
        == 2
    )
    await db_session.refresh(attempt)
    assert (attempt.audio_retention_state, attempt.async_job_id) == (
        "delete_pending",
        retry_claim.job_id,
    )


@pytest.mark.asyncio
async def test_cancelled_cleanup_retry_rejects_unsurfaced_and_stale_authority(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client ID is never deletion authority after the live snapshot goes stale."""
    session, attempt, _source, initial_claim, _initial_job_id = (
        await _seed_terminal_cancelled_cleanup_failure(
            db_session, isolated_cancel_media_root, monkeypatch
        )
    )
    session_id = session.id
    attempt_id = attempt.id
    live = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session_id
    )
    assert live.retention.retryable_audio_cleanup_attempt_id == attempt_id
    initial_job_count = await db_session.scalar(
        select(func.count(AsyncJob.id)).where(
            AsyncJob.type == "coach_cancelled_upload_cleanup"
        )
    )

    with pytest.raises(ConversationCommandError) as wrong_id:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session_id,
            request=command(
                "delete_audio",
                version=live.state_version,
                command_id="cancelled-cleanup-wrong-id",
                payload={"attempt_id": "other-cancelled-attempt"},
            ),
        )
    assert wrong_id.value.code == "coach_attempt_stale_claim"

    attempt.audio_content_hash = "f" * 64
    await db_session.commit()
    await db_session.refresh(attempt)
    with pytest.raises(ConversationCommandError) as stale_hash:
        await ConversationCommandService(db_session).execute(
            user_id="local",
                session_id=session_id,
            request=command(
                "delete_audio",
                version=live.state_version,
                command_id="cancelled-cleanup-stale-hash",
                payload={"attempt_id": attempt_id},
            ),
        )
    assert stale_hash.value.code == "coach_attempt_stale_claim"

    attempt.audio_content_hash = initial_claim.audio_content_hash
    stale_job = AsyncJob(type="coach_cancelled_upload_cleanup", status="failed")
    db_session.add(stale_job)
    await db_session.flush()
    attempt.async_job_id = stale_job.id
    await db_session.commit()
    await db_session.refresh(attempt)
    with pytest.raises(ConversationCommandError) as stale_job_result:
        await ConversationCommandService(db_session).execute(
            user_id="local",
                session_id=session_id,
            request=command(
                "delete_audio",
                version=live.state_version,
                command_id="cancelled-cleanup-stale-job",
                payload={"attempt_id": attempt_id},
            ),
        )
    assert stale_job_result.value.code == "coach_attempt_stale_claim"
    assert (
        await db_session.scalar(
            select(func.count(AsyncJob.id)).where(
                AsyncJob.type == "coach_cancelled_upload_cleanup"
            )
        )
        == initial_job_count + 1
    )


@pytest.mark.asyncio
async def test_terminal_cancelled_cleanup_failure_is_never_auto_reclaimed(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconciliation must not publish another terminal failure for this generation."""
    session, attempt, _source, _initial_claim, _initial_job_id = (
        await _seed_terminal_cancelled_cleanup_failure(
            db_session, isolated_cancel_media_root, monkeypatch
        )
    )
    before_versions = (
        attempt.attempt_version,
        session.state_version,
        session.retention_version,
    )
    before_events = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id)).where(
            InterviewSessionEvent.session_id == session.id,
            InterviewSessionEvent.recording_id == attempt.id,
            InterviewSessionEvent.event_type == "audio_delete_failed",
        )
    )

    assert await reconcile_conversational_session(db_session, session.id) == 0
    assert await reconcile_conversational_session(db_session, session.id) == 0

    await db_session.refresh(attempt)
    await db_session.refresh(session)
    assert (
        attempt.attempt_version,
        session.state_version,
        session.retention_version,
    ) == before_versions
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session.id,
                InterviewSessionEvent.recording_id == attempt.id,
                InterviewSessionEvent.event_type == "audio_delete_failed",
            )
        )
        == before_events
    )


@pytest.mark.asyncio
async def test_live_skips_invalid_cancelled_cleanup_rows_across_keyset_pages(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid early page must not hide the first authoritative retry candidate."""
    session, attempt, _source, _initial_claim, _initial_job_id = (
        await _seed_terminal_cancelled_cleanup_failure(
            db_session, isolated_cancel_media_root, monkeypatch
        )
    )
    base = attempt.created_at - timedelta(seconds=21)
    db_session.add_all(
        SessionRecording(
            session_id=session.id,
            recording_type="audio",
            attempt_state="cancelled",
            attempt_version=2,
            audio_uri=str(isolated_cancel_media_root / f"invalid-{index:02d}.webm"),
            audio_content_hash="a" * 64,
            audio_retention_policy="retain_until_deleted",
            audio_retention_state="delete_failed",
            created_at=base + timedelta(seconds=index),
        )
        for index in range(20)
    )
    await db_session.commit()

    live = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert live.retention.retryable_audio_cleanup_attempt_id == attempt.id
    assert "delete_audio" in live.allowed_commands


@pytest.mark.asyncio
async def test_live_hides_cancelled_cleanup_retry_without_exact_upload_authority(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A terminal state alone is insufficient to expose a deletion command."""
    session, attempt, _source, _initial_claim, _initial_job_id = (
        await _seed_terminal_cancelled_cleanup_failure(
            db_session, isolated_cancel_media_root, monkeypatch
        )
    )
    receipt = await db_session.scalar(
        select(InterviewAttemptUpload).where(
            InterviewAttemptUpload.attempt_id == attempt.id,
            InterviewAttemptUpload.result_state == "completed",
        )
    )
    assert receipt is not None
    receipt.result_state = "deleted"
    await db_session.commit()

    live = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert live.retention.retryable_audio_cleanup_attempt_id is None
    assert "delete_audio" not in live.allowed_commands


@pytest.mark.asyncio
async def test_uploaded_cancel_treats_absent_owned_media_as_truthfully_deleted(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leaving a missing owned upload temporary would strand a false retention claim."""
    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    source.unlink()
    cleanup_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    assert len(cleanup_claims) == 1
    await _run_cancelled_cleanup_worker(db_session, cleanup_claims[0])

    await db_session.refresh(attempt)
    receipt = await db_session.scalar(
        select(InterviewAttemptUpload).where(
            InterviewAttemptUpload.attempt_id == attempt.id,
            InterviewAttemptUpload.upload_id == "uploaded-cancel-upload",
        )
    )
    assert result.result == "accepted_processing"
    assert not source.exists()
    assert (attempt.attempt_state, attempt.audio_retention_state, attempt.audio_uri) == (
        "cancelled",
        "deleted",
        None,
    )
    assert receipt is not None and receipt.result_state == "deleted"


@pytest.mark.asyncio
async def test_uploaded_cancel_never_unlinks_a_post_claim_replacement(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping the hash/inode fence would delete the replacement below."""
    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    from app.services import coach_retention

    real_open = coach_retention.open_verified_audio_deletion_lease

    def _replace_before_open(*args, **kwargs):
        source.write_bytes(b"replacement audio must survive")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(
        coach_retention,
        "open_verified_audio_deletion_lease",
        _replace_before_open,
    )
    cleanup_claims = _capture_cancelled_cleanup_dispatch(monkeypatch)
    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    assert len(cleanup_claims) == 1
    await _run_cancelled_cleanup_worker(db_session, cleanup_claims[0])

    await db_session.refresh(attempt)
    assert result.result == "accepted_processing"
    assert source.read_bytes() == b"replacement audio must survive"
    assert attempt.audio_retention_state == "delete_failed"


@pytest.mark.asyncio
async def test_startup_reconciliation_finishes_an_expired_cancelled_upload_claim(
    db_session: AsyncSession,
    isolated_cancel_media_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing bounded startup recovery would leave a crash-stranded upload pending."""
    session, attempt, request, source = await _seed_uploaded_cancellable_attempt(
        db_session, isolated_cancel_media_root
    )
    attempt_id = attempt.id
    from app.services import coach_retention

    real_open = coach_retention.open_verified_audio_deletion_lease

    def _simulate_process_crash(*_args, **_kwargs):
        raise RuntimeError("simulated worker termination")

    monkeypatch.setattr(
        coach_retention,
        "open_verified_audio_deletion_lease",
        _simulate_process_crash,
    )
    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    job = await db_session.get(AsyncJob, result.async_job_id)
    assert job is not None and job.result_json is not None
    persisted_claim = json.loads(job.result_json)
    deadline = datetime.fromisoformat(persisted_claim["deadline_at"])
    assert job.status == "running"
    assert source.exists()
    monkeypatch.setattr(
        settings,
        "HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS",
        settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 600,
    )

    monkeypatch.setattr(
        coach_retention,
        "open_verified_audio_deletion_lease",
        real_open,
    )
    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    class _AfterDeadline(datetime):
        @classmethod
        def utcnow(cls) -> datetime:
            return deadline + timedelta(seconds=1)

    monkeypatch.setattr("app.services.coach_reconciliation.datetime", _AfterDeadline)
    assert await reconcile_stale_coach_state(batch_size=1) == 1

    db_session.expire_all()
    recovered_attempt = await db_session.get(SessionRecording, attempt_id)
    recovered_receipt = await db_session.scalar(
        select(InterviewAttemptUpload).where(
            InterviewAttemptUpload.attempt_id == attempt_id,
            InterviewAttemptUpload.upload_id == "uploaded-cancel-upload",
        )
    )
    recovered_job = await db_session.get(AsyncJob, result.async_job_id)
    assert recovered_attempt is not None
    assert (
        recovered_attempt.attempt_state,
        recovered_attempt.audio_retention_state,
        recovered_attempt.audio_uri,
        recovered_attempt.async_job_id,
    ) == ("cancelled", "deleted", None, None)
    assert recovered_receipt is not None and recovered_receipt.result_state == "deleted"
    assert recovered_job is not None and recovered_job.status == "done"
    assert not source.exists()


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
async def test_record_capture_hard_stop_persists_one_technical_event_and_replays(
    db_session: AsyncSession,
) -> None:
    """A hard recording boundary must be an idempotent, non-submitting event."""
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0, question_count=1
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
            command_id="hard-stop-begin",
            payload={
                "recording_type": "audio",
                "client_attempt_id": "hard-stop-attempt",
            },
        ),
    )
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    await db_session.refresh(session)
    authority_before = (session.state_version, session.activity_version)
    attempt_before = (
        attempt.attempt_state,
        attempt.attempt_version,
        attempt.processing_generation,
        attempt.async_job_id,
        attempt.audio_uri,
        attempt.audio_content_hash,
        attempt.audio_retention_state,
    )
    dependent_rows_before = {
        "uploads": await db_session.scalar(
            select(func.count(InterviewAttemptUpload.id)).where(
                InterviewAttemptUpload.attempt_id == attempt.id
            )
        ),
        "evaluations": await db_session.scalar(
            select(func.count(InterviewAttemptEvaluation.id)).where(
                InterviewAttemptEvaluation.recording_id == attempt.id
            )
        ),
        "stages": await db_session.scalar(
            select(func.count(InterviewAttemptStage.id)).where(
                InterviewAttemptStage.recording_id == attempt.id
            )
        ),
        "jobs": await db_session.scalar(select(func.count(AsyncJob.id))),
    }
    request = command(
        "record_capture_hard_stop",
        version=begun.state_version,
        command_id="hard-stop-command",
        payload={"attempt_id": attempt.id},
    )

    result = await service.execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert replay == result
    assert (result.state, result.state_version) == (
        "listening",
        authority_before[0] + 1,
    )
    assert "record_capture_hard_stop" in result.allowed_commands
    assert (session.status, session.conversation_state) == ("active", "listening")
    assert (session.state_version, session.activity_version) == (
        authority_before[0] + 1,
        authority_before[1] + 1,
    )
    assert (
        attempt.attempt_state,
        attempt.attempt_version,
        attempt.processing_generation,
        attempt.async_job_id,
        attempt.audio_uri,
        attempt.audio_content_hash,
        attempt.audio_retention_state,
    ) == attempt_before
    assert {
        "uploads": await db_session.scalar(
            select(func.count(InterviewAttemptUpload.id)).where(
                InterviewAttemptUpload.attempt_id == attempt.id
            )
        ),
        "evaluations": await db_session.scalar(
            select(func.count(InterviewAttemptEvaluation.id)).where(
                InterviewAttemptEvaluation.recording_id == attempt.id
            )
        ),
        "stages": await db_session.scalar(
            select(func.count(InterviewAttemptStage.id)).where(
                InterviewAttemptStage.recording_id == attempt.id
            )
        ),
        "jobs": await db_session.scalar(select(func.count(AsyncJob.id))),
    } == dependent_rows_before
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.command_id == request.command_id)
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
            event.question_id,
            event.recording_id,
            event.payload_json,
        )
        for event in events
    ] == [
        (
            "answer_capture_hard_limit_reached",
            "candidate",
            "listening",
            "listening",
            result.state_version,
            questions[0].id,
            attempt.id,
            {"limit_ms": 600000},
        )
    ]


@pytest.mark.asyncio
async def test_record_capture_hard_stop_rejects_typed_replaced_and_stale_attempts(
    db_session: AsyncSession,
) -> None:
    """Only the current listening audio capture may record the hard boundary."""
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0, question_count=1
    )
    session_id = session.id
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    typed = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            command_id="hard-stop-typed-begin",
            payload={
                "recording_type": "text",
                "client_attempt_id": "hard-stop-typed-attempt",
            },
        ),
    )
    typed_attempt = await db_session.get(SessionRecording, typed.active_attempt_id)
    assert typed_attempt is not None
    assert "record_capture_hard_stop" not in typed.allowed_commands
    typed_attempt_id = typed_attempt.id
    typed_authority = (session.state_version, session.activity_version)

    with pytest.raises(ConversationCommandError) as typed_error:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command(
                "record_capture_hard_stop",
                version=typed.state_version,
                command_id="hard-stop-typed",
                payload={"attempt_id": typed_attempt_id},
            ),
        )

    assert typed_error.value.code == "coach_attempt_not_active"

    with pytest.raises(ConversationCommandError) as wrong_attempt_error:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command(
                "record_capture_hard_stop",
                version=typed.state_version,
                command_id="hard-stop-wrong-attempt",
                payload={"attempt_id": "unrelated-attempt"},
            ),
        )

    assert wrong_attempt_error.value.code == "coach_attempt_not_active"
    await db_session.refresh(session)
    assert (session.state_version, session.activity_version) == typed_authority

    session.active_recording_id = "replaced-audio-attempt"
    await db_session.commit()
    replaced_version = session.state_version
    with pytest.raises(ConversationCommandError) as replaced_error:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command(
                "record_capture_hard_stop",
                version=replaced_version,
                command_id="hard-stop-replaced",
                payload={"attempt_id": typed_attempt_id},
            ),
        )
    assert replaced_error.value.code == "coach_attempt_not_active"

    with pytest.raises(ConversationCommandError) as stale_error:
        await service.execute(
            user_id="local",
            session_id=session_id,
            request=command(
                "record_capture_hard_stop",
                version=replaced_version - 1,
                command_id="hard-stop-stale",
                payload={"attempt_id": "replaced-audio-attempt"},
            ),
        )
    assert stale_error.value.code == "coach_conversation_version_conflict"


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
    with pytest.raises(ConversationCommandError) as raised:
        await service.execute(
            user_id="local",
            session_id=session.id,
            request=command(
                "retry_answer", version=finished.state_version,
                payload={"question_id": questions[0].id},
            ),
        )
    assert raised.value.code == "coach_conversation_invalid_state"

    prior = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(questions[0])
    assert prior is not None and prior.attempt_state == "pending_processing"
    assert questions[0].attempts_created_count == 1


@pytest.mark.asyncio
async def test_skip_resolves_to_next_question_within_command_transaction(
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
    assert result.state == "asking"
    assert result.active_question_id == questions[1].id
    assert (questions[1].question_state, questions[1].asked_sequence) == ("asked", 2)
    assert result.state_version == 4
    await db_session.refresh(session)
    assert session.activity_version == 1
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session.id)
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
            event.question_id,
        )
        for event in events
    ] == [
        ("question_skipped", "candidate", "asking", "asking", 4, questions[0].id),
        ("question_advanced", "system", "asking", "asking", 4, questions[1].id),
        ("question_presented", "system", "asking", "asking", 4, questions[1].id),
    ]


@pytest.mark.asyncio
async def test_skip_ignores_stale_pending_adaptive_follow_up(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=3
    )
    session.active_question_id = questions[0].id
    session.active_root_question_id = questions[0].id
    questions[0].question_state = "asked"
    questions[0].asked_sequence = 1
    questions[1].order_in_session = 3
    adaptive = SessionQuestion(
        id="stale-pending-adaptive",
        session_id=session.id,
        question_num=99,
        text="Stale adaptive follow-up",
        category="behavioural",
        difficulty="realistic",
        order_in_session=2,
        question_kind="adaptive_follow_up",
        root_question_id=questions[0].id,
        parent_question_id=questions[0].id,
        follow_up_depth=1,
        follow_up_reason="clarify_example",
        question_state="pending",
    )
    db_session.add(adaptive)
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("skip_question", version=3),
    )

    await db_session.refresh(adaptive)
    await db_session.refresh(questions[1])
    assert result.active_question_id == questions[1].id
    assert questions[1].question_state == "asked"
    assert adaptive.question_state == "pending"


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
@pytest.mark.parametrize("projection", ("accepted", "advanced", "cleared"))
async def test_client_attempt_replay_survives_later_session_projection(
    db_session: AsyncSession,
    projection: str,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    session.active_root_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    service = ConversationCommandService(db_session)
    payload = {
        "recording_type": "text",
        "client_attempt_id": f"projected-retry-{projection}",
    }
    first = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command("begin_answer", version=0, payload=payload),
    )
    attempt = await db_session.get(SessionRecording, first.active_attempt_id)
    assert attempt is not None
    attempt.attempt_state = "completed"
    attempt.evaluation_state = "completed"
    questions[0].question_state = "answered"
    questions[0].accepted_recording_id = attempt.id
    session.state_version = first.state_version + 1
    if projection == "accepted":
        session.conversation_state = "awaiting_next_action"
    elif projection == "advanced":
        session.conversation_state = "asking"
        session.active_question_id = questions[1].id
        session.active_root_question_id = questions[1].id
        session.active_recording_id = None
        questions[1].question_state = "asked"
        questions[1].asked_sequence = 2
    else:
        session.conversation_state = "reporting"
        session.active_question_id = None
        session.active_root_question_id = None
        session.active_recording_id = None
    await db_session.commit()

    replay = await service.execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=session.state_version,
            payload=payload,
            command_id=f"new-command-after-{projection}",
        ),
    )

    assert replay.result == "duplicate"
    assert replay.active_attempt_id == attempt.id
    assert await db_session.scalar(select(func.count(SessionRecording.id))) == 1


@pytest.mark.asyncio
async def test_client_attempt_replay_keeps_recording_type_conflict(
    db_session: AsyncSession,
) -> None:
    session, questions = await seed_session(
        db_session, state="asking", status="active", version=0
    )
    session.active_question_id = questions[0].id
    questions[0].question_state = "asked"
    await db_session.commit()
    client_attempt_id = "recording-type-conflict"
    begun = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command(
            "begin_answer",
            version=0,
            payload={
                "recording_type": "text",
                "client_attempt_id": client_attempt_id,
            },
        ),
    )
    session.conversation_state = "reporting"
    session.active_question_id = None
    session.active_recording_id = None
    session.state_version = begun.state_version + 1
    await db_session.commit()

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command(
                "begin_answer",
                version=session.state_version,
                payload={
                    "recording_type": "audio",
                    "client_attempt_id": client_attempt_id,
                },
                command_id="new-command-recording-type-conflict",
            ),
        )

    assert raised.value.code == "coach_attempt_client_id_conflict"


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


async def _seed_retryable_audio_processing(
    db: AsyncSession, *, retry_count: int = 0, retry_limit: int = 2
) -> tuple[
    InterviewSession,
    SessionQuestion,
    SessionRecording,
    InterviewAttemptEvaluation,
    InterviewTranscriptVersion,
]:
    session, questions = await seed_session(
        db, state="recoverable_error", status="active", version=11
    )
    question = questions[0]
    question.question_state = "asked"
    prior_deadline = datetime.utcnow() - timedelta(seconds=1)
    prior_job = AsyncJob(
        id="prior-retry-job",
        type="coach_attempt_processing",
        status="failed",
    )
    db.add(prior_job)
    transcript = InterviewTranscriptVersion(
        recording_id="retry-audio-attempt",
        version_number=1,
        transcript="A bounded immutable answer.",
        source="transcription",
        content_hash="transcript-hash",
        created_by="system",
        processing_generation=1,
    )
    attempt = SessionRecording(
        id="retry-audio-attempt",
        session_id=session.id,
        question_id=question.id,
        recording_type="audio",
        audio_uri=None,
        audio_content_hash="a" * 64,
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="recoverable_error",
        evaluation_state="failed",
        processing_generation=1,
        processing_retry_count=retry_count,
        processing_retry_limit=retry_limit,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="temporary",
    )
    db.add(attempt)
    await db.flush()
    transcript.recording_id = attempt.id
    db.add(transcript)
    await db.flush()
    attempt.current_transcript_version_id = transcript.id
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=1,
        state="failed",
        evaluation_contract_version="coach_conversational_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=prior_job.id,
        diagnostics_json={
            "processing_claim": {
                "processing_generation": 1,
                "job_deadline_at": prior_deadline.isoformat(),
                "source_audio_content_hash": "a" * 64,
                "source_transcript_version_id": None,
                "expected_session_state_version": 10,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": "prior-retry-token",
            },
            "result": {"reason_code": "coach_evaluation_unavailable"},
        },
    )
    db.add(evaluation)
    await db.flush()
    attempt.current_evaluation_version_id = evaluation.id
    prior_states = {
        "audio_persist": "completed",
        "transcription": "completed",
        "speech_analysis": "completed",
        "content_evaluation": "failed_retryable",
        "evidence_grounding": "failed_retryable",
        "follow_up_decision": "failed_retryable",
        "coaching_enrichment": "failed_retryable",
        "audio_cleanup": "failed_retryable",
    }
    transcript_bound = {
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    }
    for stage_name, stage_state in prior_states.items():
        transcript_input = stage_name in {
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }
        stage_diagnostics = {
            "processing_contract_version": "coach_processing_v1",
            "evaluation_contract_version": "coach_conversational_rubric_v1",
            "evidence_contract_version": "coach_evidence_grounding_v1",
            "follow_up_contract_version": "coach_follow_up_v1",
            "source_audio_content_hash": "a" * 64,
            "source_transcript_version_id": (
                transcript.id if transcript_input else None
            ),
            "source_transcript_content_hash": (
                transcript.content_hash if transcript_input else None
            ),
            "result_transcript_version_id": (
                transcript.id if stage_name == "transcription" else None
            ),
            "result_transcript_content_hash": (
                transcript.content_hash if stage_name == "transcription" else None
            ),
        }
        db.add(
            InterviewAttemptStage(
                recording_id=attempt.id,
                evaluation_version_id=evaluation.id,
                stage_name=stage_name,
                stage_state=stage_state,
                attempt_count=1,
                job_id=prior_job.id,
                claim_token="prior-retry-token",
                expected_processing_generation=1,
                source_transcript_version_id=(
                    transcript.id if stage_name in transcript_bound else None
                ),
                job_deadline_at=prior_deadline,
                completed_at=datetime.utcnow(),
                last_error_code=(
                    "coach_evaluation_unavailable"
                    if stage_state == "failed_retryable"
                    else None
                ),
                diagnostics_json=stage_diagnostics,
            )
        )
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    session.active_recording_id = attempt.id
    session.recoverable_error_scope = "attempt_processing"
    session.recoverable_error_code = "coach_evaluation_unavailable"
    await db.commit()
    return session, question, attempt, evaluation, transcript


@pytest.mark.asyncio
async def test_retry_processing_is_atomic_reuses_valid_upstream_and_replays_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _, attempt, prior_evaluation, transcript = (
        await _seed_retryable_audio_processing(db_session)
    )
    dispatched = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        dispatched.append,
    )
    request = command(
        "retry_processing", version=session.state_version, command_id="retry-processing-1"
    )

    first = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session.id, request=request
    )

    await db_session.refresh(session)
    await db_session.refresh(attempt)
    evaluations = list(
        (
            await db_session.scalars(
                select(InterviewAttemptEvaluation)
                .where(InterviewAttemptEvaluation.recording_id == attempt.id)
                .order_by(InterviewAttemptEvaluation.version_number)
            )
        ).all()
    )
    assert first == replay
    assert first.result == "accepted_processing"
    assert len(dispatched) == 1
    assert (attempt.processing_generation, attempt.processing_retry_count) == (2, 1)
    assert (attempt.attempt_state, attempt.evaluation_state) == (
        "pending_processing",
        "pending",
    )
    assert session.conversation_state == "processing_answer"
    assert session.state_version == 12
    assert len(evaluations) == 2
    assert evaluations[0].id == prior_evaluation.id
    assert evaluations[1].state == "pending"
    assert evaluations[1].transcript_version_id == transcript.id
    new_stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id == evaluations[1].id
                )
            )
        ).all()
    )
    by_name = {stage.stage_name: stage for stage in new_stages}
    assert len(by_name) == 8
    assert {
        name: by_name[name].stage_state
        for name in ("audio_persist", "transcription", "speech_analysis")
    } == {
        "audio_persist": "reused",
        "transcription": "reused",
        "speech_analysis": "reused",
    }
    assert all(
        by_name[name].reused_from_stage_id is not None
        for name in ("audio_persist", "transcription", "speech_analysis")
    )
    assert {
        by_name[name].stage_state
        for name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
            "audio_cleanup",
        )
    } == {"pending"}


@pytest.mark.asyncio
async def test_content_retry_preserves_terminal_speech_without_audio_source(
    db_session: AsyncSession,
) -> None:
    session, _, attempt, evaluation, _ = await _seed_retryable_audio_processing(
        db_session
    )
    speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert speech is not None
    speech.stage_state = "unavailable"
    speech.last_error_code = "speech_analysis_unavailable"
    await db_session.commit()

    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=command("retry_processing", version=session.state_version),
    )

    new_evaluation = await db_session.scalar(
        select(InterviewAttemptEvaluation)
        .where(
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.version_number == 2,
        )
    )
    assert new_evaluation is not None
    new_speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == new_evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert result.result == "accepted_processing"
    assert new_speech is not None
    assert new_speech.stage_state == "unavailable"
    assert new_speech.last_error_code == "speech_analysis_unavailable"


@pytest.mark.asyncio
async def test_audio_retry_verifies_owned_media_before_consuming_manual_budget(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, attempt, evaluation, _ = await _seed_retryable_audio_processing(
        db_session
    )
    media_root = tmp_path / "coach-media"
    media_root.mkdir()
    missing_audio = media_root / session.id / "missing.webm"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(media_root))
    attempt.audio_uri = str(missing_audio)
    attempt.audio_retention_state = "retained"
    speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert speech is not None
    speech.stage_state = "failed_retryable"
    speech.last_error_code = "coach_evaluation_unavailable"
    db_session.add(
        InterviewAttemptUpload(
            attempt_id=attempt.id,
            upload_id="missing-retry-source",
            request_hash="request-hash",
            content_sha256=attempt.audio_content_hash,
            byte_size=16,
            mime_type="audio/webm",
            storage_uri=str(missing_audio),
            result_state="completed",
            completed_at=datetime.utcnow(),
        )
    )
    await db_session.commit()
    before = (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command("retry_processing", version=session.state_version),
        )

    assert raised.value.code == "coach_attempt_retry_source_unavailable"
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retry_count", "retry_limit", "remove_transcript", "expected_code"),
    (
        (2, 2, False, "coach_attempt_retry_budget_exhausted"),
        (0, 2, True, "coach_attempt_retry_source_unavailable"),
    ),
)
async def test_retry_processing_rejection_consumes_no_budget_or_generation(
    db_session: AsyncSession,
    retry_count: int,
    retry_limit: int,
    remove_transcript: bool,
    expected_code: str,
) -> None:
    session, _, attempt, _, transcript = await _seed_retryable_audio_processing(
        db_session, retry_count=retry_count, retry_limit=retry_limit
    )
    if remove_transcript:
        attempt.current_transcript_version_id = None
        await db_session.flush()
        await db_session.delete(transcript)
        await db_session.commit()
    before = (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command("retry_processing", version=session.state_version),
        )

    assert raised.value.code == expected_code
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    ) == before


@pytest.mark.asyncio
async def test_retry_processing_refuses_mismatched_reuse_diagnostics_without_mutation(
    db_session: AsyncSession,
) -> None:
    session, _, attempt, evaluation, _ = await _seed_retryable_audio_processing(
        db_session
    )
    speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert speech is not None
    speech.diagnostics_json = {
        **speech.diagnostics_json,
        "source_audio_content_hash": "mismatched-audio-hash",
    }
    await db_session.commit()
    before = (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command("retry_processing", version=session.state_version),
        )

    assert raised.value.code == "coach_attempt_retry_source_unavailable"
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    (
        "job_id",
        "claim_token",
        "deadline",
        "source_transcript",
        "generation",
        "reused_provenance",
    ),
)
async def test_retry_processing_requires_exact_prior_stage_ownership(
    db_session: AsyncSession,
    corruption: str,
) -> None:
    session, _, attempt, evaluation, transcript = (
        await _seed_retryable_audio_processing(db_session)
    )
    speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    audio_persist = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.stage_name == "audio_persist",
        )
    )
    assert speech is not None and audio_persist is not None
    if corruption == "job_id":
        other_job = AsyncJob(type="coach_attempt_processing", status="failed")
        db_session.add(other_job)
        await db_session.flush()
        speech.job_id = other_job.id
    elif corruption == "claim_token":
        speech.claim_token = "wrong-prior-token"
    elif corruption == "deadline":
        speech.job_deadline_at += timedelta(microseconds=1)
    elif corruption == "source_transcript":
        speech.source_transcript_version_id = transcript.id
    elif corruption == "generation":
        speech.expected_processing_generation += 1
    else:
        speech.stage_state = "reused"
        speech.reused_from_stage_id = audio_persist.id
    await db_session.commit()
    before = (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command("retry_processing", version=session.state_version),
        )

    assert raised.value.code == "coach_attempt_stale_claim"
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    ) == before


@pytest.mark.asyncio
async def test_retry_processing_refuses_nonretryable_recorded_failure_without_mutation(
    db_session: AsyncSession,
) -> None:
    session, _, attempt, _, _ = await _seed_retryable_audio_processing(db_session)
    session.recoverable_error_code = "coach_attempt_upload_hash_mismatch"
    await db_session.commit()
    before = (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    )

    with pytest.raises(ConversationCommandError) as raised:
        await ConversationCommandService(db_session).execute(
            user_id="local",
            session_id=session.id,
            request=command("retry_processing", version=session.state_version),
        )

    assert raised.value.code == "coach_attempt_stale_claim"
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    assert (
        session.state_version,
        attempt.processing_generation,
        attempt.processing_retry_count,
    ) == before


@pytest.mark.asyncio
async def test_terminal_skip_resolves_to_reporting_within_command_transaction(
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
    session.active_root_question_id = questions[0].id
    questions[0].question_state = "asked"
    questions[0].asked_sequence = 1
    await db_session.commit()
    session_id = session.id
    question_id = questions[0].id
    request = command("skip_question", version=4)

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session_id, request=request
    )

    persisted_session = await db_session.get(InterviewSession, session_id)
    persisted_question = await db_session.get(SessionQuestion, question_id)
    assert persisted_session is not None and persisted_question is not None
    assert (result.state, result.state_version) == ("reporting", 5)
    assert (
        persisted_session.status,
        persisted_session.conversation_state,
        persisted_session.state_version,
        persisted_session.activity_version,
    ) == (
        "active",
        "reporting",
        5,
        1,
    )
    assert persisted_session.active_question_id is None
    assert persisted_session.active_root_question_id is None
    assert persisted_session.active_recording_id is None
    assert persisted_question.question_state == "skipped"
    assert persisted_session.report_state == "building"
    assert persisted_session.report_build_reason == "initial_completion"
    assert persisted_session.report_contract_version == "coach_conversational_report_v1"
    assert persisted_session.report_job_id is not None
    job = await db_session.get(AsyncJob, persisted_session.report_job_id)
    assert job is not None
    assert (job.type, job.status) == ("coach_conversational_report", "pending")
    report_job_count = await db_session.scalar(
        select(func.count(AsyncJob.id)).where(
            AsyncJob.type == "coach_conversational_report"
        )
    )
    assert report_job_count == 1
    event_count = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id)).where(
            InterviewSessionEvent.session_id == session_id
        )
    )
    assert event_count == 2
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session_id)
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
            event.question_id,
        )
        for event in events
    ] == [
        ("question_skipped", "candidate", "asking", "reporting", 5, question_id),
        ("report_claimed", "system", "asking", "reporting", 5, question_id),
    ]

    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=session_id, request=request
    )
    assert replay == result
    await db_session.refresh(persisted_session)
    assert persisted_session.state_version == result.state_version
    assert (
        await db_session.scalar(
            select(func.count(ConversationCommandResultRecord.id)).where(
                ConversationCommandResultRecord.session_id == session_id
            )
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count(AsyncJob.id)).where(
                AsyncJob.type == "coach_conversational_report"
            )
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session_id
            )
        )
        == event_count
    )
