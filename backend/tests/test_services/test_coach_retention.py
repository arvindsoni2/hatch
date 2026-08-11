"""Independent, ownership-fenced Coach audio retention behavior."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
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
from app.services.coach_retention import CoachRetentionService
from app.services.coach_attempt_pipeline import AttemptPipelineError, _process_attempt_claim
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import ConversationCommandService
from app.services.coach_reconciliation import reconcile_conversational_session
from app.services.coach_live_view import CoachLiveViewService
from app.services.coach_media_storage import StagedAudio, publish_staged_audio
from app.repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    AttemptProcessingResult,
    ConversationalSessionRepository,
    partition_current_processing_stages,
)


@dataclass
class SeededAudio:
    session: InterviewSession
    attempt: SessionRecording
    evaluation: InterviewAttemptEvaluation
    cleanup_stage: InterviewAttemptStage
    path: Path
    processing_deadline: datetime


async def _seed_audio(db_session, tmp_path: Path) -> SeededAudio:
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        experience_version="conversational_v1",
        status="active",
        conversation_state="processing_answer",
        state_version=7,
        activity_version=5,
        retention_version=2,
        deletion_state="not_requested",
        retention_policy_json={
            "audio": "retain_until_deleted",
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
        question_state="asked",
        asked_sequence=1,
    )
    db_session.add(question)
    await db_session.flush()
    media_root = tmp_path / "coach-media"
    path = media_root / session.id / "answer.webm"
    path.parent.mkdir(parents=True)
    body = b"candidate audio"
    path.write_bytes(body)
    job = AsyncJob(type="coach_attempt_processing", status="running")
    db_session.add(job)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="audio",
        transcript="bounded transcript",
        audio_uri=str(path),
        speech_metrics={"duration_ms": 1200, "word_count": 2},
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        attempt_version=3,
        processing_generation=4,
        processing_retry_limit=2,
        evaluation_state="pending",
        evaluation_json='{"answer_level":"not_assessed"}',
        async_job_id=job.id,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="temporary",
        audio_content_hash=hashlib.sha256(body).hexdigest(),
    )
    db_session.add(attempt)
    await db_session.flush()
    transcript = InterviewTranscriptVersion(
        recording_id=attempt.id,
        version_number=1,
        transcript="bounded transcript",
        source="transcription",
        content_hash=hashlib.sha256(b"bounded transcript").hexdigest(),
        created_by="system",
        processing_generation=4,
    )
    db_session.add(transcript)
    await db_session.flush()
    attempt.current_transcript_version_id = transcript.id
    deadline = datetime.utcnow() + timedelta(minutes=15)
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        transcript_version_id=transcript.id,
        version_number=1,
        state="pending",
        evaluation_contract_version="coach_conversational_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=job.id,
        diagnostics_json={
            "processing_claim": {
                "processing_generation": 4,
                "job_deadline_at": deadline.isoformat(),
                "source_audio_content_hash": hashlib.sha256(body).hexdigest(),
                "source_transcript_version_id": None,
                "expected_session_state_version": 7,
                "processing_contract_version": "coach_processing_v1",
                "claim_token": "processing-token",
            }
        },
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    session.active_recording_id = attempt.id
    stages: list[InterviewAttemptStage] = []
    for name, state in {
        "audio_persist": "completed",
        "transcription": "completed",
        "speech_analysis": "unavailable",
        "content_evaluation": "pending",
        "evidence_grounding": "pending",
        "follow_up_decision": "pending",
        "coaching_enrichment": "pending",
        "audio_cleanup": "pending",
    }.items():
        stage = InterviewAttemptStage(
            recording_id=attempt.id,
            evaluation_version_id=evaluation.id,
            stage_name=name,
            stage_state=state,
            job_id=job.id,
            claim_token="processing-token",
            expected_processing_generation=4,
            source_transcript_version_id=(
                transcript.id
                if name
                in {
                    "content_evaluation",
                    "evidence_grounding",
                    "follow_up_decision",
                    "coaching_enrichment",
                }
                else None
            ),
            job_deadline_at=deadline,
            completed_at=(
                datetime(2026, 7, 25, 11, 59)
                if state in {"completed", "unavailable"}
                else None
            ),
            diagnostics_json={
                "processing_contract_version": "coach_processing_v1",
                "evaluation_contract_version": "coach_conversational_rubric_v1",
                "evidence_contract_version": "coach_evidence_grounding_v1",
                "follow_up_contract_version": "coach_follow_up_v1",
                "source_audio_content_hash": hashlib.sha256(body).hexdigest(),
                "source_transcript_version_id": (
                    transcript.id
                    if name
                    in {
                        "content_evaluation",
                        "evidence_grounding",
                        "follow_up_decision",
                        "coaching_enrichment",
                    }
                    else None
                ),
                "source_transcript_content_hash": (
                    transcript.content_hash
                    if name
                    in {
                        "content_evaluation",
                        "evidence_grounding",
                        "follow_up_decision",
                        "coaching_enrichment",
                    }
                    else None
                ),
                "result_transcript_version_id": (
                    transcript.id if name == "transcription" else None
                ),
                "result_transcript_content_hash": (
                    transcript.content_hash if name == "transcription" else None
                ),
            },
        )
        stages.append(stage)
    db_session.add_all(stages)
    await db_session.commit()
    return SeededAudio(session, attempt, evaluation, stages[-1], path, deadline)


async def _make_content_retryable(
    db_session, seeded: SeededAudio
) -> tuple[int, int]:
    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id
                )
            )
        ).all()
    )
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "failed_retryable"
            stage.last_error_code = "coach_evaluation_unavailable"
            stage.completed_at = datetime.utcnow()
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
            stage.completed_at = datetime.utcnow()
    seeded.evaluation.state = "failed"
    seeded.evaluation.diagnostics_json = {
        "processing_claim": seeded.evaluation.diagnostics_json["processing_claim"],
        "result": {"reason_code": "coach_evaluation_unavailable"},
    }
    seeded.attempt.attempt_state = "recoverable_error"
    seeded.attempt.evaluation_state = "failed"
    seeded.attempt.async_job_id = None
    seeded.session.conversation_state = "recoverable_error"
    seeded.session.recoverable_error_scope = "attempt_processing"
    seeded.session.recoverable_error_code = "coach_evaluation_unavailable"
    processing_job = await db_session.get(AsyncJob, seeded.evaluation.async_job_id)
    assert processing_job is not None
    processing_job.status = "failed"
    processing_job.error = "coach_evaluation_unavailable"
    await db_session.commit()
    return (
        seeded.attempt.processing_generation,
        seeded.attempt.processing_retry_count,
    )


async def _processing_authority_signature(db_session, seeded: SeededAudio) -> tuple:
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.evaluation)
    job = await db_session.get(AsyncJob, seeded.evaluation.async_job_id)
    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id
                )
            )
        ).all()
    )
    return (
        seeded.session.conversation_state,
        seeded.session.state_version,
        seeded.session.retention_version,
        seeded.attempt.attempt_state,
        seeded.attempt.attempt_version,
        seeded.attempt.processing_generation,
        seeded.attempt.processing_retry_count,
        seeded.attempt.evaluation_state,
        seeded.attempt.async_job_id,
        seeded.attempt.audio_uri,
        seeded.attempt.audio_retention_state,
        seeded.evaluation.state,
        None if job is None else job.status,
        tuple(
            sorted(
                (
                    stage.stage_name,
                    stage.stage_state,
                    stage.job_id,
                    stage.claim_token,
                    stage.job_deadline_at,
                    stage.last_error_code,
                )
                for stage in stages
            )
        ),
    )


async def _cleanup_publication_signature(db_session, seeded: SeededAudio) -> tuple:
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    return (
        seeded.attempt.attempt_state,
        seeded.attempt.audio_retention_state,
        seeded.attempt.attempt_version,
        seeded.attempt.audio_uri,
        seeded.attempt.audio_deleted_at,
        seeded.session.state_version,
        seeded.session.retention_version,
        seeded.cleanup_stage.stage_state,
        seeded.cleanup_stage.job_id,
        seeded.cleanup_stage.claim_token,
        seeded.cleanup_stage.job_deadline_at,
        seeded.cleanup_stage.attempt_count,
        seeded.cleanup_stage.last_error_code,
        int(
            await db_session.scalar(
                select(func.count(AsyncJob.id)).where(
                    AsyncJob.type == "coach_audio_cleanup"
                )
            )
            or 0
        ),
        int(
            await db_session.scalar(
                select(func.count(InterviewSessionEvent.id)).where(
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type.in_(
                        ("audio_cleanup_claimed", "audio_deleted", "audio_delete_failed")
                    ),
                )
            )
            or 0
        ),
    )


@pytest.mark.asyncio
async def test_default_cleanup_claims_before_evaluation_finishes(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")

    claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    )

    assert claim is not None
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.evaluation)
    await db_session.refresh(seeded.cleanup_stage)
    assert seeded.attempt.audio_retention_state == "delete_pending"
    assert seeded.evaluation.state == "pending"
    assert seeded.cleanup_stage.stage_state == "running"


@pytest.mark.asyncio
async def test_default_cleanup_rejects_cancelled_terminal_failure_without_mutation(
    db_session, tmp_path: Path
) -> None:
    """Cancelled terminal failures are candidate-retried, never default-cleaned."""
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.attempt.attempt_state = "cancelled"
    seeded.attempt.audio_retention_state = "delete_failed"
    seeded.cleanup_stage.stage_state = "failed_retryable"
    seeded.cleanup_stage.last_error_code = "coach_audio_deletion_failed"
    await db_session.commit()
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")

    before = (
        seeded.attempt.attempt_state,
        seeded.attempt.audio_retention_state,
        seeded.attempt.attempt_version,
        seeded.attempt.audio_uri,
        seeded.session.state_version,
        seeded.session.retention_version,
        seeded.cleanup_stage.stage_state,
        seeded.cleanup_stage.job_id,
        seeded.cleanup_stage.claim_token,
        seeded.cleanup_stage.job_deadline_at,
        seeded.cleanup_stage.attempt_count,
        int(
            await db_session.scalar(
                select(func.count(AsyncJob.id)).where(
                    AsyncJob.type == "coach_audio_cleanup"
                )
            )
            or 0
        ),
        int(
            await db_session.scalar(
                select(func.count(InterviewSessionEvent.id)).where(
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type.in_(
                        ("audio_cleanup_claimed", "audio_deleted", "audio_delete_failed")
                    ),
                )
            )
            or 0
        ),
    )

    assert not await retention.default_cleanup_is_due(
        seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    )
    assert (
        await retention.claim_default_cleanup(
            seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        )
        is None
    )

    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    after = (
        seeded.attempt.attempt_state,
        seeded.attempt.audio_retention_state,
        seeded.attempt.attempt_version,
        seeded.attempt.audio_uri,
        seeded.session.state_version,
        seeded.session.retention_version,
        seeded.cleanup_stage.stage_state,
        seeded.cleanup_stage.job_id,
        seeded.cleanup_stage.claim_token,
        seeded.cleanup_stage.job_deadline_at,
        seeded.cleanup_stage.attempt_count,
        int(
            await db_session.scalar(
                select(func.count(AsyncJob.id)).where(
                    AsyncJob.type == "coach_audio_cleanup"
                )
            )
            or 0
        ),
        int(
            await db_session.scalar(
                select(func.count(InterviewSessionEvent.id)).where(
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type.in_(
                        ("audio_cleanup_claimed", "audio_deleted", "audio_delete_failed")
                    ),
                )
            )
            or 0
        ),
    )
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_boundary", "cleanup_state"),
    (
        ("missing", "failed_retryable"),
        ("invalid", "pending"),
    ),
)
async def test_default_cleanup_fallback_rejects_cancelled_terminal_failure_without_mutation(
    db_session,
    tmp_path: Path,
    media_boundary: str,
    cleanup_state: str,
) -> None:
    """Pipeline fallback cannot publish a generic result for cancellation retry."""
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.attempt.attempt_state = "cancelled"
    seeded.attempt.audio_retention_state = "delete_failed"
    seeded.cleanup_stage.stage_state = cleanup_state
    seeded.cleanup_stage.last_error_code = "coach_audio_deletion_failed"
    if media_boundary == "missing":
        seeded.path.unlink()
    else:
        seeded.path.write_bytes(b"hash-mismatched audio")
    await db_session.commit()
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    before = await _cleanup_publication_signature(db_session, seeded)

    preclaim_result = await retention.classify_cleanup_preclaim(seeded.attempt.id)
    recorded = bool(
        preclaim_result is not None
        and await retention.record_cleanup_claim_failure(
            seeded.attempt.id,
            datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
            result=preclaim_result,
        )
    )

    assert preclaim_result is None
    assert recorded is False
    assert await _cleanup_publication_signature(db_session, seeded) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_boundary", "fallback_result", "cleanup_state"),
    (
        ("missing", "deleted", "failed_retryable"),
        ("invalid", "delete_failed", "pending"),
    ),
)
async def test_default_cleanup_fallback_recorder_rejects_cancelled_terminal_failure_race(
    db_session,
    tmp_path: Path,
    media_boundary: str,
    fallback_result: str,
    cleanup_state: str,
) -> None:
    """The recorder repeats fallback authority after classification races."""
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.attempt.attempt_state = "cancelled"
    seeded.attempt.audio_retention_state = "delete_failed"
    seeded.cleanup_stage.stage_state = cleanup_state
    seeded.cleanup_stage.last_error_code = "coach_audio_deletion_failed"
    if media_boundary == "missing":
        seeded.path.unlink()
    else:
        seeded.path.write_bytes(b"hash-mismatched audio")
    await db_session.commit()
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    before = await _cleanup_publication_signature(db_session, seeded)

    assert not await retention.record_cleanup_claim_failure(
        seeded.attempt.id,
        datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
        result=fallback_result,
    )
    assert await _cleanup_publication_signature(db_session, seeded) == before


@pytest.mark.asyncio
async def test_cleanup_fence_cannot_delete_replacement(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    )
    assert claim is not None
    replacement = seeded.path.with_name("replacement.webm")
    replacement.write_bytes(b"replacement audio")
    seeded.attempt.audio_uri = str(replacement)
    seeded.attempt.audio_content_hash = hashlib.sha256(b"replacement audio").hexdigest()
    await db_session.flush()

    assert await retention.delete_claimed_audio(claim) == "stale_claim"
    assert replacement.read_bytes() == b"replacement audio"


@pytest.mark.asyncio
async def test_explicit_delete_preserves_analytical_data_and_activity_version(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    before = (
        seeded.attempt.transcript,
        seeded.attempt.current_transcript_version_id,
        seeded.attempt.current_evaluation_version_id,
        seeded.attempt.evaluation_json,
        dict(seeded.attempt.speech_metrics or {}),
        seeded.session.activity_version,
    )

    assert await retention.delete_audio(seeded.attempt.id) == "deleted"
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)

    assert (
        seeded.attempt.transcript,
        seeded.attempt.current_transcript_version_id,
        seeded.attempt.current_evaluation_version_id,
        seeded.attempt.evaluation_json,
        seeded.attempt.speech_metrics,
        seeded.session.activity_version,
    ) == before
    assert seeded.attempt.audio_uri is None
    assert seeded.attempt.audio_retention_state == "deleted"
    assert not seeded.path.exists()
    assert (seeded.attempt.attempt_version, seeded.session.state_version) == (4, 8)
    assert seeded.session.retention_version == 3

    assert await retention.delete_audio(seeded.attempt.id) == "deleted"
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    assert (seeded.attempt.attempt_version, seeded.session.state_version) == (4, 8)
    assert seeded.session.retention_version == 3
    events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.event_type == "audio_deleted",
                )
            )
        ).all()
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_failed_transcription_cleanup_is_not_claimed_before_24_hours(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    transcription = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.recording_id == seeded.attempt.id,
            InterviewAttemptStage.stage_name == "transcription",
        )
    )
    assert transcription is not None
    seeded.attempt.current_transcript_version_id = None
    seeded.evaluation.transcript_version_id = None
    transcription.stage_state = "failed_terminal"
    transcription.completed_at = datetime(2026, 7, 25, 12, 0)
    await db_session.commit()
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")

    assert (
        await retention.claim_default_cleanup(
            seeded.attempt.id,
            datetime(2026, 7, 26, 11, 59, 59, tzinfo=timezone.utc),
        )
        is None
    )
    assert (
        await retention.claim_default_cleanup(
            seeded.attempt.id,
            datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
        )
        is not None
    )


@pytest.mark.asyncio
async def test_reconciliation_deletes_failed_transcription_audio_only_when_due(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    transcription = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.recording_id == seeded.attempt.id,
            InterviewAttemptStage.stage_name == "transcription",
        )
    )
    assert transcription is not None
    seeded.attempt.current_transcript_version_id = None
    seeded.evaluation.transcript_version_id = None
    transcription.stage_state = "failed_terminal"
    transcription.completed_at = datetime(2026, 7, 25, 12, 0)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime(2026, 7, 26, 11, 59, 59)
        )
        == 0
    )
    assert seeded.path.exists()
    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime(2026, 7, 26, 12, 0)
        )
        == 1
    )
    await db_session.refresh(seeded.attempt)
    assert seeded.attempt.audio_retention_state == "deleted"
    assert not seeded.path.exists()


@pytest.mark.asyncio
async def test_not_due_missing_audio_is_not_terminalised_by_reconciliation(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    transcription = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.recording_id == seeded.attempt.id,
            InterviewAttemptStage.stage_name == "transcription",
        )
    )
    assert transcription is not None
    seeded.attempt.current_transcript_version_id = None
    seeded.evaluation.transcript_version_id = None
    transcription.stage_state = "failed_terminal"
    transcription.completed_at = datetime(2026, 7, 25, 12, 0)
    seeded.path.unlink()
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    before = (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    )

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime(2026, 7, 26, 11, 59, 59)
        )
        == 0
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    event_count = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id)).where(
            InterviewSessionEvent.session_id == seeded.session.id,
            InterviewSessionEvent.recording_id == seeded.attempt.id,
            InterviewSessionEvent.event_type.in_(
                ("audio_deleted", "audio_delete_failed")
            ),
        )
    )

    assert seeded.attempt.audio_retention_state == "temporary"
    assert seeded.attempt.audio_uri == str(seeded.path)
    assert (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    ) == before
    assert event_count == 0


@pytest.mark.asyncio
async def test_session_cleanup_pages_past_twenty_ineligible_attempts(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    base = datetime(2026, 7, 20, 12, 0)
    body = b"earlier ineligible audio"
    digest = hashlib.sha256(body).hexdigest()
    earlier: list[SessionRecording] = []
    for index in range(21):
        path = seeded.path.parent / f"ineligible-{index:02d}.webm"
        path.write_bytes(body)
        attempt = SessionRecording(
            session_id=seeded.session.id,
            question_id=None,
            recording_type="audio",
            audio_uri=str(path),
            created_at=base + timedelta(seconds=index),
            attempt_state="unavailable",
            attempt_version=1,
            processing_generation=1,
            processing_retry_limit=2,
            evaluation_state="unavailable",
            audio_retention_policy="delete_after_processing",
            audio_retention_state="temporary",
            audio_content_hash=digest,
        )
        earlier.append(attempt)
    seeded.attempt.created_at = base + timedelta(seconds=21)
    db_session.add_all(earlier)
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime(2026, 7, 26, 12, 0)
        )
        == 1
    )
    await db_session.refresh(seeded.attempt)
    assert seeded.attempt.audio_retention_state == "deleted"
    assert not seeded.path.exists()
    assert all(attempt.audio_retention_state == "temporary" for attempt in earlier)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "conversation_state"),
    (("completed", "completed"), ("active", "paused")),
)
async def test_startup_discovers_cleanup_only_session_outside_processing(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    conversation_state: str,
) -> None:
    from app.services import coach_reconciliation as reconciliation

    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.status = status
    seeded.session.conversation_state = conversation_state
    attempt_id = seeded.attempt.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    attempt = await db_session.get(SessionRecording, attempt_id)
    assert attempt is not None
    assert attempt.audio_retention_state == "deleted"
    assert not seeded.path.exists()


@pytest.mark.asyncio
async def test_startup_recovers_expired_cleanup_claim_after_postcommit_crash(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import coach_reconciliation as reconciliation

    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.conversation_state = "paused"
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    claim = await retention.claim_default_cleanup(
        seeded.attempt.id,
        datetime.now(timezone.utc)
        - timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 1
        ),
    )
    assert claim is not None
    attempt_id = seeded.attempt.id
    await db_session.commit()
    if claim._deletion_lease is not None:
        claim._deletion_lease.close()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    attempt = await db_session.get(SessionRecording, attempt_id)
    assert attempt is not None
    assert attempt.audio_retention_state == "deleted"
    assert not seeded.path.exists()


@pytest.mark.asyncio
async def test_cleanup_startup_pages_past_early_invalid_candidate_with_limit(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import coach_reconciliation as reconciliation

    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    now = datetime.utcnow()
    early = await _seed_audio(db_session, tmp_path)
    early.session.status = "completed"
    early.session.conversation_state = "completed"
    early.session.created_at = now - timedelta(days=2)
    speech = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == early.evaluation.id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert speech is not None
    speech.stage_state = "pending"
    speech.completed_at = None
    valid = await _seed_audio(db_session, tmp_path)
    valid.session.status = "completed"
    valid.session.conversation_state = "completed"
    valid.session.created_at = now - timedelta(days=1)
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(reconciliation, "AsyncSessionLocal", factory)
    original_execute = AsyncSession.execute
    page_limits: list[object] = []

    async def observe_pages(self, statement, *args, **kwargs):
        columns = set(getattr(statement, "selected_columns", {}).keys())
        if {"id", "experience_version"}.issubset(columns):
            page_limits.append(statement._limit_clause)
        return await original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", observe_pages)
    original_reconcile = reconciliation.reconcile_conversational_session
    selected: list[str] = []

    async def track(db, session_id: str) -> int:
        selected.append(session_id)
        return await original_reconcile(db, session_id)

    monkeypatch.setattr(reconciliation, "reconcile_conversational_session", track)

    assert await reconciliation.reconcile_stale_coach_state(batch_size=1) == 1
    assert valid.session.id in selected
    assert len(selected) <= 2
    assert page_limits and all(limit is not None for limit in page_limits)


@pytest.mark.asyncio
async def test_explicit_preclaim_hash_failure_is_durable_and_idempotent(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.status = "completed"
    seeded.session.conversation_state = "completed"
    seeded.path.write_bytes(b"hash-mismatched-audio")
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    prior_attempt_version = seeded.attempt.attempt_version
    prior_state_version = seeded.session.state_version
    prior_retention_version = seeded.session.retention_version
    request = ConversationCommandRequest.model_validate(
        {
            "command_id": "delete-invalid-audio",
            "command_type": "delete_audio",
            "expected_state_version": prior_state_version,
            "payload": {"attempt_id": seeded.attempt.id},
            "contract_version": "coach_conversation_command_v1",
        }
    )
    service = ConversationCommandService(db_session)

    result = await service.execute(
        user_id="local", session_id=seeded.session.id, request=request
    )

    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    cleanup_job = await db_session.get(AsyncJob, seeded.cleanup_stage.job_id)
    events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type == "audio_delete_failed",
                )
            )
        ).all()
    )
    assert result.result == "completed"
    assert seeded.attempt.audio_retention_state == "delete_failed"
    assert seeded.attempt.attempt_version == prior_attempt_version + 1
    assert seeded.session.state_version == prior_state_version + 1
    assert seeded.session.retention_version == prior_retention_version + 1
    assert seeded.cleanup_stage.stage_state == "failed_retryable"
    assert seeded.cleanup_stage.last_error_code == "coach_audio_deletion_failed"
    assert cleanup_job is not None
    assert cleanup_job.type == "coach_audio_cleanup"
    assert cleanup_job.status == "failed"
    assert cleanup_job.error == "coach_audio_deletion_failed"
    assert len(events) == 1
    assert events[0].actor_type == "candidate"
    assert events[0].payload_json == {"reason": "explicit_delete"}

    replay = await service.execute(
        user_id="local", session_id=seeded.session.id, request=request
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    replay_events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type == "audio_delete_failed",
                )
            )
        ).all()
    )
    assert replay == result
    assert seeded.attempt.attempt_version == prior_attempt_version + 1
    assert seeded.session.state_version == prior_state_version + 1
    assert seeded.session.retention_version == prior_retention_version + 1
    assert len(replay_events) == 1


@pytest.mark.asyncio
async def test_reconciliation_records_one_fenced_preclaim_hash_failure(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.status = "completed"
    seeded.session.conversation_state = "completed"
    seeded.path.write_bytes(b"hash-mismatched-audio")
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    prior_versions = (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    )

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime.utcnow()
        )
        == 1
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type == "audio_delete_failed",
                )
            )
        ).all()
    )
    assert seeded.attempt.audio_retention_state == "delete_failed"
    assert seeded.attempt.attempt_version == prior_versions[0] + 1
    assert seeded.session.state_version == prior_versions[1] + 1
    assert seeded.session.retention_version == prior_versions[2] + 1
    assert seeded.cleanup_stage.stage_state == "failed_retryable"
    assert len(events) == 1
    assert events[0].actor_type == "reconciler"
    assert events[0].payload_json == {"reason": "default_cleanup"}

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    repeat_events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type == "audio_delete_failed",
                )
            )
        ).all()
    )
    assert (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    ) == (prior_versions[0] + 1, prior_versions[1] + 1, prior_versions[2] + 1)
    assert len(repeat_events) == 1


@pytest.mark.asyncio
async def test_reconciliation_treats_truly_missing_audio_as_deleted(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.status = "completed"
    seeded.session.conversation_state = "completed"
    seeded.path.unlink()
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime.utcnow()
        )
        == 1
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.cleanup_stage)
    event = await db_session.scalar(
        select(InterviewSessionEvent).where(
            InterviewSessionEvent.session_id == seeded.session.id,
            InterviewSessionEvent.recording_id == seeded.attempt.id,
            InterviewSessionEvent.event_type == "audio_deleted",
        )
    )
    assert seeded.attempt.audio_retention_state == "deleted"
    assert seeded.attempt.audio_uri is None
    assert seeded.cleanup_stage.stage_state == "completed"
    assert event is not None and event.actor_type == "reconciler"


@pytest.mark.asyncio
async def test_reconciliation_fences_expired_claim_before_recording_media_failure(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.status = "completed"
    seeded.session.conversation_state = "completed"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    now = datetime.utcnow()
    retention = CoachRetentionService(db_session)
    claim = await retention.claim_default_cleanup(
        seeded.attempt.id,
        now
        - timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 1
        ),
    )
    assert claim is not None
    await db_session.commit()
    if claim._deletion_lease is not None:
        claim._deletion_lease.close()
    seeded.path.unlink()
    seeded.path.write_bytes(b"replacement-audio")
    prior_versions = (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    )

    assert (
        await reconcile_conversational_session(db_session, seeded.session.id, now)
        == 1
    )
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    prior_job = await db_session.get(AsyncJob, claim.job_id)
    failure_job = await db_session.get(AsyncJob, seeded.cleanup_stage.job_id)
    assert seeded.path.read_bytes() == b"replacement-audio"
    assert seeded.attempt.audio_retention_state == "delete_failed"
    assert seeded.cleanup_stage.stage_state == "failed_retryable"
    assert seeded.cleanup_stage.job_id != claim.job_id
    assert prior_job is not None and prior_job.status == "failed"
    assert failure_job is not None and failure_job.status == "failed"
    assert (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    ) == (prior_versions[0] + 1, prior_versions[1] + 1, prior_versions[2] + 1)

    assert (
        await reconcile_conversational_session(db_session, seeded.session.id, now)
        == 0
    )


@pytest.mark.asyncio
async def test_delete_audio_command_uses_retention_service_and_is_idempotent(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.conversation_state = "awaiting_next_action"
    seeded.attempt.attempt_state = "unavailable"
    seeded.attempt.evaluation_state = "unavailable"
    seeded.attempt.async_job_id = None
    seeded.evaluation.state = "unavailable"
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    request = ConversationCommandRequest.model_validate(
        {
            "command_id": "delete-audio-once",
            "command_type": "delete_audio",
            "expected_state_version": seeded.session.state_version,
            "payload": {"attempt_id": seeded.attempt.id},
            "contract_version": "coach_conversation_command_v1",
        }
    )

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=seeded.session.id, request=request
    )

    assert result.result == "accepted_processing"
    assert result.state_version == 7
    await db_session.refresh(seeded.attempt)
    assert seeded.attempt.audio_retention_state == "deleted"
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=seeded.session.id, request=request
    )
    assert replay == result
    live = await CoachLiveViewService(db_session).get_live_view(
        user_id="local", session_id=seeded.session.id
    )
    assert live.retention.audio_policy == "retain_until_deleted"
    assert live.retention.current_audio_state == "deleted"


@pytest.mark.asyncio
async def test_delete_audio_command_crash_replays_durable_accepted_result(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.conversation_state = "awaiting_next_action"
    seeded.attempt.attempt_state = "unavailable"
    seeded.attempt.evaluation_state = "unavailable"
    seeded.attempt.async_job_id = None
    seeded.evaluation.state = "unavailable"
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")

    async def crash_after_command_commit(self, claim) -> str:
        raise RuntimeError("simulated cleanup dispatch crash")

    monkeypatch.setattr(
        CoachRetentionService, "delete_claimed_audio", crash_after_command_commit
    )
    request = ConversationCommandRequest.model_validate(
        {
            "command_id": "delete-audio-crash-replay",
            "command_type": "delete_audio",
            "expected_state_version": seeded.session.state_version,
            "payload": {"attempt_id": seeded.attempt.id},
            "contract_version": "coach_conversation_command_v1",
        }
    )

    first = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=seeded.session.id, request=request
    )
    replay = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=seeded.session.id, request=request
    )

    assert first.result == "accepted_processing"
    assert replay == first
    receipt = await ConversationalSessionRepository(db_session).get_command_result(
        session_id=seeded.session.id, command_id=request.command_id
    )
    assert receipt is not None and receipt.result_json is not None


@pytest.mark.asyncio
async def test_processing_finalises_after_independent_cleanup_deleted_while_pending(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    )
    assert claim is not None
    assert await retention.delete_claimed_audio(claim) == "deleted"
    assert await retention.finalise_audio_cleanup(claim, "deleted") is True
    await db_session.refresh(seeded.evaluation)
    assert seeded.evaluation.state == "pending"

    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == seeded.attempt.id,
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id,
                )
            )
        ).all()
    )
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "unavailable"
            stage.last_error_code = "coach_evaluation_unavailable"
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
        if stage.stage_name != "audio_cleanup":
            stage.completed_at = datetime.utcnow()
    processing_claim = AttemptProcessingClaim(
        session_id=seeded.session.id,
        question_id=seeded.attempt.question_id or "",
        recording_id=seeded.attempt.id,
        transcript_version_id=seeded.attempt.current_transcript_version_id,
        evaluation_version_id=seeded.evaluation.id,
        processing_generation=4,
        job_id=seeded.attempt.async_job_id or "",
        deadline_at=seeded.processing_deadline,
    )

    assert await ConversationalSessionRepository(db_session).finalise_attempt_processing(
        claim=processing_claim,
        result=AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={"answer_level": "not_assessed"},
            transcript_version_id=seeded.attempt.current_transcript_version_id,
            diagnostics={
                "code": "coach_evaluation_unavailable",
                "execution_mode": "deterministic_stub",
            },
        ),
    )


@pytest.mark.asyncio
async def test_explicit_delete_claim_is_durable_before_filesystem_side_effect(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    attempt_id = seeded.attempt.id

    async def crash_before_unlink(_claim) -> str:
        assert seeded.path.exists()
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr(retention, "delete_claimed_audio", crash_before_unlink)
    with pytest.raises(RuntimeError, match="simulated worker crash"):
        await retention.delete_audio(attempt_id)
    await db_session.rollback()
    durable = await db_session.get(SessionRecording, attempt_id)

    assert durable is not None
    assert durable.audio_retention_state == "delete_pending"
    assert seeded.path.exists()

    assert (
        await reconcile_conversational_session(
            db_session,
            seeded.session.id,
            datetime.utcnow()
            + timedelta(
                seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 1
            ),
        )
        == 1
    )
    await db_session.refresh(durable)
    assert durable.audio_retention_state == "deleted"
    recovered_event = await db_session.scalar(
        select(InterviewSessionEvent)
        .where(
            InterviewSessionEvent.session_id == seeded.session.id,
            InterviewSessionEvent.recording_id == attempt_id,
            InterviewSessionEvent.event_type == "audio_deleted",
        )
        .order_by(InterviewSessionEvent.sequence_number.desc())
        .limit(1)
    )
    assert recovered_event is not None
    assert recovered_event.actor_type == "reconciler"
    assert not seeded.path.exists()


@pytest.mark.asyncio
async def test_recoverable_audio_delete_fences_claim_before_physical_deletion(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.session.conversation_state = "recoverable_error"
    seeded.session.recoverable_error_scope = "attempt_processing"
    seeded.session.recoverable_error_code = "coach_evaluation_unavailable"
    seeded.attempt.attempt_state = "recoverable_error"
    seeded.attempt.evaluation_state = "failed"
    processing_job_id = seeded.attempt.async_job_id
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    request = ConversationCommandRequest.model_validate(
        {
            "command_id": "delete-recoverable-audio",
            "command_type": "delete_audio",
            "expected_state_version": seeded.session.state_version,
            "payload": {"attempt_id": seeded.attempt.id},
            "contract_version": "coach_conversation_command_v1",
        }
    )

    result = await ConversationCommandService(db_session).execute(
        user_id="local", session_id=seeded.session.id, request=request
    )

    await db_session.refresh(seeded.attempt)
    processing_job = await db_session.get(AsyncJob, processing_job_id)
    assert seeded.attempt.async_job_id is None
    assert processing_job is not None and processing_job.status == "failed"
    assert processing_job.error == "coach_attempt_processing_cancelled"
    assert seeded.attempt.audio_retention_state == "deleted"
    assert "retry_processing" not in result.allowed_commands


@pytest.mark.asyncio
async def test_reconciliation_finalises_expired_claim_after_unlink_crash(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "coach-media")
    retention = CoachRetentionService(db_session)
    attempt_id = seeded.attempt.id
    session_id = seeded.session.id

    async def crash_after_unlink(_claim, _result) -> bool:
        raise RuntimeError("simulated post-unlink crash")

    monkeypatch.setattr(retention, "finalise_audio_cleanup", crash_after_unlink)
    with pytest.raises(RuntimeError, match="simulated post-unlink crash"):
        await retention.delete_audio(attempt_id)
    await db_session.rollback()
    durable = await db_session.get(SessionRecording, attempt_id)
    assert durable is not None
    assert durable.audio_retention_state == "delete_pending"
    assert not seeded.path.exists()

    assert (
        await reconcile_conversational_session(
            db_session,
                session_id,
            datetime.utcnow()
            + timedelta(
                seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 1
            ),
        )
        == 1
    )
    await db_session.refresh(durable)
    assert durable.audio_retention_state == "deleted"
    recovered_event = await db_session.scalar(
        select(InterviewSessionEvent)
        .where(
            InterviewSessionEvent.session_id == session_id,
            InterviewSessionEvent.recording_id == attempt_id,
            InterviewSessionEvent.event_type == "audio_deleted",
        )
        .order_by(InterviewSessionEvent.sequence_number.desc())
        .limit(1)
    )
    assert recovered_event is not None
    assert recovered_event.actor_type == "reconciler"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_media", ("symlink", "nonregular", "out_of_root"))
async def test_expired_cleanup_records_invalid_media_once_instead_of_assuming_deleted(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_media: str,
) -> None:
    media_root = tmp_path / "coach-media"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", media_root)
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=media_root)
    expired_at = datetime.utcnow() - timedelta(
        seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS + 1
    )
    claim = await retention.claim_default_cleanup(seeded.attempt.id, expired_at)
    assert claim is not None
    await db_session.commit()

    if invalid_media == "symlink":
        target = tmp_path / "replacement-target.webm"
        target.write_bytes(b"replacement target")
        seeded.path.unlink()
        seeded.path.symlink_to(target)
    elif invalid_media == "nonregular":
        seeded.path.unlink()
        seeded.path.mkdir()
    else:
        outside = tmp_path / "outside-owned-root.webm"
        outside.write_bytes(b"outside root")
        seeded.attempt.audio_uri = str(outside)
    await db_session.commit()
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    prior_versions = (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    )

    assert await retention.recover_expired_cleanup(
        seeded.attempt.id, datetime.utcnow()
    )
    await db_session.commit()
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    old_job = await db_session.get(AsyncJob, claim.job_id)
    failure_job = await db_session.get(AsyncJob, seeded.cleanup_stage.job_id)
    failure_events = list(
        (
            await db_session.scalars(
                select(InterviewSessionEvent).where(
                    InterviewSessionEvent.session_id == seeded.session.id,
                    InterviewSessionEvent.recording_id == seeded.attempt.id,
                    InterviewSessionEvent.event_type == "audio_delete_failed",
                )
            )
        ).all()
    )
    deleted_events = int(
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == seeded.session.id,
                InterviewSessionEvent.recording_id == seeded.attempt.id,
                InterviewSessionEvent.event_type == "audio_deleted",
            )
        )
        or 0
    )

    assert seeded.attempt.audio_retention_state == "delete_failed"
    assert seeded.attempt.audio_uri is not None
    assert (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    ) == (prior_versions[0] + 1, prior_versions[1] + 1, prior_versions[2] + 1)
    assert seeded.cleanup_stage.stage_state == "failed_retryable"
    assert seeded.cleanup_stage.last_error_code == "coach_audio_deletion_failed"
    assert old_job is not None and old_job.status == "failed"
    assert failure_job is not None and failure_job.status == "failed"
    assert len(failure_events) == 1
    assert failure_events[0].actor_type == "reconciler"
    assert failure_events[0].payload_json == {"reason": "default_cleanup"}
    assert deleted_events == 0

    assert not await retention.recover_expired_cleanup(
        seeded.attempt.id, datetime.utcnow()
    )
    await db_session.commit()
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    repeat_failure_events = int(
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == seeded.session.id,
                InterviewSessionEvent.recording_id == seeded.attempt.id,
                InterviewSessionEvent.event_type == "audio_delete_failed",
            )
        )
        or 0
    )
    assert (
        seeded.attempt.attempt_version,
        seeded.session.state_version,
        seeded.session.retention_version,
    ) == (prior_versions[0] + 1, prior_versions[1] + 1, prior_versions[2] + 1)
    assert repeat_failure_events == 1


@pytest.mark.asyncio
async def test_processing_reconciliation_preserves_independent_cleanup_authority(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    cleanup_claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    )
    assert cleanup_claim is not None
    assert await retention.delete_claimed_audio(cleanup_claim) == "deleted"
    assert await retention.finalise_audio_cleanup(cleanup_claim, "deleted")
    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == seeded.attempt.id,
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id,
                )
            )
        ).all()
    )
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "unavailable"
            stage.last_error_code = "coach_evaluation_unavailable"
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
        if stage.stage_name != "audio_cleanup":
            stage.completed_at = datetime.utcnow()
    processing_job = await db_session.get(AsyncJob, seeded.attempt.async_job_id)
    assert processing_job is not None
    processing_job.status = "failed"
    processing_job.error = "coach_evaluation_unavailable"
    processing_job.result_json = None
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, seeded.session.id, datetime.utcnow()
        )
        == 1
    )
    cleanup = await db_session.get(InterviewAttemptStage, cleanup_claim.stage_id)
    assert cleanup is not None
    assert cleanup.stage_state == "completed"
    assert cleanup.job_id == cleanup_claim.job_id


@pytest.mark.asyncio
async def test_successful_unlink_finalises_the_new_current_processing_authority(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generation race after unlink cannot strand false delete_pending state."""
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    cleanup_claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime.utcnow()
    )
    assert cleanup_claim is not None
    prior_generation, _ = await _make_content_retryable(db_session, seeded)
    assert await retention.delete_claimed_audio(cleanup_claim) == "deleted"
    # Model the already-in-flight legacy retry that passed admission before the
    # independently committed cleanup claim became visible. The new admission
    # test below proves fresh retries cannot enter this state.
    from app.repositories import conversational_session_repository as repository_module

    async def partition_before_cleanup_commit(*_args, **kwargs):
        stages = kwargs["stages"]
        return (
            tuple(stage for stage in stages if stage.stage_name != "audio_cleanup"),
            None,
        )

    monkeypatch.setattr(
        repository_module,
        "partition_current_processing_stages",
        partition_before_cleanup_commit,
    )
    seeded.cleanup_stage.stage_state = "failed_retryable"
    await db_session.flush()
    retry_job = AsyncJob(type="coach_attempt_processing", status="pending")
    db_session.add(retry_job)
    await db_session.flush()
    retry_deadline = datetime.utcnow() + timedelta(minutes=15)
    raced_retry = await ConversationalSessionRepository(
        db_session
    ).claim_retry_processing(
        recording_id=seeded.attempt.id,
        job_id=retry_job.id,
        deadline=retry_deadline,
        expected_session_state_version=seeded.session.state_version,
    )
    assert raced_retry is not None
    assert raced_retry.processing_generation == prior_generation + 1
    seeded.cleanup_stage.stage_state = "running"
    await db_session.flush()

    assert await retention.finalise_audio_cleanup(cleanup_claim, "deleted") is True

    await db_session.refresh(seeded.attempt)
    current_cleanup = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id
            == raced_retry.evaluation_version_id,
            InterviewAttemptStage.stage_name == "audio_cleanup",
        )
    )
    assert seeded.attempt.audio_retention_state == "deleted"
    assert seeded.attempt.audio_uri is None
    assert current_cleanup is not None
    assert current_cleanup.stage_state == "completed"
    assert current_cleanup.job_id == cleanup_claim.job_id
    assert current_cleanup.claim_token is None
    assert current_cleanup.job_deadline_at == cleanup_claim.deadline_at
    assert current_cleanup.reused_from_stage_id is None
    retention_version = seeded.session.retention_version
    deletion_events = int(
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == seeded.session.id,
                InterviewSessionEvent.recording_id == seeded.attempt.id,
                InterviewSessionEvent.event_type == "audio_deleted",
            )
        )
        or 0
    )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await _process_attempt_claim(raced_retry, session_factory=session_factory)
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    worker_events = int(
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == seeded.session.id,
                InterviewSessionEvent.recording_id == seeded.attempt.id,
                InterviewSessionEvent.event_type == "audio_deleted",
            )
        )
        or 0
    )
    assert seeded.attempt.audio_retention_state == "deleted"
    assert seeded.session.retention_version == retention_version
    assert worker_events == deletion_events == 1


@pytest.mark.asyncio
async def test_content_retry_rejects_active_independent_cleanup_without_budget(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    cleanup_claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime.utcnow()
    )
    assert cleanup_claim is not None
    prior_generation, prior_retry_count = await _make_content_retryable(
        db_session, seeded
    )
    prior_session_version = seeded.session.state_version
    retry_job = AsyncJob(type="coach_attempt_processing", status="pending")
    db_session.add(retry_job)
    await db_session.flush()

    retry_claim = await ConversationalSessionRepository(
        db_session
    ).claim_retry_processing(
        recording_id=seeded.attempt.id,
        job_id=retry_job.id,
        deadline=datetime.utcnow() + timedelta(minutes=15),
        expected_session_state_version=prior_session_version,
    )

    assert retry_claim is None
    await db_session.refresh(seeded.attempt)
    await db_session.refresh(seeded.session)
    await db_session.refresh(seeded.cleanup_stage)
    assert (
        seeded.attempt.processing_generation,
        seeded.attempt.processing_retry_count,
    ) == (prior_generation, prior_retry_count)
    assert seeded.session.state_version == prior_session_version
    assert seeded.session.conversation_state == "recoverable_error"
    assert seeded.cleanup_stage.stage_state == "running"
    assert seeded.cleanup_stage.job_id == cleanup_claim.job_id
    assert seeded.cleanup_stage.claim_token == cleanup_claim.claim_token
    if cleanup_claim._deletion_lease is not None:
        cleanup_claim._deletion_lease.close()


@pytest.mark.asyncio
async def test_cleanup_claim_never_holds_media_lock_while_waiting_for_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "cleanup-upload-lock-order.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}", connect_args={"timeout": 1}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    media_root = tmp_path / "coach-media"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", media_root)
    async with factory() as seed_db:
        seeded = await _seed_audio(seed_db, tmp_path)
        recording_id = seeded.attempt.id
        original_path = seeded.path

    staged_body = b"concurrent upload winner"
    staged_path = tmp_path / "concurrent-upload.stage"
    staged_path.write_bytes(staged_body)
    staged = StagedAudio(
        staged_path,
        hashlib.sha256(staged_body).hexdigest(),
        len(staged_body),
        "audio/webm",
    )
    upload_destination = original_path.parent / "concurrent-upload.webm"
    cleanup_reached_database = asyncio.Event()
    upload_committed = asyncio.Event()

    try:
        async with factory() as cleanup_db, factory() as upload_db:
            original_flush = cleanup_db.flush
            gate_first_flush = True

            async def gated_cleanup_flush(*args, **kwargs) -> None:
                nonlocal gate_first_flush
                if gate_first_flush:
                    gate_first_flush = False
                    cleanup_reached_database.set()
                    await upload_committed.wait()
                await original_flush(*args, **kwargs)

            monkeypatch.setattr(cleanup_db, "flush", gated_cleanup_flush)
            retention = CoachRetentionService(cleanup_db, media_root=media_root)

            async def cleanup_claim():
                claim = await retention.claim_default_cleanup(
                    recording_id, datetime.now(timezone.utc)
                )
                assert claim is not None
                await cleanup_db.commit()
                return claim

            async def upload_while_holding_database_write():
                await cleanup_reached_database.wait()
                upload_db.add(
                    AsyncJob(type="coach_attempt_processing", status="running")
                )
                await upload_db.flush()
                publication = await asyncio.to_thread(
                    publish_staged_audio, staged, upload_destination
                )
                await upload_db.commit()
                publication.release()
                upload_committed.set()

            claim, _ = await asyncio.wait_for(
                asyncio.gather(
                    cleanup_claim(), upload_while_holding_database_write()
                ),
                timeout=3,
            )
            cleanup_result = await retention.delete_claimed_audio(claim)
            assert cleanup_result == "deleted"
            assert await retention.finalise_audio_cleanup(claim, cleanup_result)
            await cleanup_db.commit()
    finally:
        await engine.dispose()

    assert not original_path.exists()
    assert upload_destination.read_bytes() == staged_body


@pytest.mark.asyncio
async def test_content_retry_reclaims_after_independent_cleanup_failure(
    db_session, tmp_path: Path
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    cleanup_claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime.now(timezone.utc)
    )
    assert cleanup_claim is not None
    if cleanup_claim._deletion_lease is not None:
        cleanup_claim._deletion_lease.close()
    assert await retention.finalise_audio_cleanup(cleanup_claim, "delete_failed")

    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id
                )
            )
        ).all()
    )
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "failed_retryable"
            stage.last_error_code = "coach_evaluation_unavailable"
            stage.completed_at = datetime.utcnow()
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
            stage.completed_at = datetime.utcnow()
    seeded.evaluation.state = "failed"
    seeded.evaluation.diagnostics_json = {
        "processing_claim": seeded.evaluation.diagnostics_json["processing_claim"],
        "result": {"reason_code": "coach_evaluation_unavailable"},
    }
    seeded.attempt.attempt_state = "recoverable_error"
    seeded.attempt.evaluation_state = "failed"
    seeded.attempt.async_job_id = None
    seeded.session.conversation_state = "recoverable_error"
    seeded.session.recoverable_error_scope = "attempt_processing"
    seeded.session.recoverable_error_code = "coach_evaluation_unavailable"
    processing_job = await db_session.get(AsyncJob, seeded.evaluation.async_job_id)
    assert processing_job is not None
    processing_job.status = "failed"
    processing_job.error = "coach_evaluation_unavailable"
    await db_session.commit()
    retry_job = AsyncJob(type="coach_attempt_processing", status="pending")
    db_session.add(retry_job)
    await db_session.flush()
    retry_deadline = datetime.utcnow() + timedelta(minutes=15)

    retry_claim = await ConversationalSessionRepository(
        db_session
    ).claim_retry_processing(
        recording_id=seeded.attempt.id,
        job_id=retry_job.id,
        deadline=retry_deadline,
        expected_session_state_version=seeded.session.state_version,
    )

    assert retry_claim is not None
    retry_cleanup = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id
            == retry_claim.evaluation_version_id,
            InterviewAttemptStage.stage_name == "audio_cleanup",
        )
    )
    assert retry_cleanup is not None
    assert retry_cleanup.stage_state == "failed_retryable"
    assert retry_cleanup.reused_from_stage_id is None
    assert retry_cleanup.job_id == cleanup_claim.job_id
    assert retry_cleanup.claim_token is None
    assert retry_cleanup.job_deadline_at == cleanup_claim.deadline_at
    assert retry_cleanup.expected_processing_generation == retry_claim.processing_generation


@pytest.mark.parametrize(
    "retention_state", ("delete_pending", "deleted", "delete_failed")
)
@pytest.mark.asyncio
async def test_partition_rejects_processing_owned_cleanup_when_independent_expected(
    db_session, tmp_path: Path, retention_state: str
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.attempt.audio_retention_state = retention_state
    if retention_state == "deleted":
        seeded.attempt.audio_uri = None
    seeded.cleanup_stage.stage_state = "not_applicable"
    seeded.cleanup_stage.completed_at = datetime.utcnow()
    await db_session.commit()
    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id
                )
            )
        ).all()
    )

    assert seeded.cleanup_stage.job_id == seeded.evaluation.async_job_id
    assert seeded.cleanup_stage.claim_token == "processing-token"
    assert seeded.cleanup_stage.job_deadline_at == seeded.processing_deadline
    assert (
        await partition_current_processing_stages(
            db_session,
            attempt=seeded.attempt,
            evaluation=seeded.evaluation,
            stages=stages,
            processing_job_id=seeded.evaluation.async_job_id or "",
        )
        is None
    )


@pytest.mark.parametrize(
    "retention_state", ("delete_pending", "deleted", "delete_failed")
)
@pytest.mark.asyncio
async def test_processing_consumers_reject_processing_owned_cleanup_without_mutation(
    db_session, tmp_path: Path, retention_state: str
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    seeded.attempt.audio_retention_state = retention_state
    if retention_state == "deleted":
        seeded.attempt.audio_uri = None
    seeded.cleanup_stage.stage_state = "not_applicable"
    seeded.cleanup_stage.completed_at = datetime.utcnow()
    await db_session.commit()
    processing_claim = AttemptProcessingClaim(
        session_id=seeded.session.id,
        question_id=seeded.attempt.question_id or "",
        recording_id=seeded.attempt.id,
        transcript_version_id=seeded.attempt.current_transcript_version_id,
        evaluation_version_id=seeded.evaluation.id,
        processing_generation=seeded.attempt.processing_generation,
        job_id=seeded.evaluation.async_job_id or "",
        deadline_at=seeded.processing_deadline,
    )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    before_worker = await _processing_authority_signature(db_session, seeded)
    with pytest.raises(AttemptPipelineError, match="coach_attempt_stale_claim"):
        await _process_attempt_claim(
            processing_claim, session_factory=session_factory
        )
    assert await _processing_authority_signature(
        db_session, seeded
    ) == before_worker

    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id
                )
            )
        ).all()
    )
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "unavailable"
            stage.last_error_code = "coach_evaluation_unavailable"
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
        if stage.stage_name not in {
            "audio_persist",
            "transcription",
            "speech_analysis",
        }:
            stage.completed_at = datetime.utcnow()
    await db_session.flush()
    before_finalizer = await _processing_authority_signature(db_session, seeded)
    assert not await ConversationalSessionRepository(
        db_session
    ).finalise_attempt_processing(
        claim=processing_claim,
        result=AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={"answer_level": "not_assessed"},
            transcript_version_id=seeded.attempt.current_transcript_version_id,
            diagnostics={
                "code": "coach_evaluation_unavailable",
                "execution_mode": "deterministic_stub",
            },
        ),
    )
    assert await _processing_authority_signature(
        db_session, seeded
    ) == before_finalizer

    await _make_content_retryable(db_session, seeded)
    retry_job = AsyncJob(type="coach_attempt_processing", status="pending")
    db_session.add(retry_job)
    await db_session.flush()
    retry_deadline = datetime.utcnow() + timedelta(minutes=15)
    evaluation_count = int(
        await db_session.scalar(
            select(func.count(InterviewAttemptEvaluation.id)).where(
                InterviewAttemptEvaluation.recording_id == seeded.attempt.id
            )
        )
        or 0
    )
    stage_count = int(
        await db_session.scalar(
            select(func.count(InterviewAttemptStage.id)).where(
                InterviewAttemptStage.recording_id == seeded.attempt.id
            )
        )
        or 0
    )
    before_retry = await _processing_authority_signature(db_session, seeded)

    assert (
        await ConversationalSessionRepository(db_session).claim_retry_processing(
            recording_id=seeded.attempt.id,
            job_id=retry_job.id,
            deadline=retry_deadline,
            expected_session_state_version=seeded.session.state_version,
        )
        is None
    )
    assert await _processing_authority_signature(db_session, seeded) == before_retry
    assert (
        int(
            await db_session.scalar(
                select(func.count(InterviewAttemptEvaluation.id)).where(
                    InterviewAttemptEvaluation.recording_id == seeded.attempt.id
                )
            )
            or 0
        )
        == evaluation_count
    )
    assert (
        int(
            await db_session.scalar(
                select(func.count(InterviewAttemptStage.id)).where(
                    InterviewAttemptStage.recording_id == seeded.attempt.id
                )
            )
            or 0
        )
        == stage_count
    )
    await db_session.refresh(retry_job)
    assert retry_job.status == "pending"


@pytest.mark.parametrize(
    "forgery",
    ("missing", "job_type", "token", "deadline", "generation", "diagnostics", "state"),
)
@pytest.mark.asyncio
async def test_processing_finaliser_rejects_forged_independent_cleanup_row(
    db_session, tmp_path: Path, forgery: str
) -> None:
    seeded = await _seed_audio(db_session, tmp_path)
    retention = CoachRetentionService(db_session, media_root=tmp_path / "coach-media")
    cleanup_claim = await retention.claim_default_cleanup(
        seeded.attempt.id, datetime.now(timezone.utc)
    )
    assert cleanup_claim is not None
    assert await retention.delete_claimed_audio(cleanup_claim) == "deleted"
    assert await retention.finalise_audio_cleanup(cleanup_claim, "deleted")
    stages = list(
        (
            await db_session.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == seeded.attempt.id,
                    InterviewAttemptStage.evaluation_version_id
                    == seeded.evaluation.id,
                )
            )
        ).all()
    )
    cleanup = next(stage for stage in stages if stage.stage_name == "audio_cleanup")
    for stage in stages:
        if stage.stage_name == "content_evaluation":
            stage.stage_state = "unavailable"
            stage.last_error_code = "coach_evaluation_unavailable"
        elif stage.stage_name in {
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }:
            stage.stage_state = "not_applicable"
        if stage.stage_name != "audio_cleanup":
            stage.completed_at = datetime.utcnow()
    if forgery == "missing":
        await db_session.delete(cleanup)
    elif forgery == "job_type":
        cleanup_job = await db_session.get(AsyncJob, cleanup.job_id)
        assert cleanup_job is not None
        cleanup_job.type = "coach_attempt_processing"
    elif forgery == "token":
        cleanup.claim_token = "forged-terminal-token"
    elif forgery == "deadline":
        assert cleanup.job_deadline_at is not None
        cleanup.job_deadline_at += timedelta(seconds=1)
    elif forgery == "generation":
        cleanup.expected_processing_generation = 5
    elif forgery == "diagnostics":
        cleanup.diagnostics_json = {
            **(cleanup.diagnostics_json or {}),
            "source_audio_content_hash": "f" * 64,
        }
    else:
        cleanup.stage_state = "pending"
    await db_session.flush()
    processing_claim = AttemptProcessingClaim(
        session_id=seeded.session.id,
        question_id=seeded.attempt.question_id or "",
        recording_id=seeded.attempt.id,
        transcript_version_id=seeded.attempt.current_transcript_version_id,
        evaluation_version_id=seeded.evaluation.id,
        processing_generation=4,
        job_id=seeded.attempt.async_job_id or "",
        deadline_at=seeded.processing_deadline,
    )

    assert not await ConversationalSessionRepository(
        db_session
    ).finalise_attempt_processing(
        claim=processing_claim,
        result=AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={"answer_level": "not_assessed"},
            transcript_version_id=seeded.attempt.current_transcript_version_id,
            diagnostics={
                "code": "coach_evaluation_unavailable",
                "execution_mode": "deterministic_stub",
            },
        ),
    )
