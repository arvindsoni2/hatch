"""Authoritative, privacy-bounded conversational Coach live projections."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.async_job import AsyncJob
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewTranscriptVersion,
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


async def _committed_pending_claim_with_terminal_pointer(db_session):
    """Persist the post-claim/pre-finalisation shape required by V6 section 16.3."""
    session, question = await _ready_session(db_session)
    now = datetime.utcnow()
    session.status = "active"
    session.conversation_state = "processing_answer"
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.question_state = "asked"
    question.asked_sequence = 1
    job = AsyncJob(type="coach_attempt_processing", status="running")
    db_session.add(job)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="bounded",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=2,
        processing_retry_count=0,
        processing_retry_limit=2,
        async_job_id=job.id,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(attempt)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=attempt.id,
        version_number=1,
        transcript="bounded",
        source="candidate_text",
        created_by="candidate",
        processing_generation=2,
    )
    db_session.add(transcript)
    await db_session.flush()
    attempt.current_transcript_version_id = transcript.id
    prior = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=1,
        state="unavailable",
        evaluation_contract_version="coach_conversational_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
    )
    pending = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=2,
        state="pending",
        evaluation_contract_version="coach_conversational_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=job.id,
    )
    db_session.add_all((prior, pending))
    await db_session.flush()
    attempt.current_evaluation_version_id = prior.id
    session.active_recording_id = attempt.id
    deadline = now + timedelta(minutes=5)
    claim_token = "committed-pending-token"
    pending.diagnostics_json = {
        "processing_claim": {
            "processing_generation": 2,
            "job_deadline_at": deadline.isoformat(),
            "source_audio_content_hash": None,
            "source_transcript_version_id": transcript.id,
            "expected_session_state_version": session.state_version - 1,
            "processing_contract_version": "coach_processing_v1",
            "claim_token": claim_token,
        }
    }
    db_session.add(
        InterviewAttemptStage(
            recording_id=attempt.id,
            evaluation_version_id=pending.id,
            stage_name="content_evaluation",
            stage_state="running",
            attempt_count=1,
            repair_count=0,
            job_id=job.id,
            claim_token=claim_token,
            expected_processing_generation=2,
            source_transcript_version_id=transcript.id,
            job_deadline_at=deadline,
        )
    )
    await db_session.commit()
    return session, attempt, prior, pending


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
async def test_live_reads_exact_committed_pending_claim_without_switching_terminal_pointer(
    db_session,
) -> None:
    """Using only current_evaluation_version_id makes a valid live claim unreadable."""
    (
        session,
        attempt,
        prior,
        pending,
    ) = await _committed_pending_claim_with_terminal_pointer(db_session)
    prior_id = prior.id
    pending_id = pending.id

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    await db_session.refresh(attempt)
    persisted_pending = await db_session.get(InterviewAttemptEvaluation, pending_id)
    assert attempt.current_evaluation_version_id == prior_id
    assert persisted_pending is not None and persisted_pending.state == "pending"
    assert view.conversation_state == "processing_answer"
    assert view.processing.job_id == attempt.async_job_id
    assert (view.processing.stage, view.processing.state) == (
        "content_evaluation",
        "running",
    )


@pytest.mark.asyncio
async def test_live_processing_rejects_stale_stage_transcript_ownership(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    now = datetime.utcnow()
    session.status = "active"
    session.conversation_state = "processing_answer"
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.question_state = "asked"
    job = AsyncJob(type="coach_attempt_processing", status="running")
    db_session.add(job)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="bounded",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        async_job_id=job.id,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(attempt)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=attempt.id,
        version_number=1,
        transcript="bounded",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(transcript)
    await db_session.flush()
    attempt.current_transcript_version_id = transcript.id
    deadline = now + timedelta(minutes=5)
    claim_token = "live-exact-token"
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=1,
        state="pending",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=job.id,
        diagnostics_json={
            "processing_claim": {
                "processing_generation": 1,
                "job_deadline_at": deadline.isoformat(),
                "source_audio_content_hash": None,
                "source_transcript_version_id": transcript.id,
                "expected_session_state_version": session.state_version - 1,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": claim_token,
            }
        },
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    session.active_recording_id = attempt.id
    db_session.add(
        InterviewAttemptStage(
            recording_id=attempt.id,
            evaluation_version_id=evaluation.id,
            stage_name="content_evaluation",
            stage_state="running",
            attempt_count=1,
            repair_count=0,
            job_id=job.id,
            claim_token=claim_token,
            expected_processing_generation=1,
            source_transcript_version_id="stale-private-transcript",
            job_deadline_at=deadline,
        )
    )
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )
    assert raised.value.code == "coach_conversation_invalid_state"
    assert "stale-private-transcript" not in str(raised.value)


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
    _, attempt, _, pending = await _committed_pending_claim_with_terminal_pointer(
        db_session
    )
    running_stage = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == pending.id,
            InterviewAttemptStage.stage_name == "content_evaluation",
        )
    )
    assert running_stage is not None
    db_session.add(
        InterviewAttemptStage(
            recording_id=attempt.id,
            evaluation_version_id=pending.id,
            stage_name="transcription",
            stage_state="completed",
            attempt_count=1,
            repair_count=0,
            job_id=attempt.async_job_id,
            claim_token=running_stage.claim_token,
            expected_processing_generation=attempt.processing_generation,
            source_transcript_version_id=None,
            job_deadline_at=running_stage.job_deadline_at,
            started_at=datetime.utcnow(),
        )
    )
    await db_session.commit()

    projection = await CoachLiveViewService(db_session)._project_processing(attempt)

    assert projection.stage == "content_evaluation"
    assert projection.state == "running"


@pytest.mark.asyncio
async def test_live_contextual_commands_hide_ineligible_review_actions(
    db_session,
) -> None:
    """A coarse review state must not advertise retry/accept after acceptance."""
    session, question = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "awaiting_next_action"
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.question_state = "answered"
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_limit=2,
        accepted_at=datetime.utcnow(),
    )
    db_session.add(attempt)
    await db_session.flush()
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        version_number=1,
        state="completed",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    question.accepted_recording_id = attempt.id
    question.last_accepted_generation = question.acceptance_generation
    session.active_recording_id = attempt.id
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert "retry_answer" not in view.allowed_commands
    assert "accept_attempt" not in view.allowed_commands


@pytest.mark.asyncio
async def test_live_contextual_commands_are_scope_and_report_compatible(
    db_session,
) -> None:
    """Recoverable and completed projections expose only matching recovery work."""
    session, _ = await _ready_session(db_session)
    session.status = "completed"
    session.conversation_state = "completed"
    session.report_state = "failed"
    session.report_build_reason = "initial_completion"
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )
    assert "retry_report" not in view.allowed_commands

    session.status = "active"
    session.conversation_state = "recoverable_error"
    session.report_state = "not_started"
    session.report_build_reason = None
    session.recoverable_error_scope = "initial_report"
    session.recoverable_error_code = "coach_report_conversational_snapshot_stale"
    await db_session.commit()
    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )
    assert "retry_report" in view.allowed_commands
    assert "retry_processing" not in view.allowed_commands
    assert "retry_answer" not in view.allowed_commands
    assert "end_session" not in view.allowed_commands


@pytest.mark.asyncio
async def test_active_review_ignores_transcripts_from_other_questions(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    session.status = "active"
    session.conversation_state = "awaiting_next_action"
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    question.question_state = "asked"
    active = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="unavailable",
        evaluation_state="unavailable",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(active)
    await db_session.flush()
    active_evaluation = InterviewAttemptEvaluation(
        recording_id=active.id,
        version_number=1,
        state="unavailable",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
    )
    db_session.add(active_evaluation)
    await db_session.flush()
    active.current_evaluation_version_id = active_evaluation.id
    session.active_recording_id = active.id
    historical_question = SessionQuestion(
        session_id=session.id,
        question_num=2,
        text="Historical question",
        category="technical",
        difficulty="realistic",
        order_in_session=2,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    db_session.add(historical_question)
    await db_session.flush()
    historical = SessionRecording(
        session_id=session.id,
        question_id=historical_question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(historical)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=historical.id,
        version_number=1,
        transcript="historical private transcript",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(transcript)
    await db_session.flush()
    historical.current_transcript_version_id = transcript.id
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert "edit_transcript" not in view.allowed_commands
    assert "delete_transcript" not in view.allowed_commands


@pytest.mark.asyncio
async def test_completed_session_allows_session_wide_transcript_deletion(
    db_session,
) -> None:
    session, question = await _ready_session(db_session)
    session.status = "completed"
    session.conversation_state = "completed"
    session.report_state = "fallback"
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(attempt)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=attempt.id,
        version_number=1,
        transcript="privacy deletion target",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(transcript)
    await db_session.flush()
    attempt.current_transcript_version_id = transcript.id
    await db_session.commit()

    view = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=session.id
    )

    assert "delete_transcript" in view.allowed_commands
    assert "edit_transcript" not in view.allowed_commands


@pytest.mark.asyncio
async def test_live_rejects_question_overflow_before_materializing_projection(
    db_session,
) -> None:
    session, _ = await _ready_session(db_session)
    db_session.add_all(
        SessionQuestion(
            session_id=session.id,
            question_num=index,
            text="bounded",
            category="technical",
            difficulty="realistic",
            order_in_session=index,
            question_kind="planned",
            question_state="pending",
        )
        for index in range(2, 38)
    )
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )
    assert raised.value.code == "coach_conversation_invalid_state"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("retention_policy_json", ["private-retention-canary"]),
        ("recoverable_error_context_json", ["private-error-canary"]),
    ],
)
async def test_live_malformed_json_containers_fail_closed_without_leakage(
    db_session, field: str, malformed: list[str]
) -> None:
    session, _ = await _ready_session(db_session)
    setattr(session, field, malformed)
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )
    assert raised.value.code == "coach_conversation_invalid_state"
    assert "private" not in str(raised.value)


@pytest.mark.asyncio
async def test_live_rejects_deep_diagnostic_json_without_recursion_failure(
    db_session,
) -> None:
    session, _ = await _ready_session(db_session)
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(20):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    session.recoverable_error_context_json = nested
    await db_session.commit()

    with pytest.raises(CoachLiveViewError) as raised:
        await CoachLiveViewService(db_session).get_live_view(
            user_id="local", session_id=session.id
        )
    assert raised.value.code == "coach_conversation_invalid_state"
