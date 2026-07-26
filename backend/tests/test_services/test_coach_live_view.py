"""Authoritative, privacy-bounded conversational Coach live projections."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    SessionQuestion,
    SessionRecording,
)
from app.services.coach_conversation_state import allowed_commands
from app.services.coach_live_view import CoachLiveViewError, CoachLiveViewService


async def _ready_session(db_session) -> tuple[InterviewSession, SessionQuestion]:
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        experience_version="conversational_v1",
        status="setup",
        conversation_state="ready",
        state_version=4,
        activity_version=2,
        retention_version=1,
        deletion_state="not_requested",
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
        report_state="not_started",
    )
    db_session.add(session)
    await db_session.flush()
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="pending",
        attempts_created_count=0,
    )
    db_session.add(question)
    await db_session.commit()
    return session, question


@pytest.mark.asyncio
async def test_live_reconciles_then_reloads_and_projects_registry_commands(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "advancing"
    question.question_num = 2
    question.order_in_session = 2
    prior = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="First question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    db_session.add(prior)
    await db_session.flush()
    accepted = SessionRecording(
        session_id=session.id,
        question_id=prior.id,
        recording_type="text",
        transcript="accepted answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        accepted_at=datetime.utcnow(),
    )
    db_session.add(accepted)
    await db_session.flush()
    prior.accepted_recording_id = accepted.id
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert view.conversation_state == "asking"
    assert view.active_question is not None
    assert view.active_question.id == question.id
    assert view.allowed_commands == list(
        allowed_commands(state="asking", status="active")
    )
    assert view.contract_version == "coach_live_view_v1"


@pytest.mark.asyncio
async def test_live_projection_exposes_no_error_context_or_planning_content(
    db_session,
) -> None:
    session, _ = await _ready_session(db_session)
    session.conversation_state = "recoverable_error"
    session.recoverable_error_scope = "setup"
    session.recoverable_error_code = "coach_setup_claim_expired"
    session.recoverable_error_context_json = {
        "transcript": "private answer",
        "prompt": "private prompt",
    }
    session.planning_request_json = {"cv_text": "private CV"}
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )
    serialized = json.dumps(view.model_dump(mode="json"))

    assert view.recoverable_error is not None
    assert view.recoverable_error.code == "coach_setup_claim_expired"
    assert view.recoverable_error.details.model_dump() == {}
    assert "private answer" not in serialized
    assert "private prompt" not in serialized
    assert "private CV" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ["other", "", "LOCAL"])
async def test_live_rejects_unowned_session(db_session, user_id: str) -> None:
    session, _ = await _ready_session(db_session)

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id=user_id, session_id=session.id
        )

    assert raised.value.code == "coach_conversation_invalid_state"


@pytest.mark.asyncio
async def test_live_rejects_legacy_and_deleting_sessions(db_session) -> None:
    legacy = InterviewSession(
        company_name="Legacy",
        role_title="Engineer",
        config={},
        experience_version="legacy_v1",
        status="active",
    )
    db_session.add(legacy)
    deleting, _ = await _ready_session(db_session)
    deleting.deletion_state = "deleting"
    await db_session.commit()

    service = CoachLiveViewService(db_session)
    for session_id in (legacy.id, deleting.id):
        with pytest.raises(CoachLiveViewError) as raised:
            await service.get_live_view(user_id="local", session_id=session_id)
        assert raised.value.code == "coach_conversation_invalid_state"


@pytest.mark.asyncio
async def test_live_fails_closed_on_invalid_persisted_state(db_session) -> None:
    session, _ = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "listening"
    session.active_question_id = None
    session.active_recording_id = None
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )

    assert raised.value.code == "coach_conversation_invalid_state"


@pytest.mark.asyncio
async def test_live_maps_malformed_persisted_projection_to_safe_error(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.category = "private-invalid-category"
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )

    assert raised.value.code == "coach_conversation_invalid_state"
    assert "private-invalid-category" not in str(raised.value)


@pytest.mark.asyncio
async def test_live_does_not_reconcile_non_stale_processing_claim(db_session) -> None:
    session, question = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "processing_answer"
    session.active_question_id = question.id
    # This intentionally lacks an active recording, so invariant verification proves
    # reconciliation did not turn a live claim into a different state.
    session.last_activity_at = datetime.utcnow() + timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(CoachLiveViewError):
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )
    await db_session.refresh(session)
    assert session.conversation_state == "processing_answer"


@pytest.mark.asyncio
async def test_live_rejects_asking_with_submitted_attempt_still_processing(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "asking"
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.question_state = "asked"
    db_session.add(
        SessionRecording(
            session_id=session.id,
            question_id=question.id,
            recording_type="text",
            attempt_number=1,
            attempt_kind="primary",
            attempt_state="pending_processing",
            evaluation_state="pending",
            processing_generation=1,
            processing_retry_count=0,
            processing_retry_limit=2,
            async_job_id="processing-job",
        )
    )
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )

    assert raised.value.code == "coach_conversation_invalid_state"


@pytest.mark.asyncio
async def test_processing_projection_prefers_current_running_stage(db_session) -> None:
    session, question = await _ready_session(db_session)
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        async_job_id="job-1",
    )
    db_session.add(attempt)
    await db_session.flush()
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        version_number=1,
        state="pending",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id="job-1",
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    db_session.add_all(
        (
            InterviewAttemptStage(
                recording_id=attempt.id,
                evaluation_version_id=evaluation.id,
                stage_name="transcription",
                stage_state="completed",
                attempt_count=1,
                repair_count=0,
                started_at=datetime.utcnow(),
            ),
            InterviewAttemptStage(
                recording_id=attempt.id,
                evaluation_version_id=evaluation.id,
                stage_name="content_evaluation",
                stage_state="running",
                attempt_count=1,
                repair_count=0,
                job_id="job-1",
                started_at=datetime.utcnow() - timedelta(seconds=1),
            ),
        )
    )
    await db_session.commit()

    projection = await CoachLiveViewService(db_session)._project_processing(attempt)

    assert projection.stage == "content_evaluation"
    assert projection.state == "running"
