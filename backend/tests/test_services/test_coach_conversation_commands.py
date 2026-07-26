"""Command-level contracts for the conversational Coach foundation."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
    SessionRecording,
)
from app.models.async_job import AsyncJob
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import (
    ConversationCommandError,
    ConversationCommandService,
)


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
    assert session.activity_version == 0


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
