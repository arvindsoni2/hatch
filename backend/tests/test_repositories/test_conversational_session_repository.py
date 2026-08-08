"""Transactional contract tests for conversational Coach persistence."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.async_job import AsyncJob
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
from app.repositories.conversational_session_repository import (
    AttemptLimitExhausted,
    AttemptProcessingResult,
    AttemptReservationConflict,
    CommandIdempotencyConflict,
    ConversationVersionConflict,
    ConversationalSessionRepository,
    FollowUpAdmissionClaim,
    SessionEventInput,
    StaleVersion,
    _stage_immutable_diagnostics,
    canonical_request_hash,
)
from app.schemas.coach_conversation import ConversationCommandRequest
from app.schemas.coach import CreateSessionRequest
from app.services.coach_session_plan import (
    SessionPlanError,
    claim_session_setup,
    load_claim_planning_request,
)


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
                active_question_id=question_id,
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


def _setup_request() -> CreateSessionRequest:
    return CreateSessionRequest.model_validate(
        {
            "company_name": "Example",
            "role_title": "Engineer",
            "jd_text": "Build reliable systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "mixed",
                "difficulty": "realistic",
                "duration_minutes": 30,
                "planned_question_count": 6,
                "role_family": "software_engineering",
                "role_level": "senior",
                "industry": "technology",
                "locale": "en-GB",
                "focus_areas": ["architecture"],
                "allowed_answer_modes": ["text"],
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
        }
    )


async def _claim_attempt_for_finalisation(
    factory: async_sessionmaker[AsyncSession],
    *,
    recording_type: str,
    attempt_id: str,
    job_id: str,
):
    deadline = datetime.utcnow() + timedelta(minutes=5)
    async with factory.begin() as db:
        db.add(
            SessionRecording(
                id=attempt_id,
                session_id="session-1",
                question_id="question-1",
                recording_type=recording_type,
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft" if recording_type == "text" else "uploaded",
                audio_content_hash=("d" * 64 if recording_type == "audio" else None),
                processing_retry_limit=2,
                client_attempt_id=f"client-{attempt_id}",
            )
        )
    transcript_id = None
    async with factory.begin() as db:
        repository = ConversationalSessionRepository(db)
        if recording_type == "text":
            transcript = await repository.create_transcript_version(
                recording_id=attempt_id,
                source="candidate_text",
                transcript="A source answer.",
                expected_attempt_version=0,
                processing_generation=1,
            )
            transcript_id = transcript.id
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = attempt_id
        await repository.create_evaluation_version(
            recording_id=attempt_id,
            transcript_version_id=transcript_id,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id=job_id,
        )
        claim = await repository.claim_attempt_processing(
            recording_id=attempt_id,
            expected_generation=0,
            job_id=job_id,
            deadline=deadline,
        )
        assert claim is not None
    async with factory.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "processing_answer"
        session.active_recording_id = attempt_id
        session.state_version += 1
    return claim, transcript_id


async def _processing_fence(db: AsyncSession, claim):
    fence = await ConversationalSessionRepository(db)._get_attempt_processing_fence(
        claim
    )
    assert fence is not None
    return fence


async def _seed_invalid_media_terminal_stages(
    factory: async_sessionmaker[AsyncSession], claim
) -> None:
    async with factory.begin() as db:
        fence = await _processing_fence(db, claim)
        for stage_name in (
            "audio_persist",
            "transcription",
            "speech_analysis",
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
            "audio_cleanup",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state=(
                        "unavailable"
                        if stage_name
                        in {"audio_persist", "transcription", "speech_analysis"}
                        else "not_applicable"
                    ),
                    job_id=claim.job_id,
                    claim_token=fence.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=None,
                    job_deadline_at=claim.deadline_at,
                    completed_at=datetime.utcnow(),
                    last_error_code=(
                        "invalid_audio"
                        if stage_name in {"audio_persist", "transcription"}
                        else (
                            "speech_analysis_unavailable"
                            if stage_name == "speech_analysis"
                            else None
                        )
                    ),
                )
            )


async def _seed_terminal_attempt_for_acceptance(
    factory: async_sessionmaker[AsyncSession],
    *,
    attempt_id: str = "attempt-accept",
    evaluation_state: str = "completed",
) -> tuple[str, str]:
    transcript_id = f"transcript-{attempt_id}"
    evaluation_id = f"evaluation-{attempt_id}"
    async with factory.begin() as db:
        attempt = SessionRecording(
            id=attempt_id,
            session_id="session-1",
            question_id="question-1",
            recording_type="text",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state=evaluation_state,
            evaluation_state=evaluation_state,
            processing_generation=3,
            processing_retry_limit=2,
            client_attempt_id=f"client-{attempt_id}",
        )
        db.add(attempt)
        await db.flush()
        db.add(
            InterviewTranscriptVersion(
                id=transcript_id,
                recording_id=attempt_id,
                version_number=1,
                transcript="Terminal transcript.",
                source="candidate_text",
                content_hash="f" * 64,
                created_by="candidate",
                processing_generation=3,
            )
        )
        await db.flush()
        db.add(
            InterviewAttemptEvaluation(
                id=evaluation_id,
                recording_id=attempt_id,
                transcript_version_id=transcript_id,
                version_number=1,
                state=evaluation_state,
                evaluation_contract_version="coach_conversational_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
                diagnostics_json={
                    "processing_claim": {"processing_generation": 3},
                    **(
                        {"result": {"reason_code": "coach_evaluation_unavailable"}}
                        if evaluation_state == "unavailable"
                        else {}
                    ),
                },
            )
        )
        await db.flush()
        if evaluation_state == "unavailable":
            for stage_name, stage_state in (
                ("content_evaluation", "failed_terminal"),
                ("evidence_grounding", "not_applicable"),
                ("follow_up_decision", "not_applicable"),
            ):
                db.add(
                    InterviewAttemptStage(
                        recording_id=attempt_id,
                        evaluation_version_id=evaluation_id,
                        stage_name=stage_name,
                        stage_state=stage_state,
                        source_transcript_version_id=transcript_id,
                        last_error_code=(
                            "coach_evaluation_unavailable"
                            if stage_name == "content_evaluation"
                            else None
                        ),
                    )
                )
        attempt.current_transcript_version_id = transcript_id
        attempt.current_evaluation_version_id = evaluation_id
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "awaiting_next_action"
        session.active_recording_id = attempt_id
    return transcript_id, evaluation_id


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
async def test_concurrent_different_commands_serialize_before_version_check(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    requests = (
        _command(command_id="different-a"),
        _command(command_id="different-b"),
    )

    async def claim_and_advance(request: ConversationCommandRequest):
        try:
            async with repository_database.begin() as db:
                repository = ConversationalSessionRepository(db)
                claim = await repository.claim_conversation_command(
                    session_id="session-1",
                    request=request,
                    request_hash=canonical_request_hash(
                        request, session_id="session-1"
                    ),
                )
                session = await db.get(InterviewSession, "session-1")
                assert session is not None
                session.state_version += 1
                session.conversation_state = "listening"
                await repository.complete_conversation_command(
                    claim=claim,
                    result={"result": "completed"},
                )
            return "completed"
        except ConversationVersionConflict as error:
            return (error.current_state_version, error.current_state)

    outcomes = await asyncio.gather(*(claim_and_advance(item) for item in requests))

    assert outcomes.count("completed") == 1
    assert outcomes.count((5, "listening")) == 1
    async with repository_database() as db:
        assert (
            await db.scalar(select(func.count(ConversationCommandResultRecord.id))) == 1
        )


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
        assert session.activity_version == 0


@pytest.mark.asyncio
async def test_attempt_reservation_rollback_restores_both_session_versions(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database() as db:
        with pytest.raises(RuntimeError, match="rollback"):
            async with db.begin():
                await ConversationalSessionRepository(
                    db
                ).reserve_conversational_attempt(
                    session_id="session-1",
                    question_id="question-1",
                    client_attempt_id="rollback-attempt",
                    recording_type="text",
                    expected_state_version=4,
                    attempt_kind="primary",
                    max_attempts=5,
                    processing_retry_limit=2,
                    audio_retention_policy="delete_after_processing",
                )
                raise RuntimeError("force rollback")

    async with repository_database() as db:
        session = await db.get(InterviewSession, "session-1")
        question = await db.get(SessionQuestion, "question-1")
        assert session is not None and question is not None
        assert (session.state_version, session.activity_version) == (4, 0)
        assert question.attempts_created_count == 0
        assert await db.scalar(select(func.count(SessionRecording.id))) == 0


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
        duplicate = await ConversationalSessionRepository(
            db
        ).reserve_conversational_attempt(**{**arguments, "attempt_kind": "retry"})
        assert duplicate.is_duplicate is True
        assert duplicate.attempt.id == original.attempt.id


@pytest.mark.asyncio
async def test_new_attempt_requires_the_session_active_question(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionQuestion(
                id="question-owned-but-inactive",
                session_id="session-1",
                question_num=2,
                text="An inactive question",
                category="behavioural",
                difficulty="medium",
                order_in_session=2,
                question_state="asked",
            )
        )

    async with repository_database.begin() as db:
        with pytest.raises(AttemptReservationConflict, match="active"):
            await ConversationalSessionRepository(db).reserve_conversational_attempt(
                session_id="session-1",
                question_id="question-owned-but-inactive",
                client_attempt_id="inactive-question-attempt",
                recording_type="text",
                expected_state_version=4,
                attempt_kind="primary",
                max_attempts=5,
                processing_retry_limit=2,
                audio_retention_policy="delete_after_processing",
            )


@pytest.mark.asyncio
async def test_new_attempt_checks_state_before_attempt_limit(
    repository_database,
) -> None:
    await _seed_session(repository_database, attempts_created_count=5)
    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "paused"

    async with repository_database.begin() as db:
        with pytest.raises(AttemptReservationConflict, match="active"):
            await ConversationalSessionRepository(db).reserve_conversational_attempt(
                session_id="session-1",
                question_id="question-1",
                client_attempt_id="new-client-id",
                recording_type="text",
                expected_state_version=4,
                attempt_kind="primary",
                max_attempts=5,
                processing_retry_limit=2,
                audio_retention_policy="delete_after_processing",
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
        session = await db.get(InterviewSession, "session-1")
        assert question is not None and session is not None
        assert question.attempts_created_count == 5
        assert await db.scalar(select(func.count(SessionRecording.id))) == 5
        assert (session.state_version, session.activity_version) == (5, 0)


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
        session = await db.get(InterviewSession, "session-1")
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert session is not None
        assert (session.state_version, session.activity_version) == (5, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript", ("abcd", "abcde"), ids=("exact", "over"))
async def test_candidate_transcript_enforces_snapshotted_code_point_limit(
    repository_database, transcript
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="bounded-text-attempt",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="bounded-text-client",
            )
        )

    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db, max_transcript_characters=4)
        if len(transcript) == 4:
            created = await repository.create_transcript_version(
                recording_id="bounded-text-attempt",
                source="candidate_text",
                transcript=transcript,
                expected_attempt_version=0,
                processing_generation=1,
            )
            assert created.transcript == transcript
        else:
            with pytest.raises(ValueError, match="limit"):
                await repository.create_transcript_version(
                    recording_id="bounded-text-attempt",
                    source="candidate_text",
                    transcript=transcript,
                    expected_attempt_version=0,
                    processing_generation=1,
                )

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "bounded-text-attempt")
        assert attempt is not None
        expected_count = 1 if len(transcript) == 4 else 0
        assert attempt.attempt_version == expected_count
        assert (attempt.current_transcript_version_id is not None) == bool(
            expected_count
        )
        assert (
            await db.scalar(select(func.count(InterviewTranscriptVersion.id)))
            == expected_count
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript", ("abcd", "abcde"), ids=("exact", "over"))
async def test_worker_transcript_enforces_snapshotted_code_point_limit(
    repository_database, transcript
) -> None:
    await _seed_session(repository_database)
    claim, _ = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="audio",
        attempt_id="bounded-audio-attempt",
        job_id="bounded-audio-job",
    )
    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db, max_transcript_characters=4)
        fence = await _processing_fence(db, claim)
        if len(transcript) == 4:
            created = await repository.create_worker_transcript_version(
                recording_id=claim.recording_id,
                transcript=transcript,
                expected_job_id=claim.job_id,
                expected_processing_generation=claim.processing_generation,
                expected_audio_content_hash="d" * 64,
                expected_evaluation_version_id=claim.evaluation_version_id,
                expected_claim_token=fence.claim_token,
            )
            assert created is not None and created.transcript == transcript
        else:
            with pytest.raises(ValueError, match="limit"):
                await repository.create_worker_transcript_version(
                    recording_id=claim.recording_id,
                    transcript=transcript,
                    expected_job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    expected_audio_content_hash="d" * 64,
                    expected_evaluation_version_id=claim.evaluation_version_id,
                    expected_claim_token=fence.claim_token,
                )

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert attempt is not None and evaluation is not None
        expected_count = 1 if len(transcript) == 4 else 0
        assert (attempt.current_transcript_version_id is not None) == bool(
            expected_count
        )
        assert (evaluation.transcript_version_id is not None) == bool(expected_count)
        assert (
            await db.scalar(select(func.count(InterviewTranscriptVersion.id)))
            == expected_count
        )


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
        attempt_after_transcript = await db.get(SessionRecording, "attempt-1")
        assert attempt_after_transcript is not None
        assert attempt_after_transcript.attempt_version == 1
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = "attempt-1"
        await repository.create_evaluation_version(
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
        evaluation_id = claim.evaluation_version_id
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id="attempt-1",
                    evaluation_version_id=evaluation_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id="job-1",
                    expected_processing_generation=1,
                    source_transcript_version_id=transcript.id,
                    job_deadline_at=deadline,
                )
            )

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "processing_answer"
        session.active_recording_id = "attempt-1"
        session.state_version += 1

    stale_claim = claim.__class__(**{**claim.__dict__, "job_id": "stale-job"})
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=stale_claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={
                    "diagnostics": {
                        "stages": ["audio_persist", "audio_cleanup"],
                        "state": "not_started",
                        "reason_codes": [
                            "transcription_unavailable",
                            "invalid_audio",
                        ],
                    }
                },
            ),
        )
        assert changed is False

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        evaluation_row = await db.get(InterviewAttemptEvaluation, evaluation_id)
        assert attempt is not None and evaluation_row is not None
        assert attempt.current_evaluation_version_id is None
        assert attempt.evaluation_state == "pending"
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
                diagnostics={},
            ),
        )
        assert changed is False
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        evaluation_row = await db.get(InterviewAttemptEvaluation, evaluation_id)
        assert attempt is not None and evaluation_row is not None
        assert attempt.current_evaluation_version_id is None
        assert evaluation_row.state == "pending"

    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "processing_answer"
        stage = await db.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id == evaluation_id,
                InterviewAttemptStage.stage_name == "content_evaluation",
            )
        )
        assert stage is not None
        stage.stage_state = "running"
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={},
            ),
        )
        assert changed is False
    async with repository_database.begin() as db:
        stage = await db.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id == evaluation_id,
                InterviewAttemptStage.stage_name == "content_evaluation",
            )
        )
        assert stage is not None
        stage.stage_state = "completed"
        stage.source_transcript_version_id = "stale-transcript"
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={},
            ),
        )
        assert changed is False
    async with repository_database.begin() as db:
        stage = await db.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id == evaluation_id,
                InterviewAttemptStage.stage_name == "content_evaluation",
            )
        )
        assert stage is not None
        stage.source_transcript_version_id = transcript.id

    late_claim = claim.__class__(
        **{**claim.__dict__, "deadline_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=late_claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={},
            ),
        )
        assert changed is False
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript.id,
                diagnostics={},
            ),
        )
        assert changed is True
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        session = await db.get(InterviewSession, "session-1")
        assert attempt is not None and session is not None
        assert attempt.current_evaluation_version_id == evaluation_id
        assert attempt.evaluation_state == "completed"
        assert session.conversation_state == "awaiting_next_action"


@pytest.mark.asyncio
async def test_stale_invalid_media_finaliser_rolls_back_every_authority_mutation(
    repository_database,
) -> None:
    """A late session-fence miss must undo earlier attempt/evaluation updates."""
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="audio",
        attempt_id="invalid-media-stale",
        job_id="invalid-media-stale-job",
    )
    assert transcript_id is None
    await _seed_invalid_media_terminal_stages(repository_database, claim)
    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, claim.session_id)
        assert session is not None
        session.active_question_id = None

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        session = await db.get(InterviewSession, claim.session_id)
        assert attempt is not None and evaluation is not None and session is not None
        before_attempt = (
            attempt.attempt_state,
            attempt.evaluation_state,
            attempt.evaluation_json,
            attempt.current_evaluation_version_id,
            attempt.async_job_id,
            attempt.processing_completed_at,
        )
        before_evaluation = (
            evaluation.state,
            evaluation.diagnostics_json,
            evaluation.completed_at,
        )
        before_session = (
            session.status,
            session.conversation_state,
            session.state_version,
            session.activity_version,
            session.event_version,
        )
        before_events = await db.scalar(select(func.count(InterviewSessionEvent.id)))

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(
            db
        ).finalise_invalid_attempt_media(claim=claim)
        assert changed is False

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        session = await db.get(InterviewSession, claim.session_id)
        question = await db.get(SessionQuestion, claim.question_id)
        assert (
            attempt is not None
            and evaluation is not None
            and session is not None
            and question is not None
        )
        assert (
            attempt.attempt_state,
            attempt.evaluation_state,
            attempt.evaluation_json,
            attempt.current_evaluation_version_id,
            attempt.async_job_id,
            attempt.processing_completed_at,
        ) == before_attempt
        assert (
            evaluation.state,
            evaluation.diagnostics_json,
            evaluation.completed_at,
        ) == before_evaluation
        assert (
            session.status,
            session.conversation_state,
            session.state_version,
            session.activity_version,
            session.event_version,
        ) == before_session
        assert question.accepted_recording_id is None
        assert await db.scalar(select(func.count(InterviewSessionEvent.id))) == before_events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hidden_binding",
    (
        "orphan_transcript",
        "audio_persist",
        "transcription",
        "speech_analysis",
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    ),
)
async def test_invalid_media_finaliser_rejects_every_hidden_transcript_binding(
    repository_database, hidden_binding: str
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="audio",
        attempt_id=f"hidden-binding-{hidden_binding}",
        job_id=f"hidden-binding-job-{hidden_binding}"[:36],
    )
    assert transcript_id is None
    await _seed_invalid_media_terminal_stages(repository_database, claim)
    async with repository_database.begin() as db:
        if hidden_binding == "orphan_transcript":
            db.add(
                InterviewTranscriptVersion(
                    id="orphan-invalid-media-transcript",
                    recording_id=claim.recording_id,
                    version_number=1,
                    transcript="must not survive invalid-media authority",
                    source="transcription",
                    content_hash="a" * 64,
                    created_by="system",
                    processing_generation=claim.processing_generation,
                )
            )
        else:
            stage = await db.scalar(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == claim.evaluation_version_id,
                    InterviewAttemptStage.stage_name == hidden_binding,
                )
            )
            assert stage is not None
            stage.source_transcript_version_id = "hidden-transcript"

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(
            db
        ).finalise_invalid_attempt_media(claim=claim)
        assert changed is False

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        session = await db.get(InterviewSession, claim.session_id)
        question = await db.get(SessionQuestion, claim.question_id)
        assert (
            attempt is not None
            and evaluation is not None
            and session is not None
            and question is not None
        )
        assert (
            attempt.attempt_state,
            attempt.evaluation_state,
            attempt.current_transcript_version_id,
            attempt.current_evaluation_version_id,
            attempt.async_job_id,
        ) == ("pending_processing", "pending", None, None, claim.job_id)
        assert evaluation.state == "pending"
        assert evaluation.transcript_version_id is None
        assert session.status == "active"
        assert session.conversation_state == "processing_answer"
        assert question.accepted_recording_id is None
        assert await db.scalar(select(func.count(InterviewSessionEvent.id))) == 0


@pytest.mark.asyncio
async def test_invalid_media_evaluation_claim_replacement_loses_write_fence(
    repository_database,
) -> None:
    """Replacing diagnostics between pre-read and UPDATE must roll back authority."""
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="audio",
        attempt_id="invalid-media-claim-race",
        job_id="invalid-media-claim-race-job",
    )
    assert transcript_id is None
    await _seed_invalid_media_terminal_stages(repository_database, claim)
    async with repository_database.begin() as db:
        db.add(
            AsyncJob(
                id=claim.job_id,
                type="coach_attempt_processing",
                status="pending",
            )
        )

    replacement_injected = False

    async with repository_database.begin() as db:
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert evaluation is not None
        original_diagnostics = evaluation.diagnostics_json

        def replace_claim_before_conditional_update(
            _connection,
            cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            nonlocal replacement_injected
            if (
                not replacement_injected
                and statement.lstrip().startswith(
                    "UPDATE interview_attempt_evaluations SET"
                )
            ):
                replacement_injected = True
                cursor.execute(
                    "UPDATE interview_attempt_evaluations "
                    "SET diagnostics_json = ? WHERE id = ?",
                    (
                        json.dumps(
                            {"processing_claim": {"claim_token": "replacement"}}
                        ),
                        claim.evaluation_version_id,
                    ),
                )

        event.listen(
            db.sync_session.bind,
            "before_cursor_execute",
            replace_claim_before_conditional_update,
        )
        try:
            changed = await ConversationalSessionRepository(
                db
            ).finalise_invalid_attempt_media(claim=claim)
        finally:
            event.remove(
                db.sync_session.bind,
                "before_cursor_execute",
                replace_claim_before_conditional_update,
            )
        assert changed is False

    assert replacement_injected is True
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        session = await db.get(InterviewSession, claim.session_id)
        job = await db.get(AsyncJob, claim.job_id)
        assert (
            attempt is not None
            and evaluation is not None
            and session is not None
            and job is not None
        )
        assert (
            attempt.attempt_state,
            attempt.evaluation_state,
            attempt.current_evaluation_version_id,
            attempt.async_job_id,
        ) == ("pending_processing", "pending", None, claim.job_id)
        assert evaluation.state == "pending"
        assert evaluation.diagnostics_json == original_diagnostics
        assert evaluation.completed_at is None
        assert session.status == "active"
        assert session.conversation_state == "processing_answer"
        assert job.status == "pending" and job.result_json is None
        assert await db.scalar(select(func.count(InterviewSessionEvent.id))) == 0


@pytest.mark.asyncio
async def test_processing_finaliser_accepts_same_generation_state_multi_increment(
    repository_database,
) -> None:
    """Reintroducing the pre-pipeline state equality rejects valid worker progress."""
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-state-progress",
        job_id="job-state-progress",
    )
    assert transcript_id is not None
    async with repository_database.begin() as db:
        fence = await _processing_fence(db, claim)
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id=claim.job_id,
                    claim_token=fence.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                )
            )
        session = await db.get(InterviewSession, claim.session_id)
        assert session is not None
        session.state_version += 2
        expected_final_version = session.state_version + 1

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript_id,
                diagnostics={},
            ),
        )

    assert changed is True
    async with repository_database() as db:
        session = await db.get(InterviewSession, claim.session_id)
        attempt = await db.get(SessionRecording, claim.recording_id)
        assert session is not None and attempt is not None
        assert session.state_version == expected_final_version
        assert session.conversation_state == "awaiting_next_action"
        assert attempt.processing_generation == claim.processing_generation
        assert attempt.current_evaluation_version_id == claim.evaluation_version_id


@pytest.mark.asyncio
@pytest.mark.parametrize("reason_key", ("reason", "reason_code"))
async def test_pretranscription_unavailable_finalisation_requires_exact_diagnostic(
    repository_database, reason_key
) -> None:
    await _seed_session(repository_database)
    claim, _ = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="audio",
        attempt_id="attempt-unavailable",
        job_id="job-unavailable",
    )
    async with repository_database.begin() as db:
        db.add_all(
            [
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name="transcription",
                    stage_state="failed_terminal",
                    job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    job_deadline_at=claim.deadline_at,
                    last_error_code="transcription_unavailable",
                ),
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name="speech_analysis",
                    stage_state="unavailable",
                    job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    job_deadline_at=claim.deadline_at,
                ),
            ]
        )

    async with repository_database.begin() as db:
        invalid = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="unavailable",
                evaluation_json={},
                transcript_version_id=None,
                diagnostics={"reason_code": "invalid_audio"},
            ),
        )
        assert invalid is False

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="unavailable",
                evaluation_json={},
                transcript_version_id=None,
                diagnostics={reason_key: "transcription_unavailable"},
            ),
        )
        assert changed is True

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert attempt is not None and evaluation is not None
        assert attempt.attempt_state == "unavailable"
        assert attempt.current_transcript_version_id is None
        assert evaluation.state == "unavailable"
        assert evaluation.transcript_version_id is None

    async with repository_database.begin() as db:
        accepted = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id=claim.recording_id,
            expected_state_version=6,
        )
        assert accepted.accepted is True
        assert accepted.evaluation_state == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("recording_type", ("text", "audio"))
async def test_post_transcript_evaluator_unavailable_preserves_current_transcript(
    repository_database, recording_type
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type=recording_type,
        attempt_id=f"attempt-evaluator-unavailable-{recording_type}",
        job_id=f"job-evaluator-unavailable-{recording_type}",
    )
    async with repository_database() as db:
        fence = await _processing_fence(db, claim)
    if recording_type == "audio":
        async with repository_database.begin() as db:
            transcript = await ConversationalSessionRepository(
                db
            ).create_worker_transcript_version(
                recording_id=claim.recording_id,
                transcript="Usable audio transcript.",
                expected_job_id=claim.job_id,
                expected_processing_generation=claim.processing_generation,
                expected_audio_content_hash="d" * 64,
                expected_evaluation_version_id=claim.evaluation_version_id,
                expected_claim_token=fence.claim_token,
            )
            assert transcript is not None
            transcript_id = transcript.id
    assert transcript_id is not None
    async with repository_database.begin() as db:
        stage_states = {
            "content_evaluation": "failed_terminal",
            "evidence_grounding": "not_applicable",
            "follow_up_decision": "not_applicable",
        }
        if recording_type == "audio":
            stage_states.update(
                {"transcription": "completed", "speech_analysis": "unavailable"}
            )
        for stage_name, stage_state in stage_states.items():
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state=stage_state,
                    job_id=claim.job_id,
                    claim_token=fence.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=(
                        transcript_id
                        if stage_name
                        in {
                            "content_evaluation",
                            "evidence_grounding",
                            "follow_up_decision",
                        }
                        else None
                    ),
                    job_deadline_at=claim.deadline_at,
                    last_error_code=(
                        "coach_evaluation_unavailable"
                        if stage_name == "content_evaluation"
                        else None
                    ),
                )
            )

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="unavailable",
                evaluation_json={},
                transcript_version_id=transcript_id,
                diagnostics={"reason_code": "coach_evaluation_unavailable"},
            ),
        )
        assert changed is True
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert attempt is not None and evaluation is not None
        assert attempt.attempt_state == "unavailable"
        assert attempt.current_transcript_version_id == transcript_id
        assert evaluation.state == "unavailable"
        assert evaluation.transcript_version_id == transcript_id


@pytest.mark.asyncio
async def test_evaluator_unavailable_rejects_completed_content_stage(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-invalid-evaluator-unavailable",
        job_id="job-invalid-evaluator-unavailable",
    )
    async with repository_database() as db:
        fence = await _processing_fence(db, claim)
    assert transcript_id is not None
    async with repository_database.begin() as db:
        for stage_name, stage_state in (
            ("content_evaluation", "completed"),
            ("evidence_grounding", "not_applicable"),
            ("follow_up_decision", "not_applicable"),
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state=stage_state,
                    job_id=claim.job_id,
                    claim_token=fence.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                    last_error_code=(
                        "coach_evaluation_unavailable"
                        if stage_name == "content_evaluation"
                        else None
                    ),
                )
            )
    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="unavailable",
                evaluation_json={},
                transcript_version_id=transcript_id,
                diagnostics={"reason_code": "coach_evaluation_unavailable"},
            ),
        )
        assert changed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ("audio_hash", "candidate_edit"))
async def test_processing_finaliser_rejects_audio_hash_and_edit_races(
    repository_database, race
) -> None:
    await _seed_session(repository_database)
    recording_type = "audio" if race == "audio_hash" else "text"
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type=recording_type,
        attempt_id=f"attempt-{race}",
        job_id=f"job-{race}",
    )
    async with repository_database() as db:
        fence = await _processing_fence(db, claim)
    if recording_type == "audio":
        async with repository_database.begin() as db:
            transcript = await ConversationalSessionRepository(
                db
            ).create_worker_transcript_version(
                recording_id=claim.recording_id,
                transcript="Audio source transcript.",
                expected_job_id=claim.job_id,
                expected_processing_generation=claim.processing_generation,
                expected_audio_content_hash="d" * 64,
                expected_evaluation_version_id=claim.evaluation_version_id,
                expected_claim_token=fence.claim_token,
            )
            assert transcript is not None
            transcript_id = transcript.id
    assert transcript_id is not None
    async with repository_database.begin() as db:
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                )
            )
        if race == "candidate_edit":
            await ConversationalSessionRepository(db).create_transcript_version(
                recording_id=claim.recording_id,
                source="candidate_edit",
                transcript="Candidate edited while the worker was running.",
                expected_attempt_version=1,
                processing_generation=2,
            )
        attempt = await db.get(SessionRecording, claim.recording_id)
        assert attempt is not None
        if race == "audio_hash":
            attempt.audio_content_hash = "e" * 64
        else:
            attempt.processing_generation += 1

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript_id,
                diagnostics={},
            ),
        )
        assert changed is False
    async with repository_database() as db:
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert evaluation is not None
        assert evaluation.state == "pending"


@pytest.mark.asyncio
async def test_processing_finalisation_supersedes_prior_current_evaluation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-supersede",
        job_id="job-supersede",
    )
    assert transcript_id is not None
    async with repository_database.begin() as db:
        prior = InterviewAttemptEvaluation(
            id="prior-evaluation",
            recording_id=claim.recording_id,
            transcript_version_id=transcript_id,
            version_number=0,
            state="completed",
            evaluation_contract_version="coach_conversational_rubric_v1",
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
        )
        db.add(prior)
        await db.flush()
        attempt = await db.get(SessionRecording, claim.recording_id)
        assert attempt is not None
        attempt.current_evaluation_version_id = prior.id
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                )
            )

    async with repository_database.begin() as db:
        changed = await ConversationalSessionRepository(db).finalise_attempt_processing(
            claim=claim,
            result=AttemptProcessingResult(
                evaluation_state="completed",
                evaluation_json={"answer_level": "strong"},
                transcript_version_id=transcript_id,
                diagnostics={},
            ),
        )
        assert changed is True
    async with repository_database() as db:
        prior = await db.get(InterviewAttemptEvaluation, "prior-evaluation")
        attempt = await db.get(SessionRecording, claim.recording_id)
        assert prior is not None and attempt is not None
        assert prior.state == "superseded"
        assert attempt.current_evaluation_version_id == claim.evaluation_version_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "diagnostics",
    (
        {"transcript": "raw candidate answer"},
        {"evidence": "private evidence text"},
        {"path": "/home/candidate/private"},
        {"secret": "api_key=secret-value"},
        {"code": "ok"},
        {"code": "transcription_unavailable"},
        {"error": "invalid_audio"},
        {"error_code": "transcription_unavailable"},
        {"code": "safe_but_unknown"},
        {"error": "safe_but_unknown"},
        {"error_code": "safe_but_unknown"},
        {"reason_code": "safe_but_unknown"},
        {
            "diagnostics": {
                "diagnostics": {
                    "diagnostics": {
                        "diagnostics": {"code": "coach_evaluation_unavailable"}
                    }
                }
            }
        },
        {
            "diagnostics": {
                "hint_types": ["safe_code"] * 32,
                "stages": ["transcription"] * 32,
                "reason_codes": ["coach_evaluation_unavailable"],
            }
        },
        {
            "attempt_id": "a" * 128,
            "claim_id": "b" * 128,
            "command_id": "c" * 128,
            "evaluation_version_id": "d" * 128,
            "job_id": "e" * 128,
            "question_id": "f" * 128,
            "recording_id": "g" * 128,
            "session_id": "h" * 128,
            "stage_id": "i" * 128,
            "transcript_version_id": "j" * 128,
        },
    ),
    ids=(
        "transcript",
        "evidence",
        "path",
        "secret",
        "noncanonical_ok",
        "internal_reason_as_code",
        "internal_reason_as_error",
        "internal_reason_as_error_code",
        "unknown_code",
        "unknown_error",
        "unknown_error_code",
        "unknown_reason_code",
        "deep",
        "wide",
        "oversize",
    ),
)
async def test_processing_finaliser_rejects_unsafe_diagnostics_before_mutation(
    repository_database, diagnostics
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-unsafe-diagnostics",
        job_id="job-unsafe-diagnostics",
    )
    assert transcript_id is not None
    async with repository_database.begin() as db:
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id=claim.job_id,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                )
            )

    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="diagnostics"):
            await ConversationalSessionRepository(db).finalise_attempt_processing(
                claim=claim,
                result=AttemptProcessingResult(
                    evaluation_state="completed",
                    evaluation_json={"answer_level": "strong"},
                    transcript_version_id=transcript_id,
                    diagnostics=diagnostics,
                ),
            )

    async with repository_database() as db:
        fence = await _processing_fence(db, claim)
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        session = await db.get(InterviewSession, claim.session_id)
        assert attempt is not None and evaluation is not None and session is not None
        assert attempt.evaluation_state == "pending"
        assert attempt.current_evaluation_version_id is None
        assert evaluation.state == "pending"
        assert evaluation.diagnostics_json == {
            "processing_claim": {
                "processing_generation": claim.processing_generation,
                "job_deadline_at": claim.deadline_at.isoformat(),
                "source_audio_content_hash": None,
                "source_transcript_version_id": transcript_id,
                "expected_session_state_version": 4,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": fence.claim_token,
            }
        }
        assert (session.state_version, session.activity_version) == (5, 0)


@pytest.mark.asyncio
async def test_worker_transcript_promotion_preserves_candidate_attempt_version(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="audio-attempt",
                session_id="session-1",
                question_id="question-1",
                recording_type="audio",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="pending_processing",
                attempt_version=7,
                processing_generation=3,
                async_job_id="job-audio",
                audio_content_hash="a" * 64,
                processing_retry_limit=2,
                client_attempt_id="client-audio",
            )
        )
        await db.flush()
        db.add(
            InterviewAttemptEvaluation(
                id="evaluation-audio",
                recording_id="audio-attempt",
                version_number=1,
                state="pending",
                async_job_id="job-audio",
                evaluation_contract_version="coach_conversational_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
                diagnostics_json={
                    "processing_claim": {
                        "processing_generation": 3,
                        "claim_token": "claim-token-audio",
                    }
                },
            )
        )

    async with repository_database.begin() as db:
        transcript = await ConversationalSessionRepository(
            db
        ).create_worker_transcript_version(
            recording_id="audio-attempt",
            transcript="Worker transcript.",
            expected_job_id="job-audio",
            expected_processing_generation=3,
            expected_audio_content_hash="a" * 64,
            expected_evaluation_version_id="evaluation-audio",
            expected_claim_token="claim-token-audio",
        )
        assert transcript is not None

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "audio-attempt")
        evaluation = await db.get(InterviewAttemptEvaluation, "evaluation-audio")
        assert attempt is not None and evaluation is not None
        assert attempt.attempt_version == 7
        assert attempt.current_transcript_version_id == transcript.id
        assert attempt.transcript == "Worker transcript."
        assert evaluation.transcript_version_id == transcript.id
        assert transcript.processing_generation == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "stale_value"),
    (
        ("async_job_id", "replacement-job"),
        ("processing_generation", 4),
        ("audio_content_hash", "b" * 64),
        ("attempt_state", "recoverable_error"),
        ("evaluation_version_id", "stale-evaluation"),
        ("claim_token", "stale-claim-token"),
    ),
)
async def test_stale_worker_transcript_promotion_makes_no_mutation(
    repository_database, field, stale_value
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id="audio-attempt",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="pending_processing",
            attempt_version=2,
            processing_generation=3,
            async_job_id="job-audio",
            audio_content_hash="a" * 64,
            processing_retry_limit=2,
            client_attempt_id="client-audio",
        )
        if field not in {"evaluation_version_id", "claim_token"}:
            setattr(attempt, field, stale_value)
        db.add(attempt)
        await db.flush()
        db.add(
            InterviewAttemptEvaluation(
                id="evaluation-audio",
                recording_id="audio-attempt",
                version_number=1,
                state="pending",
                async_job_id="job-audio",
                evaluation_contract_version="coach_conversational_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
                diagnostics_json={
                    "processing_claim": {
                        "processing_generation": 3,
                        "claim_token": "claim-token-audio",
                    }
                },
            )
        )

    async with repository_database.begin() as db:
        transcript = await ConversationalSessionRepository(
            db
        ).create_worker_transcript_version(
            recording_id="audio-attempt",
            transcript="Stale worker transcript.",
            expected_job_id="job-audio",
            expected_processing_generation=3,
            expected_audio_content_hash="a" * 64,
            expected_evaluation_version_id=(
                stale_value if field == "evaluation_version_id" else "evaluation-audio"
            ),
            expected_claim_token=(
                stale_value if field == "claim_token" else "claim-token-audio"
            ),
        )
        assert transcript is None

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "audio-attempt")
        evaluation = await db.get(InterviewAttemptEvaluation, "evaluation-audio")
        assert attempt is not None and evaluation is not None
        assert attempt.attempt_version == 2
        assert attempt.current_transcript_version_id is None
        assert attempt.transcript is None
        assert evaluation.transcript_version_id is None
        assert await db.scalar(select(func.count(InterviewTranscriptVersion.id))) == 0


@pytest.mark.asyncio
async def test_processing_claim_rejects_text_attempt_without_source_transcript(
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
        claim = await ConversationalSessionRepository(db).claim_attempt_processing(
            recording_id="attempt-without-evaluation",
            expected_generation=0,
            job_id="job-without-evaluation",
            deadline=datetime.utcnow() + timedelta(minutes=2),
        )
        assert claim is None  # text claims require an immutable source transcript

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-without-evaluation")
        assert attempt is not None
        assert attempt.processing_generation == 0
        assert attempt.attempt_state == "draft"
        assert attempt.async_job_id is None


@pytest.mark.asyncio
async def test_orphan_transcript_fails_closed_without_integrity_error(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-orphan-transcript",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="client-orphan-transcript",
            )
        )
        await db.flush()
        db.add(
            InterviewTranscriptVersion(
                id="orphan-transcript",
                recording_id="attempt-orphan-transcript",
                version_number=1,
                transcript="Unreferenced transcript.",
                source="candidate_text",
                created_by="candidate",
                processing_generation=1,
            )
        )

    async with repository_database.begin() as db:
        with pytest.raises(StaleVersion, match="pointer"):
            await ConversationalSessionRepository(db).create_transcript_version(
                recording_id="attempt-orphan-transcript",
                source="candidate_text",
                transcript="Replacement transcript.",
                expected_attempt_version=0,
                processing_generation=1,
            )
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-orphan-transcript")
        assert attempt is not None
        assert attempt.current_transcript_version_id is None
        assert attempt.attempt_version == 0
        assert await db.scalar(select(func.count(InterviewTranscriptVersion.id))) == 1


@pytest.mark.asyncio
async def test_orphan_evaluation_fails_claim_without_advancing_generation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-orphan-evaluation",
                session_id="session-1",
                question_id="question-1",
                recording_type="audio",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="uploaded",
                audio_content_hash="9" * 64,
                processing_retry_limit=2,
                client_attempt_id="client-orphan-evaluation",
            )
        )
        await db.flush()
        db.add(
            InterviewAttemptEvaluation(
                id="orphan-evaluation",
                recording_id="attempt-orphan-evaluation",
                version_number=1,
                state="completed",
                evaluation_contract_version="coach_conversational_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
            )
        )

    async with repository_database.begin() as db:
        claim = await ConversationalSessionRepository(db).claim_attempt_processing(
            recording_id="attempt-orphan-evaluation",
            expected_generation=0,
            job_id="job-orphan-evaluation",
            deadline=datetime.utcnow() + timedelta(minutes=5),
        )
        assert claim is None
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-orphan-evaluation")
        assert attempt is not None
        assert attempt.processing_generation == 0
        assert attempt.attempt_state == "uploaded"
        assert await db.scalar(select(func.count(InterviewAttemptEvaluation.id))) == 1


@pytest.mark.asyncio
async def test_concurrent_candidate_transcript_allocation_uses_pointer_fence(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-concurrent-transcript",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="client-concurrent-transcript",
            )
        )

    async def create(text: str):
        async with repository_database.begin() as db:
            try:
                return await ConversationalSessionRepository(
                    db
                ).create_transcript_version(
                    recording_id="attempt-concurrent-transcript",
                    source="candidate_text",
                    transcript=text,
                    expected_attempt_version=0,
                    processing_generation=1,
                )
            except StaleVersion as error:
                return error

    results = await asyncio.gather(create("First."), create("Second."))
    assert (
        sum(isinstance(result, InterviewTranscriptVersion) for result in results) == 1
    )
    assert sum(isinstance(result, StaleVersion) for result in results) == 1
    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-concurrent-transcript")
        versions = (
            await db.scalars(
                select(InterviewTranscriptVersion).where(
                    InterviewTranscriptVersion.recording_id
                    == "attempt-concurrent-transcript"
                )
            )
        ).all()
        assert attempt is not None
        assert attempt.attempt_version == 1
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert attempt.current_transcript_version_id == versions[0].id


@pytest.mark.asyncio
async def test_processing_claim_allocates_from_current_evaluation_pointer(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id="attempt-current-evaluation",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="uploaded",
            audio_content_hash="8" * 64,
            processing_retry_limit=2,
            client_attempt_id="client-current-evaluation",
        )
        db.add(attempt)
        await db.flush()
        prior = InterviewAttemptEvaluation(
            id="current-evaluation",
            recording_id=attempt.id,
            version_number=4,
            state="completed",
            evaluation_contract_version="coach_conversational_rubric_v1",
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
        )
        db.add(prior)
        await db.flush()
        attempt.current_evaluation_version_id = prior.id

    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = "attempt-current-evaluation"
        await repository.create_evaluation_version(
            recording_id="attempt-current-evaluation",
            transcript_version_id=None,
            evaluation_version=5,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-current-evaluation",
        )
        claim = await repository.claim_attempt_processing(
            recording_id="attempt-current-evaluation",
            expected_generation=0,
            job_id="job-current-evaluation",
            deadline=datetime.utcnow() + timedelta(minutes=5),
        )
        assert claim is not None
    async with repository_database() as db:
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert evaluation is not None
        assert evaluation.version_number == 5


@pytest.mark.asyncio
async def test_create_evaluation_then_claim_processing_matches_downstream_sequence(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        db.add(
            SessionRecording(
                id="attempt-claim",
                session_id="session-1",
                question_id="question-1",
                recording_type="text",
                attempt_number=1,
                attempt_kind="primary",
                attempt_state="draft",
                processing_retry_limit=2,
                client_attempt_id="claim-client",
            )
        )
    async with repository_database.begin() as db:
        transcript = await ConversationalSessionRepository(
            db
        ).create_transcript_version(
            recording_id="attempt-claim",
            source="candidate_text",
            transcript="Claim source transcript.",
            expected_attempt_version=0,
            processing_generation=1,
        )

    deadline = datetime.utcnow() + timedelta(minutes=5)
    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = "attempt-claim"
        pending = await repository.create_evaluation_version(
            recording_id="attempt-claim",
            transcript_version_id=transcript.id,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-claim",
        )
        attempt_before_claim = await db.get(SessionRecording, "attempt-claim")
        assert attempt_before_claim is not None
        assert attempt_before_claim.current_evaluation_version_id is None
        claim = await repository.claim_attempt_processing(
            recording_id="attempt-claim",
            expected_generation=0,
            job_id="job-claim",
            deadline=deadline,
        )
        assert claim is not None
        assert claim.transcript_version_id == transcript.id
        assert claim.evaluation_version_id == pending.id

    async with repository_database() as db:
        fence = await _processing_fence(db, claim)
        attempt = await db.get(SessionRecording, "attempt-claim")
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert attempt is not None and evaluation is not None
        assert attempt.processing_generation == 1
        assert attempt.evaluation_state == "pending"
        assert evaluation.version_number == 1
        assert evaluation.state == "pending"
        assert evaluation.diagnostics_json == {
            "processing_claim": {
                "processing_generation": 1,
                "job_deadline_at": deadline.isoformat(),
                "source_audio_content_hash": None,
                "source_transcript_version_id": transcript.id,
                "expected_session_state_version": 4,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": fence.claim_token,
            }
        }
        snapshot = await ConversationalSessionRepository(
            db
        ).get_attempt_processing_snapshot(
            recording_id="attempt-claim", processing_generation=1
        )
        assert snapshot is not None
        assert snapshot.claim == claim


@pytest.mark.asyncio
async def test_concurrent_processing_claim_is_fenced_without_integrity_error(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id="attempt-concurrent-claim",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="uploaded",
            audio_content_hash="c" * 64,
            processing_retry_limit=2,
            client_attempt_id="concurrent-claim-client",
        )
        db.add(attempt)
        await db.flush()
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = attempt.id
        await ConversationalSessionRepository(db).create_evaluation_version(
            recording_id=attempt.id,
            transcript_version_id=None,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-concurrent-claim",
        )

    async def claim():
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(db).claim_attempt_processing(
                recording_id="attempt-concurrent-claim",
                expected_generation=0,
                job_id="job-concurrent-claim",
                deadline=datetime.utcnow() + timedelta(minutes=5),
            )

    claims = await asyncio.gather(claim(), claim())
    assert sum(result is not None for result in claims) == 1
    async with repository_database() as db:
        evaluations = (
            await db.scalars(
                select(InterviewAttemptEvaluation).where(
                    InterviewAttemptEvaluation.recording_id
                    == "attempt-concurrent-claim"
                )
            )
        ).all()
        assert len(evaluations) == 1
        assert evaluations[0].version_number == 1


@pytest.mark.asyncio
async def test_processing_claim_rejects_parent_outside_listening_before_mutation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id="attempt-wrong-parent-state",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="uploaded",
            audio_content_hash="b" * 64,
            processing_retry_limit=2,
            client_attempt_id="client-wrong-parent-state",
        )
        db.add(attempt)
        await db.flush()
        session = await db.get(InterviewSession, "session-1")
        assert session is not None and session.conversation_state == "asking"
        session.active_recording_id = attempt.id
        evaluation = await ConversationalSessionRepository(
            db
        ).create_evaluation_version(
            recording_id=attempt.id,
            transcript_version_id=None,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-wrong-parent-state",
        )
        evaluation_id = evaluation.id

    async with repository_database.begin() as db:
        claim = await ConversationalSessionRepository(db).claim_attempt_processing(
            recording_id="attempt-wrong-parent-state",
            expected_generation=0,
            job_id="job-wrong-parent-state",
            deadline=datetime.utcnow() + timedelta(minutes=5),
        )
        assert claim is None

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-wrong-parent-state")
        evaluation = await db.get(InterviewAttemptEvaluation, evaluation_id)
        assert attempt is not None and evaluation is not None
        assert (
            attempt.attempt_state,
            attempt.processing_generation,
            attempt.async_job_id,
        ) == ("uploaded", 0, None)
        assert evaluation.diagnostics_json == {"processing_generation": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_scope", "expected_claimed"),
    (("attempt_processing", True), ("setup", False)),
)
async def test_processing_retry_claim_requires_attempt_scoped_recoverable_parent(
    repository_database, error_scope, expected_claimed
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id=f"attempt-retry-scope-{error_scope}",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="recoverable_error",
            audio_content_hash="c" * 64,
            processing_retry_limit=2,
            client_attempt_id=f"client-retry-scope-{error_scope}",
        )
        db.add(attempt)
        await db.flush()
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "recoverable_error"
        session.recoverable_error_scope = error_scope
        session.recoverable_error_code = "coach_evaluation_unavailable"
        session.active_recording_id = attempt.id
        await ConversationalSessionRepository(db).create_evaluation_version(
            recording_id=attempt.id,
            transcript_version_id=None,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id=f"job-retry-scope-{error_scope}",
        )

    async with repository_database.begin() as db:
        claim = await ConversationalSessionRepository(db).claim_attempt_processing(
            recording_id=f"attempt-retry-scope-{error_scope}",
            expected_generation=0,
            job_id=f"job-retry-scope-{error_scope}",
            deadline=datetime.utcnow() + timedelta(minutes=5),
        )
        assert (claim is not None) is expected_claimed


@pytest.mark.asyncio
async def test_retry_claim_atomically_creates_one_fenced_generation(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    deadline = datetime.utcnow() + timedelta(minutes=15)
    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "recoverable_error"
        session.recoverable_error_scope = "attempt_processing"
        session.recoverable_error_code = "coach_evaluation_unavailable"
        attempt = SessionRecording(
            id="attempt-atomic-retry",
            session_id=session.id,
            question_id="question-1",
            recording_type="text",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="recoverable_error",
            evaluation_state="failed",
            processing_generation=4,
            processing_retry_count=0,
            processing_retry_limit=2,
            audio_retention_policy="delete_after_processing",
            audio_retention_state="not_applicable",
            client_attempt_id="client-atomic-retry",
        )
        db.add(attempt)
        await db.flush()
        transcript = InterviewTranscriptVersion(
            recording_id=attempt.id,
            version_number=1,
            transcript="An immutable typed answer.",
            source="candidate_text",
            content_hash="typed-transcript-hash",
            created_by="candidate",
            processing_generation=4,
        )
        db.add(transcript)
        await db.flush()
        attempt.current_transcript_version_id = transcript.id
        prior_deadline = datetime.utcnow() - timedelta(seconds=1)
        prior = InterviewAttemptEvaluation(
            recording_id=attempt.id,
            transcript_version_id=transcript.id,
            version_number=1,
            state="failed",
            evaluation_contract_version="coach_conversational_rubric_v1",
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
            async_job_id="prior-atomic-job",
            diagnostics_json={
                "processing_claim": {
                    "processing_generation": 4,
                    "job_deadline_at": prior_deadline.isoformat(),
                    "source_audio_content_hash": None,
                    "source_transcript_version_id": transcript.id,
                    "expected_session_state_version": session.state_version - 1,
                    "processing_contract_version": "coach_processing_v1",
                    "claim_token": "prior-atomic-token",
                },
                "result": {"reason_code": "coach_evaluation_unavailable"},
            },
        )
        db.add(prior)
        await db.flush()
        attempt.current_evaluation_version_id = prior.id
        prior_states = {
            "audio_persist": "not_applicable",
            "transcription": "not_applicable",
            "speech_analysis": "not_applicable",
            "content_evaluation": "failed_retryable",
            "evidence_grounding": "failed_retryable",
            "follow_up_decision": "failed_retryable",
            "coaching_enrichment": "failed_retryable",
            "audio_cleanup": "not_applicable",
        }
        for stage_name, stage_state in prior_states.items():
            db.add(
                InterviewAttemptStage(
                    recording_id=attempt.id,
                    evaluation_version_id=prior.id,
                    stage_name=stage_name,
                        stage_state=stage_state,
                        attempt_count=1,
                        job_id="prior-atomic-job",
                        claim_token="prior-atomic-token",
                        expected_processing_generation=4,
                    source_transcript_version_id=(
                        transcript.id
                        if stage_name
                        in {
                            "content_evaluation",
                            "evidence_grounding",
                            "follow_up_decision",
                            "coaching_enrichment",
                        }
                        else None
                        ),
                        job_deadline_at=prior_deadline,
                        completed_at=datetime.utcnow(),
                    last_error_code=(
                        "coach_evaluation_unavailable"
                            if stage_state == "failed_retryable"
                            else None
                        ),
                        diagnostics_json=_stage_immutable_diagnostics(
                            stage_name=stage_name,
                            audio_content_hash=None,
                            transcript_version_id=transcript.id,
                            transcript_content_hash=transcript.content_hash,
                            evaluation_contract_version=(
                                "coach_conversational_rubric_v1"
                            ),
                            evidence_contract_version=(
                                "coach_evidence_grounding_v1"
                            ),
                            follow_up_contract_version="coach_follow_up_v1",
                        ),
                    )
            )
        job = AsyncJob(type="coach_attempt_processing", status="pending")
        db.add(job)
        await db.flush()
        session.active_recording_id = attempt.id

    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        claim = await repository.claim_retry_processing(
            recording_id="attempt-atomic-retry",
            job_id=job.id,
            deadline=deadline,
            expected_session_state_version=4,
        )
        assert claim is not None

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-atomic-retry")
        session = await db.get(InterviewSession, "session-1")
        assert attempt is not None and session is not None
        assert (attempt.processing_generation, attempt.processing_retry_count) == (5, 1)
        assert attempt.async_job_id == job.id
        assert session.conversation_state == "processing_answer"
        evaluations = list(
            (
                await db.scalars(
                    select(InterviewAttemptEvaluation)
                    .where(InterviewAttemptEvaluation.recording_id == attempt.id)
                    .order_by(InterviewAttemptEvaluation.version_number)
                )
            ).all()
        )
        assert len(evaluations) == 2 and evaluations[-1].state == "pending"
        stages = list(
            (
                await db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.evaluation_version_id
                        == evaluations[-1].id
                    )
                )
            ).all()
        )
        assert len(stages) == 8
        assert {stage.stage_name: stage.stage_state for stage in stages} == {
            "audio_persist": "not_applicable",
            "transcription": "not_applicable",
            "speech_analysis": "not_applicable",
            "content_evaluation": "pending",
            "evidence_grounding": "pending",
            "follow_up_decision": "pending",
            "coaching_enrichment": "pending",
            "audio_cleanup": "not_applicable",
        }


@pytest.mark.asyncio
async def test_stage_counters_persist_only_under_current_processing_claim(
    repository_database,
) -> None:
    """A stale internal retry must not mutate counters or manual retry budget."""
    await _seed_session(repository_database)
    claim, _ = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-stage-counters",
        job_id="job-stage-counters",
    )

    async with repository_database.begin() as db:
        repository = ConversationalSessionRepository(db)
        fence = await _processing_fence(db, claim)
        db.add(
            AsyncJob(
                id=claim.job_id,
                type="coach_attempt_processing",
                status="running",
            )
        )
        db.add(
            InterviewAttemptStage(
                recording_id=claim.recording_id,
                evaluation_version_id=claim.evaluation_version_id,
                stage_name="content_evaluation",
                stage_state="pending",
                job_id=claim.job_id,
                claim_token=fence.claim_token,
                expected_processing_generation=claim.processing_generation,
                source_transcript_version_id=claim.transcript_version_id,
                job_deadline_at=claim.deadline_at,
            )
        )
        await db.flush()
        assert await repository.persist_attempt_stage_counters(
            claim=claim,
            stage_name="content_evaluation",
            attempt_count=1,
            repair_count=0,
        ) is True
        assert await repository.persist_attempt_stage_counters(
            claim=replace(
                claim, processing_generation=claim.processing_generation + 1
            ),
            stage_name="content_evaluation",
            attempt_count=2,
            repair_count=1,
        ) is False

    async with repository_database() as db:
        stage = await db.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.recording_id == claim.recording_id,
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id,
                InterviewAttemptStage.stage_name == "content_evaluation",
            )
        )
        attempt = await db.get(SessionRecording, claim.recording_id)
        assert stage is not None and attempt is not None
        assert (stage.attempt_count, stage.repair_count) == (1, 0)
        assert attempt.processing_retry_count == 0


@pytest.mark.asyncio
async def test_processing_finaliser_validates_parent_before_child_writes(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    claim, transcript_id = await _claim_attempt_for_finalisation(
        repository_database,
        recording_type="text",
        attempt_id="attempt-parent-prevalidation",
        job_id="job-parent-prevalidation",
    )
    assert transcript_id is not None
    async with repository_database.begin() as db:
        fence = await _processing_fence(db, claim)
        for stage_name in (
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
        ):
            db.add(
                InterviewAttemptStage(
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="completed",
                    job_id=claim.job_id,
                    claim_token=fence.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=transcript_id,
                    job_deadline_at=claim.deadline_at,
                )
            )
        session = await db.get(InterviewSession, claim.session_id)
        assert session is not None
        session.deletion_state = "deleting"

    child_updates: list[str] = []
    async_engine = repository_database.kw["bind"]

    def capture_child_update(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        normalised = " ".join(statement.lower().split())
        if normalised.startswith(
            ("update session_recordings", "update interview_attempt_evaluations")
        ):
            child_updates.append(normalised)

    event.listen(
        async_engine.sync_engine, "before_cursor_execute", capture_child_update
    )
    try:
        async with repository_database.begin() as db:
            changed = await ConversationalSessionRepository(
                db
            ).finalise_attempt_processing(
                claim=claim,
                result=AttemptProcessingResult(
                    evaluation_state="completed",
                    evaluation_json={"answer_level": "strong"},
                    transcript_version_id=transcript_id,
                    diagnostics={},
                ),
            )
    finally:
        event.remove(
            async_engine.sync_engine, "before_cursor_execute", capture_child_update
        )

    assert changed is False
    assert child_updates == []


@pytest.mark.asyncio
async def test_processing_claim_and_abandonment_race_leaves_no_live_worker_owner(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    deadline = datetime.utcnow() + timedelta(minutes=5)
    async with repository_database.begin() as db:
        attempt = SessionRecording(
            id="attempt-abandon-race",
            session_id="session-1",
            question_id="question-1",
            recording_type="audio",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="uploaded",
            audio_content_hash="a" * 64,
            processing_retry_limit=2,
            client_attempt_id="client-abandon-race",
        )
        db.add(attempt)
        await db.flush()
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        session.conversation_state = "listening"
        session.active_recording_id = attempt.id
        await ConversationalSessionRepository(db).create_evaluation_version(
            recording_id=attempt.id,
            transcript_version_id=None,
            evaluation_version=1,
            processing_generation=1,
            contract_version="coach_conversational_rubric_v1",
            state="pending",
            async_job_id="job-abandon-race",
        )

    async def claim_processing():
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(db).claim_attempt_processing(
                recording_id="attempt-abandon-race",
                expected_generation=0,
                job_id="job-abandon-race",
                deadline=deadline,
            )

    async def abandon():
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(
                db
            ).abandon_conversational_session(session_id="session-1")

    claim, abandoned = await asyncio.gather(claim_processing(), abandon())
    if not abandoned:
        abandoned = await abandon()
    assert abandoned is True

    async with repository_database() as db:
        session = await db.get(InterviewSession, "session-1")
        attempt = await db.get(SessionRecording, "attempt-abandon-race")
        assert session is not None and attempt is not None
        assert (session.status, session.conversation_state) == (
            "abandoned",
            "abandoned",
        )
        assert attempt.async_job_id is None
        if claim is not None:
            assert attempt.processing_generation > claim.processing_generation
            finalised = await ConversationalSessionRepository(
                db
            ).finalise_attempt_processing(
                claim=claim,
                result=AttemptProcessingResult(
                    evaluation_state="unavailable",
                    evaluation_json={},
                    transcript_version_id=None,
                    diagnostics={"reason_code": "transcription_unavailable"},
                ),
            )
            assert finalised is False


@pytest.mark.asyncio
async def test_setup_claim_and_abandonment_race_fences_stale_setup_worker(
    repository_database,
) -> None:
    async with repository_database.begin() as db:
        db.add(
            InterviewSession(
                id="setup-abandon-race",
                company_name="Example",
                role_title="Engineer",
                status="setup",
                experience_version="conversational_v1",
                conversation_state=None,
                state_version=0,
                setup_max_attempts=3,
                deletion_state="not_requested",
            )
        )

    async def claim_setup():
        async with repository_database.begin() as db:
            try:
                return await claim_session_setup(
                    db,
                    session_id="setup-abandon-race",
                    request=_setup_request(),
                )
            except SessionPlanError:
                return None

    async def abandon():
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(
                db
            ).abandon_conversational_session(session_id="setup-abandon-race")

    setup_claim, abandoned = await asyncio.gather(claim_setup(), abandon())
    if not abandoned:
        abandoned = await abandon()
    assert abandoned is True

    async with repository_database() as db:
        session = await db.get(InterviewSession, "setup-abandon-race")
        assert session is not None
        assert (session.status, session.conversation_state) == (
            "abandoned",
            "abandoned",
        )
        assert session.setup_job_id is session.setup_claim_token is None
        if setup_claim is not None:
            with pytest.raises(SessionPlanError):
                await load_claim_planning_request(db, claim=setup_claim)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_case",
    ("missing_pointer", "nonterminal", "mismatched_transcript", "stale_generation"),
)
async def test_acceptance_rejects_missing_stale_or_nonterminal_current_evaluation(
    repository_database, invalid_case
) -> None:
    await _seed_session(repository_database)
    transcript_id, evaluation_id = await _seed_terminal_attempt_for_acceptance(
        repository_database
    )
    async with repository_database.begin() as db:
        attempt = await db.get(SessionRecording, "attempt-accept")
        evaluation = await db.get(InterviewAttemptEvaluation, evaluation_id)
        assert attempt is not None and evaluation is not None
        if invalid_case == "missing_pointer":
            attempt.current_evaluation_version_id = None
        elif invalid_case == "nonterminal":
            evaluation.state = "pending"
        elif invalid_case == "mismatched_transcript":
            other = InterviewTranscriptVersion(
                id="other-transcript",
                recording_id="attempt-accept",
                version_number=2,
                transcript="Other transcript.",
                source="candidate_edit",
                content_hash="0" * 64,
                created_by="candidate",
                processing_generation=3,
            )
            db.add(other)
            await db.flush()
            evaluation.transcript_version_id = other.id
        else:
            evaluation.diagnostics_json = {
                "processing_claim": {"processing_generation": 2}
            }

    async with repository_database.begin() as db:
        result = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=4,
        )
        assert result.accepted is False
        assert result.current_state_version == 4
        assert result.current_state == "awaiting_next_action"
        assert result.evaluation_version_id == (
            None if invalid_case == "missing_pointer" else evaluation_id
        )
        assert result.evaluation_state == (
            "pending" if invalid_case == "nonterminal" else "completed"
        )
    async with repository_database() as db:
        question = await db.get(SessionQuestion, "question-1")
        attempt = await db.get(SessionRecording, "attempt-accept")
        assert question is not None and attempt is not None
        assert question.accepted_recording_id is None
        assert attempt.accepted_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("evaluation_state", ("completed", "unavailable"))
async def test_acceptance_selects_matching_terminal_evaluation_once(
    repository_database, evaluation_state
) -> None:
    await _seed_session(repository_database)
    _, evaluation_id = await _seed_terminal_attempt_for_acceptance(
        repository_database, evaluation_state=evaluation_state
    )
    async with repository_database.begin() as db:
        result = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=4,
        )
        assert result.accepted is True
        assert result.state_version == 5
        assert result.evaluation_version_id == evaluation_id
        assert result.evaluation_state == evaluation_state

    async with repository_database.begin() as db:
        replay = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=5,
        )
        assert replay.accepted is False
    async with repository_database() as db:
        question = await db.get(SessionQuestion, "question-1")
        attempt = await db.get(SessionRecording, "attempt-accept")
        assert question is not None and attempt is not None
        assert question.accepted_recording_id == "attempt-accept"
        assert attempt.accepted_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    (("deletion_state", "deleting"), ("status", "abandoned")),
)
async def test_acceptance_rejects_inactive_or_deleting_parent_without_mutation(
    repository_database, field: str, value: str
) -> None:
    await _seed_session(repository_database)
    await _seed_terminal_attempt_for_acceptance(repository_database)
    async with repository_database.begin() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        setattr(session, field, value)

    async with repository_database.begin() as db:
        result = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=4,
        )
        assert result.accepted is False

    async with repository_database() as db:
        question = await db.get(SessionQuestion, "question-1")
        attempt = await db.get(SessionRecording, "attempt-accept")
        assert question is not None and attempt is not None
        assert question.accepted_recording_id is None
        assert attempt.accepted_at is None


def _follow_up_claim(*, duplicate_key: str) -> FollowUpAdmissionClaim:
    return FollowUpAdmissionClaim(
        session_id="session-1",
        root_question_id="question-1",
        parent_question_id="question-1",
        source_recording_id="attempt-accept",
        source_transcript_version_id="transcript-attempt-accept",
        expected_state_version=5,
        expected_acceptance_generation=0,
        question=f"What specifically happened for {duplicate_key}?",
        reason="clarify_example",
        target_dimension="specificity",
        aggregation_role="gap_repair",
        duplicate_key=duplicate_key,
        context_json={"reason": "clarify_example"},
        generation_json={"contract_version": "coach_follow_up_v1"},
    )


@pytest.mark.asyncio
async def test_acceptance_then_follow_up_creation_matches_downstream_sequence(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    await _seed_terminal_attempt_for_acceptance(repository_database)
    async with repository_database.begin() as db:
        accepted = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=4,
        )
        assert accepted.accepted is True

    async with repository_database.begin() as db:
        result = await ConversationalSessionRepository(db).create_follow_up_question(
            claim=_follow_up_claim(duplicate_key="specific-example")
        )
        assert (result.created, result.state_version) == (True, 5)
        assert result.question_id is not None

    async with repository_database() as db:
        follow_up = await db.get(SessionQuestion, result.question_id)
        assert follow_up is not None
        assert (
            follow_up.question_kind,
            follow_up.root_question_id,
            follow_up.parent_question_id,
            follow_up.follow_up_depth,
            follow_up.follow_up_source_recording_id,
            follow_up.follow_up_source_transcript_version_id,
        ) == (
            "adaptive_follow_up",
            "question-1",
            "question-1",
            1,
            "attempt-accept",
            "transcript-attempt-accept",
        )


@pytest.mark.asyncio
async def test_two_concurrent_admissions_never_exceed_root_budget(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    await _seed_terminal_attempt_for_acceptance(repository_database)
    async with repository_database.begin() as db:
        accepted = await ConversationalSessionRepository(db).accept_attempt(
            session_id="session-1",
            question_id="question-1",
            attempt_id="attempt-accept",
            expected_state_version=4,
        )
        assert accepted.accepted is True
        db.add(
            SessionQuestion(
                id="existing-follow-up",
                session_id="session-1",
                question_num=2,
                text="Existing follow-up",
                category="behavioural",
                difficulty="medium",
                order_in_session=2,
                question_kind="adaptive_follow_up",
                root_question_id="question-1",
                parent_question_id="question-1",
                follow_up_depth=1,
                follow_up_reason="clarify_example",
                follow_up_target_dimension="specificity",
                follow_up_aggregation_role="gap_repair",
                follow_up_source_recording_id="attempt-accept",
                follow_up_source_transcript_version_id=("transcript-attempt-accept"),
                follow_up_generation_json={"duplicate_key": "existing"},
                question_state="pending",
            )
        )

    async def admit(duplicate_key: str):
        async with repository_database.begin() as db:
            return await ConversationalSessionRepository(db).create_follow_up_question(
                claim=_follow_up_claim(duplicate_key=duplicate_key)
            )

    results = await asyncio.gather(admit("dup-a"), admit("dup-b"))
    assert sum(result.created for result in results) == 1
    async with repository_database() as db:
        count = await db.scalar(
            select(func.count(SessionQuestion.id)).where(
                SessionQuestion.root_question_id == "question-1",
                SessionQuestion.question_kind == "adaptive_follow_up",
            )
        )
        assert count == 2


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("session_id", "/private/session/path"),
        ("session_id", "s" * 37),
        ("event_type", "raw_candidate_content"),
        ("actor_type", "api_key_secret"),
        ("state_before", "transcript_content"),
        ("state_after", "/private/path"),
        ("question_id", "/private/path"),
        ("question_id", "q" * 37),
        ("recording_id", "secret=value"),
        ("command_id", "api_key=secret"),
        ("command_id", "c" * 65),
        ("state_version", -1),
        ("state_version", True),
    ),
)
async def test_event_envelope_is_validated_before_sequence_allocation(
    repository_database, field, value
) -> None:
    await _seed_session(repository_database)
    event_values = {
        "event_type": "session_started",
        "actor_type": "system",
        "state_version": 4,
        "state_before": "ready",
        "state_after": "asking",
        "question_id": "question-1",
        "recording_id": "recording-1",
        "command_id": "command-1",
    }
    session_id = "session-1"
    if field == "session_id":
        session_id = value
    else:
        event_values[field] = value

    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="event envelope"):
            await ConversationalSessionRepository(db).append_session_events(
                session_id=session_id,
                events=(SessionEventInput(**event_values),),
            )

    async with repository_database() as db:
        session = await db.get(InterviewSession, "session-1")
        assert session is not None
        assert session.event_version == 0
        assert await db.scalar(select(func.count(InterviewSessionEvent.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_id", ("transcript.edit:01", "content.release:1", "api_key_secret")
)
async def test_event_envelope_accepts_schema_valid_opaque_tokens(
    repository_database, command_id
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        (event_row,) = await ConversationalSessionRepository(db).append_session_events(
            session_id="session-1",
            events=(
                SessionEventInput(
                    "session_started",
                    "system",
                    4,
                    state_before="ready",
                    state_after="asking",
                    question_id="evidence_secret",
                    recording_id="private_path",
                    command_id=command_id,
                ),
            ),
        )
        assert event_row.command_id == command_id


@pytest.mark.asyncio
async def test_event_payload_extreme_depth_returns_stable_value_error(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    payload: dict[str, object] = {"reason": "transcription_unavailable"}
    for _ in range(2_000):
        payload = {"diagnostics": payload}

    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="bounded"):
            await ConversationalSessionRepository(db).append_session_events(
                session_id="session-1",
                events=(
                    SessionEventInput(
                        "attempt_processing_failed",
                        "worker",
                        4,
                        payload_json=payload,
                    ),
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {"answer": "candidate content"},
        {"metadata": {"body": "nested candidate content"}},
        {"reason": "/home/candidate/private/cv.pdf"},
        {"error": "api_key=secret-value"},
        {"secret_id": "api_key_secret_value"},
        {"status": "This is a full transcript disguised as status"},
        {"count": 1_000_001},
        {"stage": ["safe_code", "raw content with spaces"]},
    ),
)
async def test_event_payload_rejects_non_allowlisted_or_sensitive_values(
    repository_database, payload
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="content-free"):
            await ConversationalSessionRepository(db).append_session_events(
                session_id="session-1",
                events=(
                    SessionEventInput(
                        "attempt_processing_failed",
                        "worker",
                        4,
                        payload_json=payload,
                    ),
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {
            "diagnostics": {
                "diagnostics": {
                    "diagnostics": {
                        "diagnostics": {
                            "diagnostics": {"reason": "provider_unavailable"}
                        }
                    }
                }
            }
        },
        {
            "diagnostics": {
                "hint_types": ["safe_code"] * 32,
                "stages": ["safe_code"] * 32,
                "reason_codes": ["safe_code"],
            }
        },
        {
            "attempt_id": "a" * 128,
            "claim_id": "b" * 128,
            "command_id": "c" * 128,
            "evaluation_version_id": "d" * 128,
            "job_id": "e" * 128,
            "question_id": "f" * 128,
            "recording_id": "g" * 128,
            "session_id": "h" * 128,
            "stage_id": "i" * 128,
            "transcript_version_id": "j" * 128,
        },
    ),
    ids=("deep", "wide", "oversize"),
)
async def test_event_payload_rejects_unbounded_diagnostics(
    repository_database, payload
) -> None:
    await _seed_session(repository_database)
    async with repository_database.begin() as db:
        with pytest.raises(ValueError, match="bounded"):
            await ConversationalSessionRepository(db).append_session_events(
                session_id="session-1",
                events=(
                    SessionEventInput(
                        "attempt_processing_failed",
                        "worker",
                        4,
                        payload_json=payload,
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_event_payload_accepts_bounded_content_free_diagnostics(
    repository_database,
) -> None:
    await _seed_session(repository_database)
    payload = {
        "reason_code": "transcription_unavailable",
        "stage": "transcription",
        "state": "unavailable",
        "retryable": False,
        "attempt_count": 3,
        "duration_ms": 900,
        "job_id": "job_01hx7z2p4k9m6n3q8r5s1t0v",
        "contract_version": "coach_processing_v1",
    }
    async with repository_database.begin() as db:
        (event_row,) = await ConversationalSessionRepository(db).append_session_events(
            session_id="session-1",
            events=(
                SessionEventInput(
                    "attempt_processing_failed",
                    "worker",
                    4,
                    payload_json=payload,
                ),
            ),
        )
        assert event_row.payload_json == payload
