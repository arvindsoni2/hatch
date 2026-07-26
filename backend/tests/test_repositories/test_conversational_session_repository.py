"""Transactional contract tests for conversational Coach persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from app.repositories.conversational_session_repository import (
    AttemptLimitExhausted,
    AttemptProcessingResult,
    AttemptReservationConflict,
    CommandIdempotencyConflict,
    ConversationVersionConflict,
    ConversationalSessionRepository,
    SessionEventInput,
    StaleVersion,
    canonical_request_hash,
)
from app.schemas.coach_conversation import ConversationCommandRequest


def _command(**overrides: object) -> ConversationCommandRequest:
    values: dict[str, object] = {
        "command_id": "cmd-1",
        "command_type": "begin_answer",
        "expected_state_version": 4,
        "payload": {
            "recording_type": "text",
            "client_attempt_id": "client-attempt-1",
        },
        "contract_version": "coach_conversation_command_v1",
    }
    values.update(overrides)
    return ConversationCommandRequest.model_validate(values)


def test_canonical_hash_uses_semantic_defaults_and_domain_separation() -> None:
    implicit = _command()
    explicit = _command(
        payload={
            "recording_type": "text",
            "client_attempt_id": "client-attempt-1",
        }
    )
    reordered = ConversationCommandRequest.model_validate_json(
        '{"payload":{"recording_type":"text","client_attempt_id":"client-attempt-1"},'
        '"contract_version":"coach_conversation_command_v1",'
        '"expected_state_version":4,"command_type":"begin_answer","command_id":"different"}'
    )

    expected = "139749faefb375f985cf7dc4fcaef0f498b5471c53b8856d627ccd1186b2e52f"
    assert canonical_request_hash(implicit, session_id="session-1") == expected
    assert canonical_request_hash(explicit, session_id="session-1") == expected
    assert canonical_request_hash(reordered, session_id="session-1") == expected
    assert canonical_request_hash(implicit, session_id="session-2") != expected
    assert (
        canonical_request_hash(
            _command(expected_state_version=5), session_id="session-1"
        )
        != expected
    )


@pytest_asyncio.fixture
async def repository_database(tmp_path: Path):
    database = tmp_path / "repository.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


async def _seed_session(
    factory: async_sessionmaker[AsyncSession],
    *,
    session_id: str = "session-1",
    question_id: str = "question-1",
    state_version: int = 4,
    attempts_created_count: int = 0,
) -> None:
    async with factory.begin() as db:
        db.add(
            InterviewSession(
                id=session_id,
                company_name="Example",
                role_title="Engineer",
                experience_version="conversational_v1",
                status="active",
                conversation_state="asking",
                state_version=state_version,
                retention_policy_json={"audio": "delete_after_processing"},
            )
        )
        db.add(
            SessionQuestion(
                id=question_id,
                session_id=session_id,
                question_num=1,
                text="Tell me about a difficult delivery.",
                category="behavioural",
                difficulty="medium",
                order_in_session=1,
                question_state="asked",
                attempts_created_count=attempts_created_count,
            )
        )


@pytest.mark.asyncio
async def test_duplicate_command_precedes_stale_version_and_survives_restart(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    request = _command()
    request_hash = canonical_request_hash(request, session_id="session-1")

    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        claim = await repository.claim_conversation_command(
            session_id="session-1", request=request, request_hash=request_hash
        )
        assert claim.is_duplicate is False
        await repository.complete_conversation_command(
            claim=claim,
            result={"result": "completed", "state_version": 5},
            result_state="completed",
        )

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.state_version = 99

    async with repository_database.begin() as restarted_db:
        replay = await ConversationalSessionRepository(
            restarted_db
        ).claim_conversation_command(
            session_id="session-1", request=request, request_hash=request_hash
        )
        assert replay.is_duplicate is True
        assert replay.result_json == {"result": "completed", "state_version": 5}


@pytest.mark.asyncio
async def test_same_command_id_with_different_hash_conflicts(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    request = _command()
    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        claim = await repository.claim_conversation_command(
            session_id="session-1",
            request=request,
            request_hash=canonical_request_hash(request, session_id="session-1"),
        )
        await repository.complete_conversation_command(
            claim=claim, result={"result": "completed"}, result_state="completed"
        )

    async with repository_database.begin() as db:
        with pytest.raises(CommandIdempotencyConflict):
            await ConversationalSessionRepository(db).claim_conversation_command(
                session_id="session-1",
                request=request,
                request_hash="f" * 64,
            )


@pytest.mark.asyncio
async def test_concurrent_identical_command_is_claimed_once(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    request = _command()
    request_hash = canonical_request_hash(request, session_id="session-1")

    async def claim():
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(db).claim_conversation_command(
                session_id="session-1", request=request, request_hash=request_hash
            )

    claims = await asyncio.gather(claim(), claim())
    assert sum(not claim.is_duplicate for claim in claims) == 1
    assert sum(claim.is_duplicate for claim in claims) == 1
    assert claims[0].record_id == claims[1].record_id


@pytest.mark.asyncio
async def test_new_stale_command_creates_no_receipt(repository_database) -> None:
    await _seed_session(repository_database)
    stale = _command(expected_state_version=3)
    async with repository_database() as db:
        with pytest.raises(ConversationVersionConflict):
            async with db.begin():
                await ConversationalSessionRepository(db).claim_conversation_command(
                    session_id="session-1",
                    request=stale,
                    request_hash=canonical_request_hash(stale, session_id="session-1"),
                )
        await db.rollback()

    async with repository_database() as db:
        count = await db.scalar(select(func.count(ConversationCommandResultRecord.id)))
        assert count == 0


@pytest.mark.asyncio
async def test_event_allocation_is_contiguous_and_rollback_leaves_no_gap(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database() as db:
        with pytest.raises(RuntimeError):
            async with db.begin():
                repository = ConversationalSessionRepository(db)
                await repository.append_session_events(
                    session_id="session-1",
                    events=(
                        SessionEventInput("session_started", "system", 4),
                        SessionEventInput("question_presented", "system", 4),
                    ),
                )
                raise RuntimeError("force rollback")

    async with repository_database.begin() as db:
        events = await ConversationalSessionRepository(db).append_session_events(
            session_id="session-1",
            events=(
                SessionEventInput("session_started", "system", 4),
                SessionEventInput("question_presented", "system", 4),
                SessionEventInput("hint_requested", "candidate", 4),
            ),
        )
        assert [event.sequence_number for event in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_concurrent_event_allocation_has_unique_contiguous_sequences(
    repository_database,
) -> None:
    await _seed_session(repository_database)

    async def append(event_type: str) -> int:
        async with repository_database.begin() as db:
            (event,) = await ConversationalSessionRepository(db).append_session_events(
                session_id="session-1",
                events=(SessionEventInput(event_type, "system", 4),),
            )
            return event.sequence_number

    allocated = await asyncio.gather(
        append("session_started"), append("question_presented")
    )
    assert sorted(allocated) == [1, 2]


@pytest.mark.asyncio
async def test_attempt_reservation_is_monotonic_snapshotted_and_transfers_hints(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        question = await db.get(SessionQuestion, "question-1")
        assert question is not None
        question.pending_hint_count = 2
        question.pending_hint_types_json = ["star_structure", "clarify_question"]

    async with repository_database.begin() as db:
        reservation = await ConversationalSessionRepository(
            db
        ).reserve_conversational_attempt(
            session_id="session-1",
            question_id="question-1",
            client_attempt_id="client-1",
            recording_type="text",
            expected_state_version=4,
            attempt_kind="primary",
            max_attempts=5,
            processing_retry_limit=2,
            audio_retention_policy="delete_after_processing",
        )
        assert reservation.attempt.attempt_number == 1
        assert reservation.attempt.hint_count == 2
        assert reservation.pending_hint_types == (
            "star_structure",
            "clarify_question",
        )
        assert reservation.attempt.processing_retry_limit == 2
        assert reservation.attempt.audio_retention_policy == "delete_after_processing"

    async with repository_database() as db:
        question = await db.get(SessionQuestion, "question-1")
        session = await db.get(InterviewSession, "session-1")
        assert question is not None and session is not None
        assert question.attempts_created_count == 1
        assert question.pending_hint_count == 0
        assert question.pending_hint_types_json is None
        assert session.active_recording_id == reservation.attempt.id
        assert session.conversation_state == "listening"
        assert session.state_version == 5


@pytest.mark.asyncio
async def test_duplicate_client_attempt_precedes_state_version_and_limit_validation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    arguments = dict(
        session_id="session-1",
        question_id="question-1",
        client_attempt_id="client-1",
        recording_type="audio",
        expected_state_version=4,
        attempt_kind="primary",
        max_attempts=5,
        processing_retry_limit=2,
        audio_retention_policy="retain_until_deleted",
    )
    async with repository_database.begin() as db:
        original = await ConversationalSessionRepository(
            db
        ).reserve_conversational_attempt(**arguments)

    async with repository_database.begin() as db:
        duplicate = await ConversationalSessionRepository(
            db
        ).reserve_conversational_attempt(
            **{**arguments, "expected_state_version": 0, "max_attempts": 0}
        )
        assert duplicate.is_duplicate is True
        assert duplicate.attempt.id == original.attempt.id

    async with repository_database.begin() as db:
        with pytest.raises(AttemptReservationConflict):
            await ConversationalSessionRepository(db).reserve_conversational_attempt(
                **{**arguments, "question_id": "different-question"}
            )
        with pytest.raises(AttemptReservationConflict):
            await ConversationalSessionRepository(db).reserve_conversational_attempt(
                **{**arguments, "recording_type": "text"}
            )


@pytest.mark.asyncio
async def test_limit_counts_terminal_attempts_and_rejects_sixth(
    repository_database,
) -> None:
    await _seed_session(repository_database, attempts_created_count=5)
    async with repository_database.begin() as db:
        for number, state in enumerate(
            ("cancelled", "invalid", "unavailable", "deleted", "completed"), start=1
        ):
            db.add(
                SessionRecording(
                    id=f"attempt-{number}",
                    session_id="session-1",
                    question_id="question-1",
                    recording_type="text",
                    attempt_number=number,
                    attempt_kind="primary" if number == 1 else "retry",
                    attempt_state=state,
                    processing_retry_limit=2,
                    client_attempt_id=f"old-{number}",
                )
            )

    async with repository_database.begin() as db:
        with pytest.raises(AttemptLimitExhausted):
            await ConversationalSessionRepository(db).reserve_conversational_attempt(
                session_id="session-1",
                question_id="question-1",
                client_attempt_id="sixth",
                recording_type="text",
                expected_state_version=4,
                attempt_kind="retry",
                max_attempts=5,
                processing_retry_limit=2,
                audio_retention_policy="delete_after_processing",
            )


@pytest.mark.asyncio
async def test_concurrent_fifth_and_sixth_reservations_create_only_fifth(
    repository_database,
) -> None:
    await _seed_session(repository_database, attempts_created_count=4)
    async with repository_database.begin() as db:
        for number in range(1, 5):
            db.add(
                SessionRecording(
                    id=f"attempt-{number}",
                    session_id="session-1",
                    question_id="question-1",
                    recording_type="text",
                    attempt_number=number,
                    attempt_kind="primary" if number == 1 else "retry",
                    attempt_state="cancelled",
                    processing_retry_limit=2,
                    client_attempt_id=f"old-{number}",
                )
            )

    async def reserve(client_id: str):
        async with repository_database() as db:
            try:
                async with db.begin():
                    return await ConversationalSessionRepository(
                        db
                    ).reserve_conversational_attempt(
                        session_id="session-1",
                        question_id="question-1",
                        client_attempt_id=client_id,
                        recording_type="text",
                        expected_state_version=4,
                        attempt_kind="retry",
                        max_attempts=5,
                        processing_retry_limit=2,
                        audio_retention_policy="delete_after_processing",
                    )
            except (
                AttemptLimitExhausted,
                AttemptReservationConflict,
                ConversationVersionConflict,
            ) as error:
                return error

    results = await asyncio.gather(reserve("client-five"), reserve("client-six"))
    reservations = [result for result in results if not isinstance(result, Exception)]
    assert len(reservations) == 1
    assert reservations[0].attempt.attempt_number == 5
    async with repository_database() as db:
        question = await db.get(SessionQuestion, "question-1")
        assert question is not None
        assert question.attempts_created_count == 5
        assert await db.scalar(select(func.count(SessionRecording.id))) == 5


@pytest.mark.asyncio
async def test_concurrent_begin_creates_at_most_one_active_attempt(
    repository_database,
) -> None:
    await _seed_session(repository_database)

    async def reserve(client_id: str):
        async with repository_database() as db:
            try:
                async with db.begin():
                    return await ConversationalSessionRepository(
                        db
                    ).reserve_conversational_attempt(
                        session_id="session-1",
                        question_id="question-1",
                        client_attempt_id=client_id,
                        recording_type="text",
                        expected_state_version=4,
                        attempt_kind="primary",
                        max_attempts=5,
                        processing_retry_limit=2,
                        audio_retention_policy="delete_after_processing",
                    )
            except (AttemptReservationConflict, ConversationVersionConflict):
                return None

    results = await asyncio.gather(reserve("client-a"), reserve("client-b"))
    assert sum(result is not None for result in results) == 1
    async with repository_database() as db:
        attempts = (await db.scalars(select(SessionRecording))).all()
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1


@pytest.mark.asyncio
async def test_version_creation_and_stale_processing_finaliser_are_fenced(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-1",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="client-1",
            )
        )

    deadline = datetime.utcnow() + timedelta(minutes=2)
    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        transcript = await repository.create_transcript_version(
            recording_id="attempt-1",
            source="candidate_text",
            transcript="A concise answer.",
            expected_attempt_version=0,
            processing_generation=1,
        )
        evaluation = await repository.create_evaluation_version(
            recording_id="attempt-1",
            transcript_version_id=transcript.id,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-1",
        )
        claim = await repository.claim_attempt_processing(
            recording_id="attempt-1",
            expected_generation=0,
            job_id="job-1",
            deadline=deadline,
        )
        assert claim is not None
        assert claim.evaluation_version_id == evaluation.id

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "processing_answer"
        session.active_recording_id = "attempt-1"

    stale_claim = claim.__class__(**{**claim.__dict__, "job_id": "stale-job"})
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=stale_claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={"code": "ok"},
            ),
        )
        assert changed is False

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        evaluation_row = await db.get(InterviewAttemptEvaluation, evaluation.id)
        assert attempt is not None and evaluation_row is not None
        assert attempt.current_evaluation_version_id is None
        assert attempt.evaluation_state is None
        assert evaluation_row.state == "pending"

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "asking"
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={"code": "ok"},
            ),
        )
        assert changed is False
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        evaluation_row = await db.get(InterviewAttemptEvaluation, evaluation.id)
        assert attempt is not None and evaluation_row is not None
        assert attempt.current_evaluation_version_id is None
        assert evaluation_row.state == "pending"

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "processing_answer"
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={"code": "ok"},
            ),
        )
        assert changed is True
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        session = await db.get(InterviewSession, "session-1")
        assert attempt is not None and session is not None
        assert attempt.current_evaluation_version_id == evaluation.id
        assert attempt.evaluation_state == "completed"
        assert session.conversation_state == "awaiting_next_action"


@pytest.mark.asyncio
async def test_failed_processing_claim_rolls_back_attempt_generation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-without-evaluation",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="client-no-evaluation",
            )
        )

    async with repository_database.begin() as db:
        with pytest.raises(StaleVersion):
            await ConversationalSessionRepository(db).claim_attempt_processing(
                recording_id="attempt-without-evaluation",
                expected_generation=0,
                job_id="job-without-evaluation",
                deadline=datetime.utcnow() + timedelta(minutes=2),
            )

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-without-evaluation")
        assert attempt is not None
        assert attempt.processing_generation == 0
        assert attempt.attempt_state == "draft"
        assert attempt.async_job_id is None


@pytest.mark.asyncio
async def test_event_payload_does_not_persist_raw_candidate_content(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="content"):
            await ConversationalSessionRepository(db).append_session_events(
                session_id="session-1",
                events=(
                    SessionEventInput(
                        "answer_submitted",
                        "candidate",
                        4,
                        payload_json={"transcript": "raw candidate answer"},
                    ),
                ),
            )
    async with repository_database() as db:
        assert await db.scalar(select(func.count(InterviewSessionEvent.id))) == 0
        assert await db.scalar(select(func.count(InterviewTranscriptVersion.id))) == 0
