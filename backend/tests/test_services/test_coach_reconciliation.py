"""Recovery and report-claim tests for Coach C1."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.async_job import AsyncJob
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from app.repositories.conversational_session_repository import (
    _stage_immutable_diagnostics,
)
from app.repositories.session_repository import SessionRepository
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import ConversationCommandService
from app.services.coach_command_projection import contextual_allowed_commands
from app.services.coach_conversational_contracts import RUBRIC_CONTRACT
from app.services.coach_reconciliation import (
    reconcile_conversational_session,
    reconcile_job,
    reconcile_session,
    reconcile_stale_coach_state,
)
from app.services.coach_service import CoachService


async def _session_with_question(db_session):
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        status="active",
        report_state="not_started",
        activity_version=0,
    )
    db_session.add(session)
    await db_session.flush()
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="Technical",
        difficulty="realistic",
        order_in_session=1,
    )
    db_session.add(question)
    await db_session.flush()
    return session, question


async def _conversational_session(db_session, *, state: str, status: str = "active"):
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        experience_version="conversational_v1",
        status=status,
        conversation_state=state,
        state_version=3,
        activity_version=1,
        deletion_state="not_requested",
        report_state="not_started",
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
    )
    db_session.add(session)
    await db_session.flush()
    return session


async def _event_count(db_session, session_id: str, event_type: str) -> int:
    rows = await db_session.scalars(
        select(InterviewSessionEvent.id).where(
            InterviewSessionEvent.session_id == session_id,
            InterviewSessionEvent.event_type == event_type,
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_expired_setup_claim_is_fenced_once_without_spending_retry(
    db_session,
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 7
    session.setup_attempt_count = 2
    session.setup_max_attempts = 3
    session.setup_job_id = job.id
    session.setup_claim_token = "setup-token"
    session.setup_claimed_at = now - timedelta(minutes=2)
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    await db_session.refresh(job)

    assert (session.status, session.conversation_state) == (
        "setup",
        "recoverable_error",
    )
    assert session.recoverable_error_code == "coach_setup_claim_expired"
    assert session.recoverable_error_scope == "setup"
    assert session.setup_job_id is None
    assert session.setup_claim_token is None
    assert session.setup_attempt_count == 2
    assert session.setup_generation == 7
    assert job.status == "failed"
    assert job.error == "coach_setup_claim_expired"
    assert job.result_json is None
    assert await _event_count(db_session, session.id, "session_plan_claim_expired") == 1


@pytest.mark.asyncio
async def test_expired_setup_claim_at_budget_becomes_terminal_failed(
    db_session,
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="pending")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 2
    session.setup_attempt_count = 3
    session.setup_max_attempts = 3
    session.setup_job_id = job.id
    session.setup_claim_token = "terminal-token"
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    await db_session.refresh(session)

    assert (session.status, session.conversation_state) == ("failed", "failed")
    assert session.setup_attempt_count == 3


@pytest.mark.asyncio
async def test_unexpired_or_superseded_setup_claim_is_noop(db_session) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 4
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "newer-token"
    session.setup_claim_expires_at = now + timedelta(minutes=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "planning"
    assert session.setup_generation == 4
    assert await _event_count(db_session, session.id, "session_plan_claim_expired") == 0


async def _processing_claim(
    db_session, *, deadline: datetime, retries: int, limit: int
):
    session = await _conversational_session(db_session, state="processing_answer")
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="asked",
        asked_sequence=1,
    )
    db_session.add(question)
    await db_session.flush()
    job = AsyncJob(type="coach_attempt_processing", status="running")
    db_session.add(job)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="bounded answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=2,
        processing_retry_count=retries,
        processing_retry_limit=limit,
        async_job_id=job.id,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(attempt)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=attempt.id,
        version_number=1,
        transcript="bounded answer",
        source="candidate_text",
        created_by="candidate",
        processing_generation=2,
    )
    db_session.add(transcript)
    await db_session.flush()
    attempt.current_transcript_version_id = transcript.id
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=1,
        state="pending",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=job.id,
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    claim_token = "stage-token"
    evaluation.diagnostics_json = {
        "processing_claim": {
            "processing_generation": 2,
            "job_deadline_at": deadline.isoformat(),
            "source_audio_content_hash": None,
            "source_transcript_version_id": transcript.id,
            "expected_session_state_version": session.state_version,
            "processing_contract_version": "coach_processing_v1",
            "claim_token": claim_token,
        }
    }
    stage = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=evaluation.id,
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
    db_session.add(stage)
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    session.active_recording_id = attempt.id
    await db_session.commit()
    return session, question, attempt, evaluation, stage, job


async def _preserve_terminal_evaluation_pointer(
    db_session,
    *,
    attempt: SessionRecording,
    pending: InterviewAttemptEvaluation,
) -> InterviewAttemptEvaluation:
    """Model a committed new claim whose previous terminal version stays current."""
    pending.version_number = 2
    prior = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=attempt.current_transcript_version_id,
        version_number=1,
        state="unavailable",
        evaluation_contract_version=pending.evaluation_contract_version,
        evidence_contract_version=pending.evidence_contract_version,
        follow_up_contract_version=pending.follow_up_contract_version,
    )
    db_session.add(prior)
    await db_session.flush()
    attempt.current_evaluation_version_id = prior.id
    await db_session.commit()
    return prior


async def _configure_downstream_processing_failure(
    db_session,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    content_stage: InterviewAttemptStage,
    job: AsyncJob,
    stage_name: str,
    stage_state: str,
) -> InterviewAttemptStage:
    """Persist content success followed by one owned downstream failure."""
    rubric = {
        "answer_level": "interview_ready",
        "contract_version": RUBRIC_CONTRACT,
    }
    evaluation.rubric_json = rubric
    content_stage.stage_state = "completed"
    content_stage.completed_at = datetime.utcnow()
    ordered_downstream = (
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    )
    target: InterviewAttemptStage | None = None
    target_seen = False
    for name in ordered_downstream:
        if name == stage_name:
            target_seen = True
        persisted_state = (
            stage_state
            if name == stage_name
            else "pending"
            if target_seen
            else "completed"
        )
        row = InterviewAttemptStage(
            recording_id=attempt.id,
            evaluation_version_id=evaluation.id,
            stage_name=name,
            stage_state=persisted_state,
            attempt_count=1,
            repair_count=0,
            job_id=content_stage.job_id,
            claim_token=content_stage.claim_token,
            expected_processing_generation=content_stage.expected_processing_generation,
            source_transcript_version_id=evaluation.transcript_version_id,
            job_deadline_at=content_stage.job_deadline_at,
            completed_at=(
                datetime.utcnow()
                if persisted_state in {"completed", "failed_terminal"}
                else None
            ),
            last_error_code=(
                "coach_attempt_job_budget_exhausted"
                if name == stage_name and stage_state != "running"
                else None
            ),
        )
        db_session.add(row)
        if name == stage_name:
            target = row
    assert target is not None
    job.status = "failed"
    job.error = "coach_attempt_job_budget_exhausted"
    await db_session.commit()
    return target


def _finish_answer_command(
    *, attempt_id: str, version: int
) -> ConversationCommandRequest:
    return ConversationCommandRequest.model_validate(
        {
            "command_id": "finish-answer-reconciliation",
            "command_type": "finish_answer",
            "expected_state_version": version,
            "payload": {
                "attempt_id": attempt_id,
                "transcript": "A bounded answer from the real command flow.",
            },
            "contract_version": "coach_conversation_command_v1",
        }
    )


async def _add_accepted_question(db_session, session, now: datetime) -> None:
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Accepted question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    db_session.add(question)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="accepted answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        accepted_at=now,
    )
    db_session.add(attempt)
    await db_session.flush()
    question.accepted_recording_id = attempt.id
    session.active_question_id = question.id
    session.active_root_question_id = question.id


@pytest.mark.asyncio
async def test_processing_claim_within_deadline_is_noop(db_session) -> None:
    now = datetime.utcnow()
    session, _, attempt, _, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(attempt)
    await db_session.refresh(stage)
    await db_session.refresh(job)
    assert attempt.attempt_state == "pending_processing"
    assert stage.stage_state == "running"
    assert job.status == "running"


@pytest.mark.asyncio
async def test_real_finish_answer_terminal_claim_reconciles_after_state_increment(
    db_session,
) -> None:
    session = await _conversational_session(db_session, state="asking")
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="asked",
        asked_sequence=1,
        attempts_created_count=0,
    )
    db_session.add(question)
    await db_session.flush()
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    await db_session.commit()
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=ConversationCommandRequest.model_validate(
            {
                "command_id": "begin-answer-reconciliation",
                "command_type": "begin_answer",
                "expected_state_version": session.state_version,
                "payload": {
                    "recording_type": "text",
                    "client_attempt_id": "real-finish-answer",
                },
                "contract_version": "coach_conversation_command_v1",
            }
        ),
    )
    assert begun.active_attempt_id is not None
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    result = await service.execute(
        user_id="local",
        session_id=session.id,
        request=_finish_answer_command(
            attempt_id=attempt.id, version=begun.state_version
        ),
    )
    await db_session.refresh(session)
    evaluation = await db_session.get(
        InterviewAttemptEvaluation, attempt.current_evaluation_version_id
    )
    assert evaluation is not None
    claim = evaluation.diagnostics_json["processing_claim"]
    assert claim["expected_session_state_version"] + 2 == session.state_version
    assert result.state == session.conversation_state == "awaiting_next_action"
    session.conversation_state = "processing_answer"
    session.state_version = claim["expected_session_state_version"] + 1
    session.activity_version -= 1
    await db_session.execute(
        delete(InterviewSessionEvent).where(
            InterviewSessionEvent.session_id == session.id,
            InterviewSessionEvent.event_type == "attempt_processing_failed",
        )
    )
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id) == 1
    assert await reconcile_conversational_session(db_session, session.id) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "awaiting_next_action"
    assert await _event_count(db_session, session.id, "attempt_processing_failed") == 1


@pytest.mark.asyncio
async def test_expired_processing_claim_becomes_recoverable_without_retry_spend(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, evaluation, stage, job):
        await db_session.refresh(row)

    assert session.conversation_state == "recoverable_error"
    assert session.recoverable_error_scope == "attempt_processing"
    assert session.recoverable_error_code == "coach_attempt_job_budget_exhausted"
    assert attempt.attempt_state == "recoverable_error"
    assert attempt.processing_retry_count == 1
    assert attempt.async_job_id is None
    assert evaluation.state == "failed"
    assert stage.stage_state == "failed_retryable"
    assert job.status == "failed"
    assert job.result_json is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reconcile_mode", ("targeted", "startup"))
@pytest.mark.parametrize(
    "lineage_corruption",
    (
        None,
        "token",
        "source_transcript",
        "contract",
        "downstream_link",
        "nonreused_link",
    ),
)
async def test_expired_audio_retry_with_reused_transcription_reconciles_once(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    reconcile_mode: str,
    lineage_corruption: str | None,
) -> None:
    """A retry may bind an earlier immutable transcript only through reuse provenance."""
    now = datetime.utcnow()
    session, _, attempt, evaluation, content, job = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )
    transcript_id = attempt.current_transcript_version_id
    assert transcript_id is not None
    transcript = await db_session.get(InterviewTranscriptVersion, transcript_id)
    assert transcript is not None
    attempt.processing_generation = 3
    content.expected_processing_generation = 3
    transcript.processing_generation = 1
    evaluation.version_number = 3
    attempt.recording_type = "audio"
    attempt.audio_content_hash = "b" * 64
    retry_claim = dict(evaluation.diagnostics_json["processing_claim"])
    retry_claim["source_audio_content_hash"] = attempt.audio_content_hash
    retry_claim["source_transcript_version_id"] = transcript_id
    retry_claim["processing_generation"] = 3
    evaluation.diagnostics_json = {"processing_claim": retry_claim}
    prior_deadline = now - timedelta(minutes=1)
    prior_job = AsyncJob(type="coach_attempt_processing", status="failed")
    db_session.add(prior_job)
    await db_session.flush()
    prior_evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript_id,
        version_number=1,
        state="failed",
        evaluation_contract_version=evaluation.evaluation_contract_version,
        evidence_contract_version=evaluation.evidence_contract_version,
        follow_up_contract_version=evaluation.follow_up_contract_version,
        async_job_id=prior_job.id,
        diagnostics_json={
            "processing_claim": {
                "processing_generation": 1,
                "job_deadline_at": prior_deadline.isoformat(),
                "source_audio_content_hash": attempt.audio_content_hash,
                "source_transcript_version_id": None,
                "expected_session_state_version": session.state_version - 1,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": "prior-audio-retry-token",
            },
            "result": {"reason_code": "transcription_unavailable"},
        },
    )
    db_session.add(prior_evaluation)
    await db_session.flush()
    prior_transcription = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=prior_evaluation.id,
        stage_name="transcription",
        stage_state="completed",
        attempt_count=1,
        job_id=prior_job.id,
        claim_token="prior-audio-retry-token",
        expected_processing_generation=1,
        job_deadline_at=prior_deadline,
        completed_at=now - timedelta(minutes=1),
        diagnostics_json=_stage_immutable_diagnostics(
            stage_name="transcription",
            audio_content_hash=attempt.audio_content_hash,
            transcript_version_id=transcript_id,
            transcript_content_hash=transcript.content_hash,
            evaluation_contract_version=evaluation.evaluation_contract_version,
            evidence_contract_version=evaluation.evidence_contract_version,
            follow_up_contract_version=evaluation.follow_up_contract_version,
        ),
    )
    db_session.add(prior_transcription)
    await db_session.flush()
    prior_content = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=prior_evaluation.id,
        stage_name="content_evaluation",
        stage_state="completed",
        attempt_count=1,
        job_id=prior_job.id,
        claim_token="prior-audio-retry-token",
        expected_processing_generation=1,
        source_transcript_version_id=transcript_id,
        job_deadline_at=prior_deadline,
        completed_at=prior_deadline,
        diagnostics_json=_stage_immutable_diagnostics(
            stage_name="content_evaluation",
            audio_content_hash=attempt.audio_content_hash,
            transcript_version_id=transcript_id,
            transcript_content_hash=transcript.content_hash,
            evaluation_contract_version=evaluation.evaluation_contract_version,
            evidence_contract_version=evaluation.evidence_contract_version,
            follow_up_contract_version=evaluation.follow_up_contract_version,
        ),
    )
    db_session.add(prior_content)
    await db_session.flush()
    middle_deadline = now - timedelta(seconds=30)
    middle_job = AsyncJob(type="coach_attempt_processing", status="failed")
    db_session.add(middle_job)
    await db_session.flush()
    middle_evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript_id,
        version_number=2,
        state="failed",
        evaluation_contract_version=evaluation.evaluation_contract_version,
        evidence_contract_version=evaluation.evidence_contract_version,
        follow_up_contract_version=evaluation.follow_up_contract_version,
        async_job_id=middle_job.id,
        diagnostics_json={
            "processing_claim": {
                "processing_generation": 2,
                "job_deadline_at": middle_deadline.isoformat(),
                "source_audio_content_hash": attempt.audio_content_hash,
                "source_transcript_version_id": transcript_id,
                "expected_session_state_version": session.state_version - 1,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": "middle-audio-retry-token",
            }
        },
    )
    db_session.add(middle_evaluation)
    await db_session.flush()
    middle_transcription = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=middle_evaluation.id,
        stage_name="transcription",
        stage_state="reused",
        attempt_count=0,
        job_id=middle_job.id,
        claim_token="middle-audio-retry-token",
        expected_processing_generation=2,
        reused_from_stage_id=prior_transcription.id,
        job_deadline_at=middle_deadline,
        completed_at=middle_deadline,
        diagnostics_json=prior_transcription.diagnostics_json,
    )
    db_session.add(middle_transcription)
    await db_session.flush()
    middle_content = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=middle_evaluation.id,
        stage_name="content_evaluation",
        stage_state="reused",
        attempt_count=0,
        job_id=middle_job.id,
        claim_token="middle-audio-retry-token",
        expected_processing_generation=2,
        source_transcript_version_id=transcript_id,
        reused_from_stage_id=prior_content.id,
        job_deadline_at=middle_deadline,
        completed_at=middle_deadline,
        diagnostics_json=prior_content.diagnostics_json,
    )
    db_session.add(middle_content)
    await db_session.flush()
    if lineage_corruption == "token":
        middle_transcription.claim_token = "forged-middle-token"
    elif lineage_corruption == "source_transcript":
        forged_claim = dict(middle_evaluation.diagnostics_json["processing_claim"])
        forged_claim["source_transcript_version_id"] = None
        middle_evaluation.diagnostics_json = {"processing_claim": forged_claim}
    elif lineage_corruption == "contract":
        middle_evaluation.evaluation_contract_version = "forged-contract"
    reused_transcription = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=evaluation.id,
        stage_name="transcription",
        stage_state="reused",
        attempt_count=0,
        job_id=job.id,
        claim_token=content.claim_token,
        expected_processing_generation=attempt.processing_generation,
        source_transcript_version_id=None,
        reused_from_stage_id=middle_transcription.id,
        job_deadline_at=content.job_deadline_at,
        completed_at=now - timedelta(seconds=2),
        diagnostics_json=prior_transcription.diagnostics_json,
    )
    db_session.add(reused_transcription)
    content.stage_state = "reused"
    content.reused_from_stage_id = middle_content.id
    content.completed_at = now - timedelta(seconds=2)
    content.diagnostics_json = prior_content.diagnostics_json
    evidence = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=evaluation.id,
        stage_name="evidence_grounding",
        stage_state="running",
        attempt_count=1,
        job_id=job.id,
        claim_token=content.claim_token,
        expected_processing_generation=attempt.processing_generation,
        source_transcript_version_id=transcript_id,
        job_deadline_at=content.job_deadline_at,
        diagnostics_json=_stage_immutable_diagnostics(
            stage_name="evidence_grounding",
            audio_content_hash=attempt.audio_content_hash,
            transcript_version_id=transcript_id,
            transcript_content_hash=transcript.content_hash,
            evaluation_contract_version=evaluation.evaluation_contract_version,
            evidence_contract_version=evaluation.evidence_contract_version,
            follow_up_contract_version=evaluation.follow_up_contract_version,
        ),
    )
    db_session.add(evidence)
    if lineage_corruption == "downstream_link":
        content.reused_from_stage_id = prior_content.id
    elif lineage_corruption == "nonreused_link":
        evidence.reused_from_stage_id = middle_content.id
    await db_session.commit()

    if lineage_corruption is not None:
        if reconcile_mode == "startup":
            factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
            monkeypatch.setattr(
                "app.services.coach_reconciliation.AsyncSessionLocal", factory
            )
            assert await reconcile_stale_coach_state(batch_size=1) == 0
        else:
            assert await reconcile_conversational_session(
                db_session, session.id, now
            ) == 0
        return

    if reconcile_mode == "startup":
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        monkeypatch.setattr(
            "app.services.coach_reconciliation.AsyncSessionLocal", factory
        )
        assert await reconcile_stale_coach_state(batch_size=1) == 1
        assert await reconcile_stale_coach_state(batch_size=1) == 0
        db_session.expire_all()
    else:
        assert await reconcile_conversational_session(db_session, session.id, now) == 1
        assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, evaluation, content, evidence, job):
        await db_session.refresh(row)
    assert session.conversation_state == "recoverable_error"
    assert attempt.attempt_state == "recoverable_error"
    assert attempt.processing_retry_count == 1
    assert evaluation.state == "failed"
    assert content.stage_state == "reused"
    assert evidence.stage_state == "failed_retryable"
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_lazy_expiry_resolves_owned_pending_evaluation_not_terminal_pointer(
    db_session,
) -> None:
    """Targeted recovery must discover a committed pending claim by ownership."""
    now = datetime.utcnow()
    session, _, attempt, pending, stage, job = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )
    prior = await _preserve_terminal_evaluation_pointer(
        db_session, attempt=attempt, pending=pending
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, pending, stage, job):
        await db_session.refresh(row)

    assert session.conversation_state == "recoverable_error"
    assert attempt.current_evaluation_version_id == prior.id
    assert attempt.attempt_state == "recoverable_error"
    assert pending.state == "failed"
    assert stage.stage_state == "failed_retryable"
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_real_reconciled_failure_is_claimable_without_publishing_failed_evaluation(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, pending, content, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=0, limit=2
    )
    pending.evaluation_contract_version = RUBRIC_CONTRACT
    prior = await _preserve_terminal_evaluation_pointer(
        db_session, attempt=attempt, pending=pending
    )
    transcript = await db_session.get(
        InterviewTranscriptVersion, attempt.current_transcript_version_id
    )
    assert transcript is not None
    transcript.content_hash = "real-reconciled-transcript-hash"
    diagnostics = _stage_immutable_diagnostics(
        stage_name="content_evaluation",
        audio_content_hash=None,
        transcript_version_id=transcript.id,
        transcript_content_hash=transcript.content_hash,
        evaluation_contract_version=pending.evaluation_contract_version,
        evidence_contract_version=pending.evidence_contract_version,
        follow_up_contract_version=pending.follow_up_contract_version,
    )
    content.diagnostics_json = diagnostics
    for stage_name in (
        "audio_persist",
        "transcription",
        "speech_analysis",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    ):
        transcript_bound = stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }
        not_applicable = stage_name in {
            "audio_persist",
            "transcription",
            "speech_analysis",
            "audio_cleanup",
        }
        db_session.add(
            InterviewAttemptStage(
                recording_id=attempt.id,
                evaluation_version_id=pending.id,
                stage_name=stage_name,
                stage_state="not_applicable" if not_applicable else "pending",
                attempt_count=0,
                repair_count=0,
                job_id=content.job_id,
                claim_token=content.claim_token,
                expected_processing_generation=attempt.processing_generation,
                source_transcript_version_id=(
                    transcript.id if transcript_bound else None
                ),
                job_deadline_at=content.job_deadline_at,
                completed_at=now if not_applicable else None,
                diagnostics_json=_stage_immutable_diagnostics(
                    stage_name=stage_name,
                    audio_content_hash=None,
                    transcript_version_id=transcript.id,
                    transcript_content_hash=transcript.content_hash,
                    evaluation_contract_version=pending.evaluation_contract_version,
                    evidence_contract_version=pending.evidence_contract_version,
                    follow_up_contract_version=pending.follow_up_contract_version,
                ),
            )
        )
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    await db_session.refresh(session)
    await db_session.refresh(attempt)
    await db_session.refresh(pending)
    assert attempt.current_evaluation_version_id == prior.id
    assert pending.state == "failed"
    projected = await contextual_allowed_commands(db_session, session)
    assert "retry_processing" in projected
    valid_diagnostics = pending.diagnostics_json
    pending.diagnostics_json = {
        **valid_diagnostics,
        "result": {"reason_code": "coach_grounding_source_unavailable"},
    }
    await db_session.commit()
    assert "retry_processing" not in await contextual_allowed_commands(
        db_session, session
    )
    pending.diagnostics_json = valid_diagnostics
    await db_session.commit()
    valid_token = content.claim_token
    content.claim_token = "forged-stale-stage-token"
    await db_session.commit()
    assert "retry_processing" not in await contextual_allowed_commands(
        db_session, session
    )
    content.claim_token = valid_token
    await db_session.commit()

    dispatched = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        dispatched.append,
    )
    result = await ConversationCommandService(db_session).execute(
        user_id="local",
        session_id=session.id,
        request=ConversationCommandRequest.model_validate(
            {
                "command_id": "retry-real-reconciled-failure",
                "command_type": "retry_processing",
                "expected_state_version": session.state_version,
                "payload": {},
                "contract_version": "coach_conversation_command_v1",
            }
        ),
    )

    await db_session.refresh(attempt)
    assert result.result == "accepted_processing"
    assert len(dispatched) == 1
    assert attempt.processing_retry_count == 1
    assert attempt.processing_generation == 3
    assert attempt.current_evaluation_version_id == prior.id


@pytest.mark.asyncio
async def test_expired_processing_claim_at_retry_limit_becomes_unavailable(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    for row in (session, attempt, evaluation, stage):
        await db_session.refresh(row)

    assert session.conversation_state == "recoverable_error"
    assert attempt.attempt_state == "unavailable"
    assert attempt.evaluation_state == "unavailable"
    assert evaluation.state == "unavailable"
    assert stage.stage_state == "failed_terminal"
    assert stage.last_error_code == "coach_attempt_job_budget_exhausted"
    assert evaluation.diagnostics_json["result"] == {
        "reason_code": "coach_attempt_job_budget_exhausted"
    }
    assert attempt.processing_retry_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage_name", ("evidence_grounding", "follow_up_decision"))
async def test_exhausted_downstream_failure_uses_terminal_stage_fallback(
    db_session,
    stage_name: str,
) -> None:
    """Grounding/follow-up failure must not discard a completed content rubric."""
    now = datetime.utcnow()
    session, _, attempt, evaluation, content, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=2, limit=2
    )
    failed_stage = await _configure_downstream_processing_failure(
        db_session,
        attempt=attempt,
        evaluation=evaluation,
        content_stage=content,
        job=job,
        stage_name=stage_name,
        stage_state="running",
    )
    expected_rubric = dict(evaluation.rubric_json)

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, evaluation, failed_stage, job):
        await db_session.refresh(row)

    assert session.conversation_state == "awaiting_next_action"
    assert (attempt.attempt_state, attempt.evaluation_state) == (
        "completed",
        "completed",
    )
    assert attempt.current_evaluation_version_id == evaluation.id
    assert json.loads(attempt.evaluation_json) == expected_rubric
    assert evaluation.state == "completed"
    assert evaluation.rubric_json == expected_rubric
    assert failed_stage.stage_state == "unavailable"
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_all_terminal_downstream_failure_is_published_once(db_session) -> None:
    """Returning early when no stage is active strands a publishable evaluation."""
    now = datetime.utcnow()
    session, _, attempt, evaluation, content, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=2, limit=2
    )
    failed_stage = await _configure_downstream_processing_failure(
        db_session,
        attempt=attempt,
        evaluation=evaluation,
        content_stage=content,
        job=job,
        stage_name="follow_up_decision",
        stage_state="failed_terminal",
    )
    downstream = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                    InterviewAttemptStage.stage_name == "coaching_enrichment",
                )
            )
        ).all()
    )
    assert len(downstream) == 1
    downstream[0].stage_state = "unavailable"
    downstream[0].completed_at = now
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    await db_session.refresh(evaluation)
    await db_session.refresh(failed_stage)
    assert session.conversation_state == "awaiting_next_action"
    assert evaluation.state == "completed"
    assert failed_stage.stage_state == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage_form", ("active", "all_terminal"))
async def test_startup_selector_matches_targeted_downstream_fallback(
    db_session,
    monkeypatch,
    stage_form: str,
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    session, _, attempt, evaluation, content, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=2, limit=2
    )
    await _configure_downstream_processing_failure(
        db_session,
        attempt=attempt,
        evaluation=evaluation,
        content_stage=content,
        job=job,
        stage_name="follow_up_decision",
        stage_state="running" if stage_form == "active" else "failed_terminal",
    )
    if stage_form == "all_terminal":
        coaching = await db_session.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id == evaluation.id,
                InterviewAttemptStage.stage_name == "coaching_enrichment",
            )
        )
        assert coaching is not None
        coaching.stage_state = "unavailable"
        coaching.completed_at = now
        await db_session.commit()
    session_id = session.id
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "awaiting_next_action"


@pytest.mark.asyncio
async def test_exhausted_recovery_publishes_unavailable_from_null_pointer(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )
    attempt.current_evaluation_version_id = None
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    for row in (attempt, evaluation):
        await db_session.refresh(row)

    expected = {
        "answer_level": "not_assessed",
        "contract_version": RUBRIC_CONTRACT,
    }
    assert attempt.current_evaluation_version_id == evaluation.id
    assert json.loads(attempt.evaluation_json) == expected
    assert evaluation.rubric_json == expected
    assert evaluation.state == "unavailable"


@pytest.mark.asyncio
async def test_exhausted_recovery_supersedes_prior_terminal_pointer(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, pending, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )
    prior = await _preserve_terminal_evaluation_pointer(
        db_session, attempt=attempt, pending=pending
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    for row in (attempt, pending, prior):
        await db_session.refresh(row)

    expected = {
        "answer_level": "not_assessed",
        "contract_version": RUBRIC_CONTRACT,
    }
    assert prior.state == "superseded"
    assert attempt.current_evaluation_version_id == pending.id
    assert json.loads(attempt.evaluation_json) == expected
    assert pending.rubric_json == expected
    assert pending.state == "unavailable"


@pytest.mark.asyncio
async def test_terminal_evaluation_missed_transition_moves_to_awaiting_once(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )
    attempt.attempt_state = "completed"
    attempt.evaluation_state = "completed"
    attempt.async_job_id = None
    evaluation.state = "completed"
    evaluation.diagnostics_json["result"] = {"code": "completed"}
    stage.stage_state = "completed"
    job.status = "done"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "awaiting_next_action"
    assert (session.state_version, session.activity_version) == (4, 2)
    assert (
        await _event_count(db_session, session.id, "attempt_processing_completed") == 1
    )


@pytest.mark.asyncio
async def test_terminal_evaluation_from_superseded_generation_is_noop(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )
    attempt.attempt_state = "completed"
    attempt.evaluation_state = "completed"
    attempt.async_job_id = None
    evaluation.state = "completed"
    evaluation.diagnostics_json = {
        "processing_claim": {
            **evaluation.diagnostics_json["processing_claim"],
            "processing_generation": attempt.processing_generation - 1,
        }
    }
    stage.stage_state = "completed"
    job.status = "done"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "processing_answer"
    assert (
        await _event_count(db_session, session.id, "attempt_processing_completed") == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("coach_evaluation_unavailable", 1),
        ("coach_attempt_job_budget_exhausted", 1),
        ("coach_transcript_schema_invalid", 1),
        ("coach_followup_duplicate", 0),
    ],
)
async def test_terminal_unavailable_missed_transition_uses_shared_reason_authority(
    db_session, reason: str, expected: int
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=2, limit=2
    )
    attempt.attempt_state = attempt.evaluation_state = "unavailable"
    attempt.async_job_id = None
    evaluation.state = "unavailable"
    evaluation.diagnostics_json["result"] = {"reason_code": reason}
    stage.stage_state = "failed_terminal"
    stage.last_error_code = reason
    job.status = "done"
    await db_session.commit()

    assert (
        await reconcile_conversational_session(db_session, session.id, now) == expected
    )
    await db_session.refresh(session)
    assert session.conversation_state == (
        "awaiting_next_action" if expected else "processing_answer"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_key", "bad_value"),
    [
        ("claim_token", "stale-token"),
        ("processing_contract_version", "stale-contract"),
        ("source_transcript_version_id", "stale-transcript"),
    ],
)
async def test_missed_terminal_transition_requires_full_claim_snapshot(
    db_session, claim_key: str, bad_value: object
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )
    attempt.attempt_state = attempt.evaluation_state = "completed"
    attempt.async_job_id = None
    evaluation.state = "completed"
    evaluation.diagnostics_json["result"] = {"code": "completed"}
    evaluation.diagnostics_json["processing_claim"][claim_key] = bad_value
    stage.stage_state = "completed"
    stage.claim_token = None
    job.status = "done"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert (
        session.conversation_state,
        session.state_version,
        session.activity_version,
    ) == (
        "processing_answer",
        3,
        1,
    )


@pytest.mark.asyncio
async def test_expired_processing_fences_every_owned_active_stage_atomically(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )
    sibling = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=evaluation.id,
        stage_name="evidence_grounding",
        stage_state="pending",
        attempt_count=0,
        repair_count=0,
        job_id=stage.job_id,
        claim_token=stage.claim_token,
        expected_processing_generation=stage.expected_processing_generation,
        source_transcript_version_id=evaluation.transcript_version_id,
        job_deadline_at=stage.job_deadline_at,
    )
    db_session.add(sibling)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    await db_session.refresh(stage)
    await db_session.refresh(sibling)
    assert stage.stage_state == sibling.stage_state == "failed_retryable"
    assert stage.claim_token == sibling.claim_token == "stage-token"


@pytest.mark.asyncio
async def test_expired_processing_with_stale_stage_transcript_source_is_noop(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )
    stage.source_transcript_version_id = "stale-private-source"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, evaluation, stage, job):
        await db_session.refresh(row)
    assert session.conversation_state == "processing_answer"
    assert attempt.attempt_state == "pending_processing"
    assert evaluation.state == "pending"
    assert stage.stage_state == "running"
    assert job.status == "running"


@pytest.mark.asyncio
async def test_terminal_budget_audio_pretranscription_uses_exact_unavailable_form(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )
    attempt.recording_type = "audio"
    attempt.audio_content_hash = "audio-hash"
    transcript = await db_session.get(
        InterviewTranscriptVersion, attempt.current_transcript_version_id
    )
    attempt.current_transcript_version_id = None
    evaluation.transcript_version_id = None
    await db_session.flush()
    assert transcript is not None
    await db_session.delete(transcript)
    evaluation.diagnostics_json["processing_claim"]["source_audio_content_hash"] = (
        "audio-hash"
    )
    evaluation.diagnostics_json["processing_claim"]["source_transcript_version_id"] = (
        None
    )
    stage.stage_name = "transcription"
    stage.source_transcript_version_id = None
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    await db_session.refresh(evaluation)
    assert evaluation.state == "unavailable"
    assert evaluation.transcript_version_id is None
    assert evaluation.diagnostics_json["result"] == {
        "reason_code": "transcription_unavailable"
    }


@pytest.mark.asyncio
async def test_terminal_budget_typed_null_transcript_is_corrupt_noop(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )
    assert attempt.recording_type == "text"
    attempt.current_transcript_version_id = None
    evaluation = await db_session.get(
        InterviewAttemptEvaluation, attempt.current_evaluation_version_id
    )
    assert evaluation is not None
    evaluation.transcript_version_id = None
    evaluation.diagnostics_json["processing_claim"]["source_transcript_version_id"] = (
        None
    )
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "processing_answer"


@pytest.mark.asyncio
@pytest.mark.parametrize("transient", ["advancing", "asking_follow_up"])
async def test_transient_state_presents_existing_next_question_once(
    db_session, transient: str
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(db_session, state=transient)
    prior = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="First question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        accepted_recording_id=None,
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
        accepted_at=now,
    )
    db_session.add(accepted)
    await db_session.flush()
    accepted_transcript = InterviewTranscriptVersion(
        recording_id=accepted.id,
        version_number=1,
        transcript="accepted answer",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(accepted_transcript)
    await db_session.flush()
    accepted.current_transcript_version_id = accepted_transcript.id
    prior.accepted_recording_id = accepted.id
    if transient == "asking_follow_up":
        next_question = SessionQuestion(
            session_id=session.id,
            question_num=2,
            text="Give a measurable result.",
            category="technical",
            difficulty="realistic",
            order_in_session=2,
            question_kind="adaptive_follow_up",
            question_state="pending",
            root_question_id=prior.id,
            parent_question_id=prior.id,
            follow_up_depth=1,
            follow_up_reason="measurable_result",
            follow_up_source_recording_id=accepted.id,
            follow_up_source_transcript_version_id=accepted_transcript.id,
        )
    else:
        next_question = SessionQuestion(
            session_id=session.id,
            question_num=2,
            text="Second question",
            category="behavioural",
            difficulty="realistic",
            order_in_session=2,
            question_kind="planned",
            question_state="pending",
        )
    db_session.add(next_question)
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    await db_session.refresh(next_question)
    assert session.conversation_state == "asking"
    assert session.active_question_id == next_question.id
    assert next_question.question_state == "asked"
    assert next_question.asked_sequence == 2
    assert await _event_count(db_session, session.id, "question_presented") == 1


async def _advancing_with_two_planned_questions(db_session, now: datetime):
    session = await _conversational_session(db_session, state="advancing")
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
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        accepted_at=now,
    )
    db_session.add(accepted)
    await db_session.flush()
    prior.accepted_recording_id = accepted.id
    later = SessionQuestion(
        session_id=session.id,
        question_num=3,
        text="Third question",
        category="technical",
        difficulty="realistic",
        order_in_session=3,
        question_kind="planned",
        question_state="pending",
    )
    first = SessionQuestion(
        session_id=session.id,
        question_num=2,
        text="Second question",
        category="behavioural",
        difficulty="realistic",
        order_in_session=2,
        question_kind="planned",
        question_state="pending",
    )
    db_session.add_all((later, first))
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()
    return session, first, later


@pytest.mark.asyncio
async def test_advancing_selects_first_of_multiple_remaining_planned_questions(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, first, later = await _advancing_with_two_planned_questions(db_session, now)
    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    for row in (session, first, later):
        await db_session.refresh(row)
    assert session.active_question_id == first.id
    assert first.question_state == "asked"
    assert later.question_state == "pending"


@pytest.mark.asyncio
async def test_transient_without_persisted_acceptance_is_noop(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
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
    next_question = SessionQuestion(
        session_id=session.id,
        question_num=2,
        text="Second question",
        category="behavioural",
        difficulty="realistic",
        order_in_session=2,
        question_kind="planned",
        question_state="pending",
    )
    db_session.add_all((prior, next_question))
    await db_session.flush()
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(next_question)
    assert next_question.question_state == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["recording", "transcript", "deleted"])
async def test_follow_up_reconciliation_requires_current_accepted_source(
    db_session, mismatch: str
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(db_session, state="asking_follow_up")
    prior = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Root",
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
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        accepted_at=now,
    )
    db_session.add(accepted)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=accepted.id,
        version_number=1,
        transcript="accepted source",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(transcript)
    await db_session.flush()
    accepted.current_transcript_version_id = transcript.id
    prior.accepted_recording_id = accepted.id
    follow_up = SessionQuestion(
        session_id=session.id,
        question_num=2,
        text="Specific follow-up",
        category="technical",
        difficulty="realistic",
        order_in_session=2,
        question_kind="adaptive_follow_up",
        question_state="pending",
        root_question_id=prior.id,
        parent_question_id=prior.id,
        follow_up_depth=1,
        follow_up_reason="measurable_result",
        follow_up_source_recording_id=(
            "stale-recording" if mismatch == "recording" else accepted.id
        ),
        follow_up_source_transcript_version_id=(
            "stale-transcript" if mismatch == "transcript" else transcript.id
        ),
        source_deleted=mismatch == "deleted",
    )
    db_session.add(follow_up)
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(follow_up)
    assert follow_up.question_state == "pending"


@pytest.mark.asyncio
async def test_follow_up_reconciliation_rejects_duplicate_pending_candidates(
    db_session,
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(db_session, state="asking_follow_up")
    await _add_accepted_question(db_session, session, now)
    prior = await db_session.get(SessionQuestion, session.active_question_id)
    assert prior is not None and prior.accepted_recording_id is not None
    accepted = await db_session.get(SessionRecording, prior.accepted_recording_id)
    assert accepted is not None
    transcript = InterviewTranscriptVersion(
        recording_id=accepted.id,
        version_number=1,
        transcript="source",
        source="candidate_text",
        created_by="candidate",
        processing_generation=1,
    )
    db_session.add(transcript)
    await db_session.flush()
    accepted.current_transcript_version_id = transcript.id
    for index in (2, 3):
        db_session.add(
            SessionQuestion(
                session_id=session.id,
                question_num=index,
                text=f"Follow-up {index}",
                category="technical",
                difficulty="realistic",
                order_in_session=index,
                question_kind="adaptive_follow_up",
                question_state="pending",
                root_question_id=prior.id,
                parent_question_id=prior.id,
                follow_up_depth=1,
                follow_up_reason="measurable_result",
                follow_up_source_recording_id=accepted.id,
                follow_up_source_transcript_version_id=transcript.id,
            )
        )
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0


@pytest.mark.asyncio
async def test_advancing_without_question_or_existing_report_claim_fails_closed(
    db_session,
) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "advancing"
    assert session.report_job_id is None


@pytest.mark.asyncio
async def test_advancing_rejects_dangling_report_claim(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await _add_accepted_question(db_session, session, datetime.utcnow())
    session.report_state = "building"
    session.report_build_reason = "initial_completion"
    session.report_job_id = "missing-job"
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "advancing"


@pytest.mark.asyncio
async def test_advancing_finishes_existing_report_claim_once(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await _add_accepted_question(db_session, session, datetime.utcnow())
    job = AsyncJob(type="coach_conversational_report", status="pending")
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_build_reason = "initial_completion"
    session.report_job_id = job.id
    session.report_started_at = datetime.utcnow()
    session.report_contract_version = "coach_conversational_report_v1"
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 1
    )
    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "reporting"
    assert await _event_count(db_session, session.id, "report_claimed") == 1


@pytest.mark.asyncio
async def test_advancing_rejects_wrong_report_job_type_or_missing_snapshot(
    db_session,
) -> None:
    for job_type, started_at in (
        ("submit_answer", datetime.utcnow()),
        ("coach_conversational_report", None),
    ):
        session = await _conversational_session(db_session, state="advancing")
        await _add_accepted_question(db_session, session, datetime.utcnow())
        job = AsyncJob(type=job_type, status="pending")
        db_session.add(job)
        await db_session.flush()
        session.report_state = "building"
        session.report_build_reason = "initial_completion"
        session.report_job_id = job.id
        session.report_started_at = started_at
        session.report_contract_version = "coach_conversational_report_v1"
        await db_session.commit()

        assert (
            await reconcile_conversational_session(
                db_session, session.id, datetime.utcnow()
            )
            == 0
        )


@pytest.mark.asyncio
async def test_reconciliation_event_failure_rolls_back_state(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "rollback-token"
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    session_id = session.id
    job_id = job.id
    await db_session.commit()

    async def fail_event(*args, **kwargs):
        raise RuntimeError("event insert failed")

    monkeypatch.setattr(
        "app.services.coach_reconciliation.ConversationalSessionRepository.append_session_events",
        fail_event,
    )
    with pytest.raises(RuntimeError, match="event insert failed"):
        await reconcile_conversational_session(db_session, session_id, now)
    await db_session.rollback()
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "planning"
    assert recovered.setup_job_id == job_id


@pytest.mark.asyncio
async def test_job_poll_uses_targeted_conversational_reconciliation(db_session) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "poll-token"
    session.setup_claim_expires_at = now - timedelta(days=1)
    session_id = session.id
    job_id = job.id
    await db_session.commit()

    assert await reconcile_job(db_session, job_id) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_startup_reconciliation_uses_shared_conversational_routine(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "startup-token"
    session.setup_claim_expires_at = now - timedelta(days=1)
    session_id = session.id
    await db_session.commit()

    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [0, -1, 101, True])
async def test_startup_reconciliation_rejects_invalid_batch_size(batch_size) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        await reconcile_stale_coach_state(batch_size=batch_size)


@pytest.mark.asyncio
async def test_startup_limit_is_applied_after_stale_candidate_filter(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    live = await _conversational_session(db_session, state="planning", status="setup")
    live_job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(live_job)
    await db_session.flush()
    live.setup_job_id = live_job.id
    live.setup_claim_token = "live-token"
    live.setup_claim_expires_at = now + timedelta(days=1)
    await db_session.commit()
    stale = await _conversational_session(db_session, state="planning", status="setup")
    stale_job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(stale_job)
    await db_session.flush()
    stale.setup_job_id = stale_job.id
    stale.setup_claim_token = "stale-token"
    stale.setup_claim_expires_at = now - timedelta(days=1)
    stale_id = stale.id
    await db_session.commit()
    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, stale_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_startup_pages_past_early_unreconciled_candidate_with_bounded_discovery(
    db_session, monkeypatch
) -> None:
    """A lost fence in an early row must not consume the startup success budget."""
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()

    async def expired_setup(created_at: datetime, token: str) -> InterviewSession:
        session = await _conversational_session(
            db_session, state="planning", status="setup"
        )
        job = AsyncJob(type="coach_session_setup", status="running")
        db_session.add(job)
        await db_session.flush()
        session.created_at = created_at
        session.setup_generation = 1
        session.setup_attempt_count = 1
        session.setup_job_id = job.id
        session.setup_claim_token = token
        session.setup_claim_expires_at = now - timedelta(minutes=1)
        return session

    early = await expired_setup(now - timedelta(days=2), "early-stale-token")
    later = await expired_setup(now - timedelta(days=1), "later-stale-token")
    early_id, later_id = early.id, later.id
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original_execute = AsyncSession.execute
    candidate_page_limits = []

    async def observe_candidate_pages(self, statement, *args, **kwargs):
        columns = set(getattr(statement, "selected_columns", {}).keys())
        if {"id", "experience_version"}.issubset(columns):
            candidate_page_limits.append(statement._limit_clause)
        return await original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", observe_candidate_pages)
    original = reconciliation.reconcile_conversational_session
    reconciled_ids: list[str] = []

    async def lose_early_fence(db, session_id: str) -> int:
        reconciled_ids.append(session_id)
        if session_id == early_id:
            return 0
        return await original(db, session_id)

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", lose_early_fence
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert reconciled_ids == [early_id, later_id]
    assert candidate_page_limits
    assert all(limit is not None for limit in candidate_page_limits)
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, later_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_startup_batch_one_skips_invalid_transient_on_repeated_runs(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    invalid = await _conversational_session(db_session, state="advancing")
    invalid.created_at = now - timedelta(days=2)
    await db_session.commit()
    stale = await _conversational_session(db_session, state="planning", status="setup")
    stale.created_at = now - timedelta(days=1)
    job = AsyncJob(type="coach_session_setup", status="failed")
    db_session.add(job)
    await db_session.flush()
    stale.setup_generation = 1
    stale.setup_attempt_count = 1
    stale.setup_job_id = job.id
    stale.setup_claim_token = "actionable-startup-token"
    stale.setup_claim_expires_at = now - timedelta(minutes=1)
    stale_id = stale.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconcile_stale_coach_state(batch_size=1) == 0
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, stale_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_startup_batch_one_skips_live_legacy_attempt_for_due_report(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    live, live_question = await _session_with_question(db_session)
    live.created_at = now - timedelta(days=2)
    live_job = AsyncJob(type="submit_answer", status="running", updated_at=now)
    db_session.add(live_job)
    await db_session.flush()
    db_session.add(
        SessionRecording(
            session_id=live.id,
            question_id=live_question.id,
            recording_type="text",
            attempt_number=1,
            attempt_kind="primary",
            evaluation_state="pending",
            async_job_id=live_job.id,
        )
    )
    await db_session.commit()
    due, _ = await _session_with_question(db_session)
    due.created_at = now - timedelta(days=1)
    report_job = AsyncJob(
        type="end_coach_session",
        status="failed",
        updated_at=now - timedelta(days=1),
    )
    db_session.add(report_job)
    await db_session.flush()
    due.report_state = "building"
    due.report_job_id = report_job.id
    due.report_started_at = now - timedelta(days=1)
    due_id = due.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, due_id)
    assert recovered is not None
    assert recovered.report_state == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformation",
    [
        "claim_generation_type",
        "claim_extra_key",
        "claim_token_type",
        "claim_contract",
        "claim_deadline",
        "stage_source",
        "stage_sibling_deadline_null",
    ],
)
@pytest.mark.parametrize("newer_kind", ["setup", "processing"])
async def test_startup_prelimit_excludes_malformed_processing_snapshot(
    db_session, monkeypatch, malformation: str, newer_kind: str
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed, _, _, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=5), retries=1, limit=2
    )
    malformed.created_at = now - timedelta(days=2)
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    if malformation == "claim_generation_type":
        claim["processing_generation"] = "2"
    elif malformation == "claim_extra_key":
        claim["private_extra_key"] = "must-fail-closed"
    elif malformation == "claim_token_type":
        claim["claim_token"] = 7
    elif malformation == "claim_contract":
        claim["processing_contract_version"] = "stale-contract"
    elif malformation == "claim_deadline":
        claim["job_deadline_at"] = (now - timedelta(days=1)).isoformat()
    elif malformation == "stage_source":
        stage.source_transcript_version_id = "stale-transcript-source"
    else:
        db_session.add(
            InterviewAttemptStage(
                recording_id=stage.recording_id,
                evaluation_version_id=stage.evaluation_version_id,
                stage_name="evidence_grounding",
                stage_state="running",
                attempt_count=1,
                repair_count=0,
                job_id=stage.job_id,
                claim_token=stage.claim_token,
                expected_processing_generation=stage.expected_processing_generation,
                source_transcript_version_id=stage.source_transcript_version_id,
                job_deadline_at=None,
            )
        )
    evaluation.diagnostics_json = {"processing_claim": claim}
    malformed_id = malformed.id
    await db_session.commit()

    if newer_kind == "setup":
        actionable = await _conversational_session(
            db_session, state="planning", status="setup"
        )
        setup_job = AsyncJob(type="coach_session", status="failed")
        db_session.add(setup_job)
        await db_session.flush()
        actionable.setup_generation = 1
        actionable.setup_attempt_count = 1
        actionable.setup_max_attempts = 2
        actionable.setup_job_id = setup_job.id
        actionable.setup_claim_token = "newer-actionable-setup"
        actionable.setup_claim_expires_at = now - timedelta(minutes=1)
    else:
        actionable, _, _, _, _, _ = await _processing_claim(
            db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
        )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, session_id: str) -> int:
        result = await original(db, session_id)
        selected_results.append((session_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    first_total = await reconciliation.reconcile_stale_coach_state(batch_size=1)
    assert first_total == 1, selected_results
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {session_id for session_id, _ in selected_results}


@pytest.mark.asyncio
async def test_startup_invalid_diagnostics_json_fails_closed_before_limit(
    db_session, monkeypatch
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed, _, _, evaluation, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=5), retries=1, limit=2
    )
    malformed.created_at = now - timedelta(days=2)
    malformed_id = malformed.id
    await db_session.execute(
        text(
            "UPDATE interview_attempt_evaluations "
            "SET diagnostics_json = :diagnostics WHERE id = :evaluation_id"
        ),
        {"diagnostics": "{not-json", "evaluation_id": evaluation.id},
    )
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, session_id: str) -> int:
        result = await original(db, session_id)
        selected_results.append((session_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {session_id for session_id, _ in selected_results}


@pytest.mark.asyncio
@pytest.mark.parametrize("timespec", ["seconds", "milliseconds"])
async def test_startup_deadline_comparison_is_semantic(
    db_session, monkeypatch, timespec: str
) -> None:
    now = datetime.utcnow()
    microsecond = 120_000 if timespec == "milliseconds" else 0
    deadline = (now - timedelta(minutes=1)).replace(microsecond=microsecond)
    session, _, _, evaluation, _, _ = await _processing_claim(
        db_session, deadline=deadline, retries=1, limit=2
    )
    session_id = session.id
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    claim["job_deadline_at"] = deadline.isoformat(timespec=timespec)
    evaluation.diagnostics_json = {"processing_claim": claim}
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


async def _pending_audio_claim_with_active_stage(
    db_session,
    *,
    now: datetime,
    stage_name: str,
    source: str | None = None,
    created_current_generation: bool = False,
):
    session, _, attempt, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    transcript = await db_session.get(
        InterviewTranscriptVersion, evaluation.transcript_version_id
    )
    assert transcript is not None
    attempt.recording_type = "audio"
    attempt.audio_content_hash = "audio-pretranscription-hash"
    attempt.current_transcript_version_id = None
    evaluation.transcript_version_id = None
    diagnostics = dict(evaluation.diagnostics_json)
    claim = dict(diagnostics["processing_claim"])
    claim["source_audio_content_hash"] = attempt.audio_content_hash
    claim["source_transcript_version_id"] = None
    diagnostics["processing_claim"] = claim
    evaluation.diagnostics_json = diagnostics
    stage.stage_name = stage_name
    stage.source_transcript_version_id = source
    if not created_current_generation:
        transcript.processing_generation = attempt.processing_generation - 1
    await db_session.commit()
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage_name", ["audio_persist", "transcription", "speech_analysis"]
)
async def test_startup_selector_admits_each_retryable_audio_pretranscription_stage(
    db_session, monkeypatch, stage_name: str
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    session = await _pending_audio_claim_with_active_stage(
        db_session, now=now, stage_name=stage_name
    )
    session_id = session.id
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert selected_results == [(session_id, 1)]


@pytest.mark.asyncio
async def test_startup_transcription_with_current_generation_transcript_is_excluded(
    db_session, monkeypatch
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed = await _pending_audio_claim_with_active_stage(
        db_session,
        now=now,
        stage_name="transcription",
        created_current_generation=True,
    )
    malformed.created_at = now - timedelta(days=2)
    malformed_id = malformed.id
    assert await reconcile_conversational_session(db_session, malformed_id, now) == 0
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {selected_id for selected_id, _ in selected_results}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage_name", "source"),
    [
        ("content_evaluation", None),
        ("evidence_grounding", None),
        ("audio_persist", "unexpected-transcript-source"),
        ("transcription", "unexpected-transcript-source"),
    ],
)
async def test_retryable_audio_pretranscription_rejects_invalid_stage_forms(
    db_session, monkeypatch, stage_name: str, source: str | None
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed = await _pending_audio_claim_with_active_stage(
        db_session, now=now, stage_name=stage_name, source=source
    )
    malformed.created_at = now - timedelta(days=2)
    malformed_id = malformed.id
    assert await reconcile_conversational_session(db_session, malformed_id, now) == 0
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {selected_id for selected_id, _ in selected_results}


@pytest.mark.asyncio
@pytest.mark.parametrize("delta_microseconds", [1, 100, 400, 999])
async def test_startup_deadline_rejects_microsecond_mismatch_before_limit(
    db_session, monkeypatch, delta_microseconds: int
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    deadline = (now - timedelta(minutes=5)).replace(microsecond=123_000)
    malformed, _, _, evaluation, _, _ = await _processing_claim(
        db_session, deadline=deadline, retries=1, limit=2
    )
    malformed.created_at = now - timedelta(days=2)
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    claim["job_deadline_at"] = (
        deadline + timedelta(microseconds=delta_microseconds)
    ).isoformat()
    evaluation.diagnostics_json = {"processing_claim": claim}
    malformed_id = malformed.id
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {selected_id for selected_id, _ in selected_results}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rendered",
    [
        "2026-07-28T10:11:12",
        "2026-07-28 10:11:12.1",
        "2026-07-28T10:11:12.1204",
        "2026-07-28 10:11:12.120400",
        "2026-07-28T10:11:12.120400Z",
        "2026-07-28 10:11:12.120400+00:00",
    ],
)
async def test_startup_deadline_accepts_v6_equivalent_producer_formats(
    db_session, monkeypatch, rendered: str
) -> None:
    parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    deadline = parsed.replace(tzinfo=None)
    session, _, _, evaluation, _, _ = await _processing_claim(
        db_session, deadline=deadline, retries=1, limit=2
    )
    session_id = session.id
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    claim["job_deadline_at"] = rendered
    evaluation.diagnostics_json = {"processing_claim": claim}
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rendered",
    [
        "2026-07-28T10:11:12.1234567",
        "2026-07-28T10:11:12.120400+01:00",
        "2026-02-30T10:11:12",
        "0000-01-01T10:11:12",
        "not-a-deadline",
    ],
)
async def test_startup_deadline_rejects_invalid_utc_forms_before_limit(
    db_session, monkeypatch, rendered: str
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed, _, _, evaluation, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=5), retries=1, limit=2
    )
    malformed.created_at = now - timedelta(days=2)
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    claim["job_deadline_at"] = rendered
    evaluation.diagnostics_json = {"processing_claim": claim}
    malformed_id = malformed.id
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {selected_id for selected_id, _ in selected_results}


@pytest.mark.asyncio
async def test_startup_raw_matching_year_zero_deadlines_fail_closed_before_limit(
    db_session, monkeypatch
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed, _, _, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=5), retries=1, limit=2
    )
    malformed.created_at = now - timedelta(days=2)
    malformed_id = malformed.id
    claim = dict(evaluation.diagnostics_json["processing_claim"])
    claim["job_deadline_at"] = "0000-01-01T10:11:12.123456"
    evaluation_id = evaluation.id
    stage_id = stage.id
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE interview_attempt_evaluations "
            "SET diagnostics_json = :diagnostics WHERE id = :evaluation_id"
        ),
        {
            "diagnostics": json.dumps({"processing_claim": claim}),
            "evaluation_id": evaluation_id,
        },
    )
    await db_session.execute(
        text(
            "UPDATE interview_attempt_stages "
            "SET job_deadline_at = :deadline WHERE id = :stage_id"
        ),
        {"deadline": "0000-01-01 10:11:12.123456", "stage_id": stage_id},
    )
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {selected_id for selected_id, _ in selected_results}


async def _make_terminal_processing_candidate(
    db_session, *, now: datetime, variant: str
):
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=2, limit=2
    )
    session.created_at = now - timedelta(days=2)
    attempt.attempt_state = attempt.evaluation_state = "completed"
    attempt.async_job_id = None
    evaluation.state = "completed"
    diagnostics = dict(evaluation.diagnostics_json)
    diagnostics["result"] = {"code": "completed"}
    evaluation.diagnostics_json = diagnostics
    stage.stage_state = "completed"
    job.status = "done"

    if variant == "active_question_mismatch":
        other = SessionQuestion(
            session_id=session.id,
            question_num=2,
            text="Unrelated active question",
            category="technical",
            difficulty="realistic",
            order_in_session=2,
            question_kind="planned",
            question_state="asked",
            asked_sequence=2,
        )
        db_session.add(other)
        await db_session.flush()
        session.active_question_id = other.id
    elif variant == "completed_result_not_mapping":
        diagnostics = dict(evaluation.diagnostics_json)
        diagnostics["result"] = "completed"
        evaluation.diagnostics_json = diagnostics
    elif variant == "completed_content_not_completed":
        stage.stage_state = "failed_terminal"
    elif variant == "completed_audio_transcript_wrong_generation":
        transcript = await db_session.get(
            InterviewTranscriptVersion, evaluation.transcript_version_id
        )
        assert transcript is not None
        attempt.recording_type = "audio"
        attempt.audio_content_hash = "audio-hash"
        diagnostics = dict(evaluation.diagnostics_json)
        claim = dict(diagnostics["processing_claim"])
        claim["source_audio_content_hash"] = "audio-hash"
        claim["source_transcript_version_id"] = None
        diagnostics["processing_claim"] = claim
        evaluation.diagnostics_json = diagnostics
        transcript.processing_generation = attempt.processing_generation - 1
    elif variant == "valid_completed":
        pass
    elif variant.startswith("audio_unavailable"):
        transcript = await db_session.get(
            InterviewTranscriptVersion, evaluation.transcript_version_id
        )
        assert transcript is not None
        attempt.recording_type = "audio"
        attempt.audio_content_hash = "audio-hash"
        attempt.current_transcript_version_id = None
        attempt.attempt_state = attempt.evaluation_state = "unavailable"
        evaluation.transcript_version_id = None
        evaluation.state = "unavailable"
        diagnostics = dict(evaluation.diagnostics_json)
        claim = dict(diagnostics["processing_claim"])
        claim["source_audio_content_hash"] = "audio-hash"
        claim["source_transcript_version_id"] = None
        diagnostics["processing_claim"] = claim
        diagnostics["result"] = {"reason_code": "transcription_unavailable"}
        evaluation.diagnostics_json = diagnostics
        stage.stage_name = "transcription"
        stage.stage_state = "failed_terminal"
        stage.last_error_code = "transcription_unavailable"
        stage.source_transcript_version_id = None
        if variant != "audio_unavailable_created_transcript":
            transcript.processing_generation = attempt.processing_generation - 1
        if variant == "audio_unavailable_stage_outcome":
            stage.stage_state = "completed"
        elif variant == "audio_unavailable_completed_downstream":
            db_session.add(
                InterviewAttemptStage(
                    recording_id=attempt.id,
                    evaluation_version_id=evaluation.id,
                    stage_name="content_evaluation",
                    stage_state="completed",
                    attempt_count=1,
                    repair_count=0,
                    job_id=job.id,
                    claim_token=stage.claim_token,
                    expected_processing_generation=attempt.processing_generation,
                    source_transcript_version_id=None,
                    job_deadline_at=stage.job_deadline_at,
                )
            )
    else:
        attempt.attempt_state = attempt.evaluation_state = "unavailable"
        evaluation.state = "unavailable"
        reason = "coach_evaluation_unavailable"
        diagnostics = dict(evaluation.diagnostics_json)
        diagnostics["result"] = {"reason_code": reason}
        stage.stage_state = "failed_terminal"
        stage.last_error_code = reason
        if variant == "unavailable_reason_invalid":
            diagnostics["result"] = {"reason_code": "coach_followup_duplicate"}
            stage.last_error_code = "coach_followup_duplicate"
        elif variant == "unavailable_null_reason_does_not_fallback":
            diagnostics["result"] = {
                "reason_code": None,
                "code": "coach_evaluation_unavailable",
            }
        elif variant == "unavailable_last_error_mismatch":
            stage.last_error_code = "coach_transcript_schema_invalid"
        elif variant == "unavailable_completed_downstream":
            db_session.add(
                InterviewAttemptStage(
                    recording_id=attempt.id,
                    evaluation_version_id=evaluation.id,
                    stage_name="evidence_grounding",
                    stage_state="completed",
                    attempt_count=1,
                    repair_count=0,
                    job_id=job.id,
                    claim_token=stage.claim_token,
                    expected_processing_generation=attempt.processing_generation,
                    source_transcript_version_id=evaluation.transcript_version_id,
                    job_deadline_at=stage.job_deadline_at,
                )
            )
        evaluation.diagnostics_json = diagnostics
    await db_session.commit()
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant",
    [
        "active_question_mismatch",
        "completed_result_not_mapping",
        "completed_content_not_completed",
        "completed_audio_transcript_wrong_generation",
        "unavailable_reason_invalid",
        "unavailable_null_reason_does_not_fallback",
        "unavailable_last_error_mismatch",
        "unavailable_completed_downstream",
        "audio_unavailable_created_transcript",
        "audio_unavailable_stage_outcome",
        "audio_unavailable_completed_downstream",
    ],
)
async def test_startup_terminal_selector_matches_targeted_reconcile_prerequisites(
    db_session, monkeypatch, variant: str
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    malformed = await _make_terminal_processing_candidate(
        db_session, now=now, variant=variant
    )
    malformed_id = malformed.id
    actionable, _, _, _, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(minutes=1), retries=1, limit=2
    )
    actionable.created_at = now - timedelta(days=1)
    actionable_id = actionable.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, session_id: str) -> int:
        result = await original(db, session_id)
        selected_results.append((session_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(actionable_id, 1)]
    assert malformed_id not in {session_id for session_id, _ in selected_results}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant", ["valid_completed", "valid_content_unavailable", "audio_unavailable"]
)
async def test_startup_selector_reconciles_each_valid_terminal_form_once(
    db_session, monkeypatch, variant: str
) -> None:
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    session = await _make_terminal_processing_candidate(
        db_session, now=now, variant=variant
    )
    session_id = session.id
    persisted_diagnostics = await db_session.scalar(
        text(
            "SELECT e.diagnostics_json FROM interview_attempt_evaluations e "
            "JOIN session_recordings r ON r.current_evaluation_version_id = e.id "
            "WHERE r.session_id = :session_id"
        ),
        {"session_id": session_id},
    )
    assert "result" in json.loads(persisted_diagnostics)
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original = reconciliation.reconcile_conversational_session
    selected_results: list[tuple[str, int]] = []

    async def tracking_reconcile(db, selected_id: str) -> int:
        result = await original(db, selected_id)
        selected_results.append((selected_id, result))
        return result

    monkeypatch.setattr(
        reconciliation, "reconcile_conversational_session", tracking_reconcile
    )

    first_total = await reconciliation.reconcile_stale_coach_state(batch_size=1)
    assert first_total == 1, selected_results
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    assert selected_results == [(session_id, 1)]


@pytest.mark.asyncio
async def test_startup_expiry_selects_owned_pending_evaluation_behind_terminal_pointer(
    db_session, monkeypatch
) -> None:
    """Startup selection must use generation/job/claim ownership, not current pointer."""
    from app.services import coach_reconciliation as reconciliation

    now = datetime.utcnow()
    session, _, attempt, pending, _, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )
    prior = await _preserve_terminal_evaluation_pointer(
        db_session, attempt=attempt, pending=pending
    )
    session_id = session.id
    attempt_id = attempt.id
    pending_id = pending.id
    prior_id = prior.id
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 0
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    recovered_attempt = await db_session.get(SessionRecording, attempt_id)
    recovered_pending = await db_session.get(InterviewAttemptEvaluation, pending_id)
    assert recovered is not None and recovered_attempt is not None
    assert recovered_pending is not None
    assert recovered.conversation_state == "recoverable_error"
    assert recovered_attempt.current_evaluation_version_id == prior_id
    assert recovered_pending.state == "failed"


@pytest.mark.asyncio
async def test_startup_treats_multiple_planned_questions_as_actionable(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    session, first, later = await _advancing_with_two_planned_questions(db_session, now)
    session_id, first_id, later_id = session.id, first.id, later.id
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    recovered_first = await db_session.get(SessionQuestion, first_id)
    recovered_later = await db_session.get(SessionQuestion, later_id)
    assert recovered is not None
    assert recovered_first is not None and recovered_later is not None
    assert recovered.active_question_id == first_id
    assert recovered_first.question_state == "asked"
    assert recovered_later.question_state == "pending"


@pytest.mark.asyncio
async def test_startup_resets_running_jobs_before_coach_reconciliation(
    db_session, monkeypatch
) -> None:
    from app import main as app_main

    now = datetime.utcnow()
    session, _, _, _, _, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=5), retries=1, limit=2
    )
    session_id = session.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async def no_init() -> None:
        return None

    class Scheduler:
        def start(self) -> None:
            return None

        def shutdown(self, *, wait: bool) -> None:
            assert wait is False

    monkeypatch.setattr(app_main, "init_db", no_init)
    monkeypatch.setattr(app_main, "AsyncSessionLocal", factory)
    monkeypatch.setattr("app.services.coach_reconciliation.AsyncSessionLocal", factory)
    monkeypatch.setattr(app_main, "JobRepository", lambda session: object())
    monkeypatch.setattr(app_main, "JobService", lambda repository: object())
    monkeypatch.setattr(app_main, "ApplicationRepository", lambda session: object())
    monkeypatch.setattr(app_main, "ReminderService", lambda *args, **kwargs: object())
    monkeypatch.setattr(app_main, "LLMClient", lambda: object())
    monkeypatch.setattr(app_main, "EmailGenerator", lambda client: object())
    monkeypatch.setattr(
        app_main, "create_scheduler", lambda *args, **kwargs: Scheduler()
    )
    monkeypatch.setattr(app_main, "load_runtime", lambda: {"ai_mode": "not_configured"})
    monkeypatch.setattr(app_main.settings, "DIGEST_ENABLED", False)
    monkeypatch.setattr(app_main, "shutdown_telemetry", lambda **kwargs: None)

    async with app_main.lifespan(FastAPI()):
        pass

    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    await db_session.refresh(job)
    assert recovered is not None
    assert job.status == "failed"
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_file_backed_concurrent_reconciliation_is_exactly_once(
    tmp_path,
) -> None:
    database_path = tmp_path / "coach-reconciliation.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 10},
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.utcnow()
    async with factory() as seed:
        session, _, _, _, _, _ = await _processing_claim(
            seed, deadline=now - timedelta(seconds=1), retries=1, limit=2
        )
        session_id = session.id

    async def recover() -> int:
        async with factory() as worker:
            return await reconcile_conversational_session(worker, session_id, now)

    try:
        results = await asyncio.gather(recover(), recover())
        assert sorted(results) == [0, 1]
        async with factory() as verifier:
            assert (
                await _event_count(verifier, session_id, "attempt_processing_failed")
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_answer_recovery_is_no_score_and_idempotent(db_session) -> None:
    session, question = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(
        type="submit_answer", status="running", created_at=old, updated_at=old
    )
    db_session.add(job)
    await db_session.flush()
    recording = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="answer",
        evaluation_state="pending",
        async_job_id=job.id,
        created_at=old,
    )
    db_session.add(recording)
    await db_session.commit()

    assert await reconcile_session(db_session, session.id) == 1
    await db_session.refresh(recording)
    await db_session.refresh(job)
    payload = json.loads(recording.evaluation_json)
    assert recording.evaluation_state == "failed"
    assert payload["scores"] == {}
    assert payload["overall"] is None
    assert payload["reason_code"] == "stale_async_job_recovered"
    assert job.status == "failed"
    assert await reconcile_session(db_session, session.id) == 0


@pytest.mark.asyncio
async def test_done_job_pending_recording_marks_persistence_failure(db_session) -> None:
    session, question = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="submit_answer", status="done", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    recording = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        evaluation_state="pending",
        async_job_id=job.id,
        created_at=old,
    )
    db_session.add(recording)
    await db_session.commit()

    await reconcile_session(db_session, session.id)
    await db_session.refresh(recording)
    gates = json.loads(recording.evaluation_json)["diagnostic"]["gate_codes"]
    assert gates == ["coach_async_job_failed", "coach_persistence_failed"]


@pytest.mark.asyncio
async def test_report_claim_rejects_pending_and_fences_old_worker(db_session) -> None:
    session, question = await _session_with_question(db_session)
    repo = SessionRepository(db_session)
    pending_job = AsyncJob(type="submit_answer")
    db_session.add(pending_job)
    await db_session.flush()
    db_session.add(
        SessionRecording(
            session_id=session.id,
            question_id=question.id,
            recording_type="text",
            evaluation_state="pending",
            async_job_id=pending_job.id,
        )
    )
    session_id = session.id
    await db_session.commit()

    assert not await repo.claim_report(session_id, "report-1", 0)
    await db_session.rollback()

    session = await repo.get_session(session_id)
    recording = (await repo.get_recordings(session_id))[0]
    recording.evaluation_state = "failed"
    await db_session.commit()
    assert await repo.claim_report(session_id, "report-1", session.activity_version)
    await db_session.commit()
    assert await repo.fail_report_claim(
        session_id,
        "report-1",
        {
            "validation_schema_version": "1.0.0",
            "stage": "session_report",
            "outcome": "failed",
            "execution_mode": "deterministic",
            "prompt_id": None,
            "prompt_version": None,
            "output_schema_version": None,
            "model_id": None,
            "attempt_count": 0,
            "repair_count": 0,
            "gate_codes": ["coach_async_job_failed"],
            "duration_ms": 0,
        },
    )
    await db_session.commit()
    assert not await repo.finalize_report_claim(
        session_id,
        "report-1",
        report_json={},
        rubric={},
        overall_score=None,
        feedback_summary="",
        report_state="fallback",
        report_diagnostic={},
        aggregation_diagnostic={},
    )


@pytest.mark.asyncio
async def test_stale_report_recovery_is_retryable_idempotent_and_fenced(
    db_session,
) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="running", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    old_job_id = job.id
    session_id = session.id
    await db_session.commit()

    assert await reconcile_session(db_session, session_id) == 1
    await db_session.refresh(session)
    await db_session.refresh(job)
    assert session.report_state == "failed"
    assert session.status == "active"
    assert session.report_started_at is None
    assert job.status == "failed"
    report_diagnostic = session.diagnostics["stages"]["session_report"]
    assert report_diagnostic["reason_code"] == "stale_async_job_recovered"
    assert report_diagnostic["final"]["gate_codes"] == ["coach_async_job_failed"]
    assert await reconcile_session(db_session, session_id) == 0

    repository = SessionRepository(db_session)
    assert await repository.claim_report(session_id, "replacement-job", 0)
    await db_session.commit()
    assert not await repository.finalize_report_claim(
        session_id,
        old_job_id,
        report_json={},
        rubric={},
        overall_score=None,
        feedback_summary="",
        report_state="fallback",
        report_diagnostic={},
        aggregation_diagnostic={},
    )


@pytest.mark.asyncio
async def test_done_job_building_report_records_persistence_failure(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="done", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    await db_session.commit()

    assert await reconcile_session(db_session, session.id) == 1
    await db_session.refresh(session)
    await db_session.refresh(job)
    gates = session.diagnostics["stages"]["session_report"]["final"]["gate_codes"]
    assert gates == ["coach_async_job_failed", "coach_persistence_failed"]
    assert session.report_state == "failed"
    assert session.status == "active"
    assert job.status == "done"


@pytest.mark.asyncio
async def test_startup_reconciliation_uses_fresh_session_for_stale_report(
    db_session,
    monkeypatch,
) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="running", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    session_id = session.id
    await db_session.commit()

    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await SessionRepository(db_session).get_session(session_id)
    assert recovered is not None
    assert recovered.report_state == "failed"
    assert recovered.status == "active"


@pytest.mark.asyncio
async def test_get_report_returns_snapshot_without_mutation(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    snapshot = {
        "session_id": session.id,
        "report_state": "completed",
        "overall_score": None,
        "question_count_total": 1,
        "question_count_evaluated": 0,
        "question_count_skipped": 0,
        "question_count_unavailable": 0,
        "question_count_unanswered": 1,
        "category_scores": {},
        "executive_summary": "Stored snapshot",
        "strengths": [],
        "improvement_areas": [],
        "coaching_points": [],
        "practice_plan": [],
        "question_evaluations": [],
    }
    session.status = "completed"
    session.report_state = "completed"
    session.report_json = snapshot
    await db_session.commit()

    report = await CoachService.__new__(CoachService).get_report(session.id, db_session)

    assert report.model_dump(mode="json") == snapshot | {"diagnostic": None}
    assert not db_session.dirty


@pytest.mark.asyncio
async def test_legacy_completed_report_is_in_memory_fallback(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    session.status = "completed"
    await db_session.commit()

    report = await CoachService.__new__(CoachService).get_report(session.id, db_session)

    assert report.report_state == "fallback"
    assert report.overall_score is None
    assert report.diagnostic is not None
    await db_session.refresh(session)
    assert session.report_json is None
