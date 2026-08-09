"""Independent, ownership-fenced audio retention for conversational Coach."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.async_job import AsyncJob
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewAttemptUpload,
    InterviewSession,
    InterviewSessionEvent,
    SessionRecording,
)
from ..repositories.conversational_session_repository import (
    ConversationalSessionRepository,
    SessionEventInput,
    partition_current_processing_stages,
)
from .coach_media_storage import (
    CoachMediaError,
    OwnedAudioDeletionLease,
    open_verified_audio_deletion_lease,
    owned_audio_path_is_missing,
)


AudioCleanupResult = Literal["deleted", "delete_failed", "stale_claim"]


class _CleanupFenceLost(RuntimeError):
    """Roll back a cleanup publication whose exact aggregate changed."""


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _default_cleanup_is_due(
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stages: dict[str, InterviewAttemptStage],
    now: datetime,
) -> bool:
    """Apply the one canonical default-cleanup eligibility predicate."""
    cleanup = stages["audio_cleanup"]
    transcription = stages["transcription"]
    speech = stages["speech_analysis"]
    speech_terminal = speech.stage_state in {
        "completed",
        "reused",
        "unavailable",
        "not_applicable",
        "failed_terminal",
    }
    transcript_committed = bool(
        attempt.current_transcript_version_id
        and evaluation.transcript_version_id
        == attempt.current_transcript_version_id
        and transcription.stage_state in {"completed", "reused"}
    )
    failed_transcription_due = bool(
        transcription.stage_state
        in {"unavailable", "failed_retryable", "failed_terminal"}
        and transcription.completed_at is not None
        and now
        >= transcription.completed_at
        + timedelta(hours=settings.HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS)
    )
    active_cleanup = bool(
        cleanup.stage_state == "running"
        and (cleanup.job_deadline_at is None or cleanup.job_deadline_at > now)
    )
    return bool(
        attempt.audio_retention_policy == "delete_after_processing"
        and attempt.audio_retention_state
        in {"temporary", "delete_failed", "delete_pending"}
        and speech_terminal
        and (transcript_committed or failed_transcription_due)
        and not active_cleanup
    )


@dataclass(frozen=True)
class AudioCleanupClaim:
    session_id: str
    question_id: str | None
    recording_id: str
    evaluation_version_id: str
    stage_id: str
    processing_generation: int
    job_id: str
    claim_token: str
    deadline_at: datetime
    audio_uri: str
    audio_content_hash: str
    audio_retention_policy: str
    reason: Literal["default_cleanup", "explicit_delete"]
    _deletion_lease: OwnedAudioDeletionLease | None = field(
        repr=False, compare=False
    )


class CoachRetentionService:
    """Claim and finalise physical audio deletion independently of evaluation."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        media_root: Path | None = None,
    ) -> None:
        self.db = db
        self.repository = ConversationalSessionRepository(db)
        self.media_root = Path(media_root or settings.HATCH_COACH_MEDIA_ROOT)

    async def claim_default_cleanup(
        self, recording_id: str, now: datetime
    ) -> AudioCleanupClaim | None:
        return await self._claim_cleanup(
            recording_id,
            now=_naive_utc(now),
            reason="default_cleanup",
        )

    async def default_cleanup_is_due(
        self, recording_id: str, now: datetime
    ) -> bool:
        """Return eligibility without probing or mutating the media boundary."""
        now = _naive_utc(now)
        attempt = await self.db.scalar(
            select(SessionRecording)
            .where(SessionRecording.id == recording_id)
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or attempt.recording_type != "audio"
            or attempt.audio_uri is None
            or attempt.audio_content_hash is None
        ):
            return False
        session = await self.db.scalar(
            select(InterviewSession).where(
                InterviewSession.id == attempt.session_id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.deletion_state == "not_requested",
            )
        )
        if session is None:
            return False
        stage_rows = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                    )
                )
            ).all()
        )
        by_evaluation: dict[str, dict[str, InterviewAttemptStage]] = {}
        for row in stage_rows:
            by_evaluation.setdefault(row.evaluation_version_id, {})[
                row.stage_name
            ] = row
        candidates = [
            rows
            for rows in by_evaluation.values()
            if {"transcription", "speech_analysis", "audio_cleanup"}
            <= rows.keys()
        ]
        if len(candidates) != 1:
            return False
        stages = candidates[0]
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, stages["audio_cleanup"].evaluation_version_id
        )
        return bool(
            evaluation is not None
            and evaluation.recording_id == attempt.id
            and _default_cleanup_is_due(
                attempt=attempt,
                evaluation=evaluation,
                stages=stages,
                now=now,
            )
        )

    async def claim_explicit_cleanup(
        self, recording_id: str, now: datetime
    ) -> AudioCleanupClaim | None:
        return await self._claim_cleanup(
            recording_id,
            now=_naive_utc(now),
            reason="explicit_delete",
        )

    async def _claim_cleanup(
        self,
        recording_id: str,
        *,
        now: datetime,
        reason: Literal["default_cleanup", "explicit_delete"],
    ) -> AudioCleanupClaim | None:
        attempt = await self.db.scalar(
            select(SessionRecording)
            .where(SessionRecording.id == recording_id)
            .execution_options(populate_existing=True)
        )
        if attempt is None:
            return None
        session = await self.db.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == attempt.session_id)
            .execution_options(populate_existing=True)
        )
        if (
            session is None
            or session.experience_version != "conversational_v1"
            or session.deletion_state != "not_requested"
            or attempt.recording_type != "audio"
            or attempt.audio_uri is None
            or attempt.audio_content_hash is None
            or attempt.audio_retention_policy
            not in {"delete_after_processing", "retain_until_deleted"}
            or attempt.audio_retention_state
            not in {"temporary", "retained", "delete_failed", "delete_pending"}
        ):
            return None
        stage_rows = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                    )
                )
            ).all()
        )
        by_evaluation: dict[str, dict[str, InterviewAttemptStage]] = {}
        for row in stage_rows:
            by_evaluation.setdefault(row.evaluation_version_id, {})[
                row.stage_name
            ] = row
        candidates = [
            rows
            for rows in by_evaluation.values()
            if {"transcription", "speech_analysis", "audio_cleanup"} <= rows.keys()
        ]
        if len(candidates) != 1:
            return None
        stages = candidates[0]
        cleanup = stages["audio_cleanup"]
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, cleanup.evaluation_version_id
        )
        if evaluation is None or evaluation.recording_id != attempt.id:
            return None
        if reason == "default_cleanup" and not _default_cleanup_is_due(
            attempt=attempt,
            evaluation=evaluation,
            stages=stages,
            now=now,
        ):
            return None
        prior_cleanup_job_id = cleanup.job_id

        try:
            lease = open_verified_audio_deletion_lease(
                self.media_root,
                Path(attempt.audio_uri),
                attempt.audio_content_hash,
            )
        except CoachMediaError:
            return None
        # Global lock order: media preflight must be released before the durable
        # database claim. Physical mutation reacquires only after that claim commits.
        lease.close()
        job = AsyncJob(type="coach_audio_cleanup", status="running")
        self.db.add(job)
        await self.db.flush()
        token = str(uuid.uuid4())
        deadline = now + timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS
        )
        try:
            async with self.db.begin_nested():
                attempt_change = await self.db.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == attempt.id,
                        SessionRecording.session_id == session.id,
                        SessionRecording.processing_generation
                        == attempt.processing_generation,
                        SessionRecording.audio_uri == attempt.audio_uri,
                        SessionRecording.audio_content_hash
                        == attempt.audio_content_hash,
                        SessionRecording.audio_retention_policy
                        == attempt.audio_retention_policy,
                        SessionRecording.audio_retention_state.in_(
                            ("temporary", "retained", "delete_failed", "delete_pending")
                        ),
                    )
                    .values(audio_retention_state="delete_pending")
                )
                stage_change = await self.db.execute(
                    update(InterviewAttemptStage)
                    .where(
                        InterviewAttemptStage.id == cleanup.id,
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.evaluation_version_id == evaluation.id,
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                        InterviewAttemptStage.stage_state.in_(
                            (
                                "pending",
                                "not_started",
                                "not_applicable",
                                "failed_retryable",
                                "failed_terminal",
                                "completed",
                                "running",
                            )
                        ),
                    )
                    .values(
                        stage_state="running",
                        job_id=job.id,
                        claim_token=token,
                        job_deadline_at=deadline,
                        started_at=now,
                        completed_at=None,
                        last_error_code=None,
                        attempt_count=InterviewAttemptStage.attempt_count + 1,
                    )
                )
                if attempt_change.rowcount != 1 or stage_change.rowcount != 1:
                    raise RuntimeError("stale cleanup claim")
                if prior_cleanup_job_id and prior_cleanup_job_id != job.id:
                    await self.db.execute(
                        update(AsyncJob)
                        .where(
                            AsyncJob.id == prior_cleanup_job_id,
                            AsyncJob.type == "coach_audio_cleanup",
                            AsyncJob.status.in_(("pending", "running")),
                        )
                        .values(
                            status="failed",
                            result_json=None,
                            error="coach_audio_cleanup_failed",
                            updated_at=now,
                        )
                    )
                await self.repository.append_session_events(
                    session_id=session.id,
                    events=(
                        SessionEventInput(
                            event_type="audio_cleanup_claimed",
                            actor_type=(
                                "candidate"
                                if reason == "explicit_delete"
                                else "worker"
                            ),
                            state_version=session.state_version,
                            state_before=session.conversation_state,
                            state_after=session.conversation_state,
                            question_id=attempt.question_id,
                            recording_id=attempt.id,
                            payload_json={"reason": reason},
                        ),
                    ),
                )
                await self.db.flush()
        except BaseException:
            await self.db.rollback()
            return None
        return AudioCleanupClaim(
            session_id=session.id,
            question_id=attempt.question_id,
            recording_id=attempt.id,
            evaluation_version_id=evaluation.id,
            stage_id=cleanup.id,
            processing_generation=attempt.processing_generation,
            job_id=job.id,
            claim_token=token,
            deadline_at=deadline,
            audio_uri=attempt.audio_uri,
            audio_content_hash=attempt.audio_content_hash,
            audio_retention_policy=attempt.audio_retention_policy,
            reason=reason,
            _deletion_lease=None,
        )

    async def delete_claimed_audio(
        self, claim: AudioCleanupClaim
    ) -> AudioCleanupResult:
        """Fence DB ownership, then mutate media synchronously, then release."""
        owned = await self.db.scalar(
            select(SessionRecording.id)
            .join(
                InterviewAttemptStage,
                InterviewAttemptStage.recording_id == SessionRecording.id,
            )
            .where(
                SessionRecording.id == claim.recording_id,
                SessionRecording.session_id == claim.session_id,
                SessionRecording.processing_generation == claim.processing_generation,
                SessionRecording.audio_uri == claim.audio_uri,
                SessionRecording.audio_content_hash == claim.audio_content_hash,
                SessionRecording.audio_retention_policy
                == claim.audio_retention_policy,
                SessionRecording.audio_retention_state == "delete_pending",
                InterviewAttemptStage.id == claim.stage_id,
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id,
                InterviewAttemptStage.stage_name == "audio_cleanup",
                InterviewAttemptStage.stage_state == "running",
                InterviewAttemptStage.job_id == claim.job_id,
                InterviewAttemptStage.claim_token == claim.claim_token,
                InterviewAttemptStage.expected_processing_generation
                == claim.processing_generation,
                InterviewAttemptStage.job_deadline_at == claim.deadline_at,
            )
        )
        if owned is None:
            if claim._deletion_lease is not None:
                claim._deletion_lease.close()
            return "stale_claim"
        lease = claim._deletion_lease
        if lease is None:
            source = Path(claim.audio_uri)
            if owned_audio_path_is_missing(self.media_root, source):
                return "deleted"
            try:
                lease = open_verified_audio_deletion_lease(
                    self.media_root, source, claim.audio_content_hash
                )
            except CoachMediaError:
                return "delete_failed"
        try:
            deleted = lease.delete_owned()
        except CoachMediaError:
            result: AudioCleanupResult = "delete_failed"
        else:
            result = "deleted" if deleted else "stale_claim"
        finally:
            lease.close()
        return result

    async def recover_expired_cleanup(
        self, recording_id: str, now: datetime
    ) -> bool:
        """Finish an exact expired claim whose worker unlinked before publication."""
        now = _naive_utc(now)
        attempt = await self.db.get(SessionRecording, recording_id)
        if (
            attempt is None
            or attempt.audio_retention_state != "delete_pending"
            or attempt.audio_uri is None
            or attempt.audio_content_hash is None
        ):
            return False
        cleanup = await self.db.scalar(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.recording_id == attempt.id,
                InterviewAttemptStage.stage_name == "audio_cleanup",
                InterviewAttemptStage.stage_state == "running",
                InterviewAttemptStage.job_deadline_at <= now,
            )
        )
        if (
            cleanup is None
            or cleanup.job_id is None
            or cleanup.claim_token is None
            or cleanup.job_deadline_at is None
        ):
            return False
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, cleanup.evaluation_version_id
        )
        if evaluation is None or evaluation.async_job_id is None:
            return False
        stages = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.evaluation_version_id == evaluation.id,
                    )
                )
            ).all()
        )
        partition = await partition_current_processing_stages(
            self.db,
            attempt=attempt,
            evaluation=evaluation,
            stages=stages,
            processing_job_id=evaluation.async_job_id,
        )
        if partition is None or partition[1] is None:
            return False
        event = await self.db.scalar(
            select(InterviewSessionEvent)
            .where(
                InterviewSessionEvent.session_id == attempt.session_id,
                InterviewSessionEvent.recording_id == attempt.id,
                InterviewSessionEvent.event_type == "audio_cleanup_claimed",
            )
            .order_by(InterviewSessionEvent.sequence_number.desc())
            .limit(1)
        )
        reason = (
            "explicit_delete"
            if event is not None
            and (event.payload_json or {}).get("reason") == "explicit_delete"
            else "default_cleanup"
        )
        claim = AudioCleanupClaim(
            session_id=attempt.session_id,
            question_id=attempt.question_id,
            recording_id=attempt.id,
            evaluation_version_id=evaluation.id,
            stage_id=cleanup.id,
            processing_generation=attempt.processing_generation,
            job_id=cleanup.job_id,
            claim_token=cleanup.claim_token,
            deadline_at=cleanup.job_deadline_at,
            audio_uri=attempt.audio_uri,
            audio_content_hash=attempt.audio_content_hash,
            audio_retention_policy=attempt.audio_retention_policy or "",
            reason=reason,
            _deletion_lease=None,
        )
        if owned_audio_path_is_missing(self.media_root, Path(claim.audio_uri)):
            return await self.finalise_reconciled_audio_cleanup(claim, "deleted")
        preclaim_result = await self.classify_cleanup_preclaim(recording_id)
        if preclaim_result != "delete_failed":
            return False
        return await self.record_cleanup_claim_failure(
            recording_id,
            now,
            result="delete_failed",
            reason=reason,
            actor_type="reconciler",
        )

    async def record_cleanup_claim_failure(
        self,
        recording_id: str,
        now: datetime,
        *,
        result: Literal["deleted", "delete_failed"] = "delete_failed",
        reason: Literal["default_cleanup", "explicit_delete"] = "default_cleanup",
        actor_type: Literal["candidate", "worker", "reconciler"] = "worker",
    ) -> bool:
        """Publish one fenced terminal result for a pre-claim media failure."""
        now = _naive_utc(now)
        attempt = await self.db.scalar(
            select(SessionRecording)
            .where(SessionRecording.id == recording_id)
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or attempt.recording_type != "audio"
            or attempt.audio_uri is None
            or attempt.audio_content_hash is None
            or attempt.audio_retention_policy
            not in {"delete_after_processing", "retain_until_deleted"}
            or attempt.audio_retention_state
            not in {"temporary", "retained", "delete_failed", "delete_pending"}
            or (
                reason == "default_cleanup"
                and (
                    attempt.audio_retention_policy != "delete_after_processing"
                    or attempt.audio_retention_state
                    not in {"temporary", "delete_failed", "delete_pending"}
                )
            )
        ):
            return False
        media_missing = result == "deleted"
        cleanup_rows = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.stage_name == "audio_cleanup",
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                    )
                )
            ).all()
        )
        if len(cleanup_rows) != 1:
            return False
        cleanup = cleanup_rows[0]
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, cleanup.evaluation_version_id
        )
        session = await self.db.get(InterviewSession, attempt.session_id)
        if (
            evaluation is None
            or evaluation.recording_id != attempt.id
            or session is None
            or session.experience_version != "conversational_v1"
            or session.deletion_state != "not_requested"
        ):
            return False
        allowed_stage_states = {"pending", "not_started"}
        if media_missing or reason == "explicit_delete":
            allowed_stage_states.add("failed_retryable")
        if (
            cleanup.stage_state == "running"
            and cleanup.job_deadline_at is not None
            and cleanup.job_deadline_at <= now
        ):
            allowed_stage_states.add("running")
        if cleanup.stage_state not in allowed_stage_states:
            return False
        prior_attempt_state = attempt.audio_retention_state
        prior_attempt_version = attempt.attempt_version
        prior_session_state_version = session.state_version
        prior_retention_version = session.retention_version
        prior_stage_state = cleanup.stage_state
        prior_stage_job_id = cleanup.job_id
        prior_stage_claim_token = cleanup.claim_token
        prior_stage_deadline = cleanup.job_deadline_at
        prior_stage_attempt_count = cleanup.attempt_count
        target_state = "deleted" if media_missing else "delete_failed"
        target_stage = "completed" if media_missing else "failed_retryable"
        event_type = "audio_deleted" if media_missing else "audio_delete_failed"
        job_status = "done" if media_missing else "failed"
        deadline = now + timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS
        )
        try:
            async with self.db.begin_nested():
                job = AsyncJob(
                    type="coach_audio_cleanup",
                    status=job_status,
                    result_json=(
                        '{"result":"deleted"}' if media_missing else None
                    ),
                    error=(None if media_missing else "coach_audio_deletion_failed"),
                    updated_at=now,
                )
                self.db.add(job)
                await self.db.flush()
                attempt_values: dict[str, object] = {
                    "audio_retention_state": target_state,
                    "attempt_version": SessionRecording.attempt_version + 1,
                }
                if media_missing:
                    attempt_values.update(
                        {"audio_uri": None, "audio_deleted_at": now}
                    )
                attempt_change = await self.db.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == attempt.id,
                        SessionRecording.session_id == session.id,
                        SessionRecording.processing_generation
                        == attempt.processing_generation,
                        SessionRecording.attempt_version == prior_attempt_version,
                        SessionRecording.audio_retention_state == prior_attempt_state,
                        SessionRecording.audio_uri == attempt.audio_uri,
                        SessionRecording.audio_content_hash
                        == attempt.audio_content_hash,
                        SessionRecording.audio_retention_policy
                        == attempt.audio_retention_policy,
                    )
                    .values(**attempt_values)
                )
                stage_change = await self.db.execute(
                    update(InterviewAttemptStage)
                    .where(
                        InterviewAttemptStage.id == cleanup.id,
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.evaluation_version_id
                        == evaluation.id,
                        InterviewAttemptStage.stage_name == "audio_cleanup",
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                        InterviewAttemptStage.stage_state == prior_stage_state,
                        InterviewAttemptStage.job_id == prior_stage_job_id,
                        InterviewAttemptStage.claim_token
                        == prior_stage_claim_token,
                        InterviewAttemptStage.job_deadline_at
                        == prior_stage_deadline,
                        InterviewAttemptStage.attempt_count
                        == prior_stage_attempt_count,
                    )
                    .values(
                        stage_state=target_stage,
                        job_id=job.id,
                        claim_token=None,
                        started_at=now,
                        completed_at=now,
                        job_deadline_at=deadline,
                        attempt_count=InterviewAttemptStage.attempt_count + 1,
                        last_error_code=(
                            None if media_missing else "coach_audio_deletion_failed"
                        ),
                    )
                )
                session_change = await self.db.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session.id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.state_version
                        == prior_session_state_version,
                        InterviewSession.retention_version
                        == prior_retention_version,
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        state_version=InterviewSession.state_version + 1,
                        retention_version=InterviewSession.retention_version + 1,
                    )
                    .returning(InterviewSession.state_version)
                )
                state_version = session_change.scalar_one_or_none()
                if (
                    attempt_change.rowcount != 1
                    or stage_change.rowcount != 1
                    or state_version is None
                ):
                    raise _CleanupFenceLost
                if (
                    prior_stage_job_id is not None
                    and prior_stage_job_id != job.id
                    and prior_stage_state == "running"
                ):
                    await self.db.execute(
                        update(AsyncJob)
                        .where(
                            AsyncJob.id == prior_stage_job_id,
                            AsyncJob.type == "coach_audio_cleanup",
                            AsyncJob.status.in_(("pending", "running")),
                        )
                        .values(
                            status="failed",
                            result_json=None,
                            error="coach_audio_deletion_failed",
                            updated_at=now,
                        )
                    )
                await self.repository.append_session_events(
                    session_id=session.id,
                    events=(
                        SessionEventInput(
                            event_type=event_type,
                            actor_type=actor_type,
                            state_version=state_version,
                            state_before=session.conversation_state,
                            state_after=session.conversation_state,
                            question_id=attempt.question_id,
                            recording_id=attempt.id,
                            payload_json={"reason": reason},
                        ),
                    ),
                )
                await self.db.flush()
        except _CleanupFenceLost:
            return False
        return True

    async def classify_cleanup_preclaim(
        self, recording_id: str
    ) -> Literal["deleted", "delete_failed"] | None:
        """Classify only a missing leaf or a verified media-boundary failure."""
        attempt = await self.db.scalar(
            select(SessionRecording)
            .where(SessionRecording.id == recording_id)
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or attempt.audio_uri is None
            or attempt.audio_content_hash is None
        ):
            return None
        source = Path(attempt.audio_uri)
        if owned_audio_path_is_missing(self.media_root, source):
            return "deleted"
        try:
            lease = open_verified_audio_deletion_lease(
                self.media_root, source, attempt.audio_content_hash
            )
        except CoachMediaError:
            return "delete_failed"
        lease.close()
        return None

    async def finalise_audio_cleanup(
        self, claim: AudioCleanupClaim, result: AudioCleanupResult
    ) -> bool:
        return await self._finalise_audio_cleanup(claim, result, actor_type=None)

    async def finalise_reconciled_audio_cleanup(
        self, claim: AudioCleanupClaim, result: AudioCleanupResult
    ) -> bool:
        """Finalise cleanup whose database mutation is reconciliation-owned."""
        return await self._finalise_audio_cleanup(
            claim, result, actor_type="reconciler"
        )

    async def _finalise_audio_cleanup(
        self,
        claim: AudioCleanupClaim,
        result: AudioCleanupResult,
        *,
        actor_type: Literal["reconciler"] | None,
    ) -> bool:
        if result == "stale_claim":
            return False
        now = datetime.utcnow()
        target_state = "deleted" if result == "deleted" else "delete_failed"
        target_stage = "completed" if result == "deleted" else "failed_retryable"
        event_type = "audio_deleted" if result == "deleted" else "audio_delete_failed"
        try:
            async with self.db.begin_nested():
                attempt_values: dict[str, object] = {
                    "audio_retention_state": target_state,
                    "attempt_version": SessionRecording.attempt_version + 1,
                }
                if result == "deleted":
                    attempt_values.update(
                        {"audio_uri": None, "audio_deleted_at": now}
                    )
                attempt_change = await self.db.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.processing_generation
                        == claim.processing_generation,
                        SessionRecording.audio_uri == claim.audio_uri,
                        SessionRecording.audio_content_hash
                        == claim.audio_content_hash,
                        SessionRecording.audio_retention_policy
                        == claim.audio_retention_policy,
                        SessionRecording.audio_retention_state == "delete_pending",
                    )
                    .values(**attempt_values)
                )
                stage_change = await self.db.execute(
                    update(InterviewAttemptStage)
                    .where(
                        InterviewAttemptStage.id == claim.stage_id,
                        InterviewAttemptStage.recording_id == claim.recording_id,
                        InterviewAttemptStage.evaluation_version_id
                        == claim.evaluation_version_id,
                        InterviewAttemptStage.stage_name == "audio_cleanup",
                        InterviewAttemptStage.stage_state == "running",
                        InterviewAttemptStage.job_id == claim.job_id,
                        InterviewAttemptStage.claim_token == claim.claim_token,
                        InterviewAttemptStage.expected_processing_generation
                        == claim.processing_generation,
                        InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                    )
                    .values(
                        stage_state=target_stage,
                        completed_at=now,
                        last_error_code=(
                            None
                            if result == "deleted"
                            else "coach_audio_deletion_failed"
                        ),
                        claim_token=None,
                    )
                )
                session_change = await self.db.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        state_version=InterviewSession.state_version + 1,
                        retention_version=InterviewSession.retention_version + 1,
                    )
                    .returning(InterviewSession.state_version)
                )
                job_change = await self.db.execute(
                    update(AsyncJob)
                    .where(
                        AsyncJob.id == claim.job_id,
                        AsyncJob.type == "coach_audio_cleanup",
                        AsyncJob.status.in_(("pending", "running")),
                    )
                    .values(
                        status="done" if result == "deleted" else "failed",
                        result_json=(
                            '{"result":"deleted"}'
                            if result == "deleted"
                            else None
                        ),
                        error=(
                            None
                            if result == "deleted"
                            else "coach_audio_deletion_failed"
                        ),
                        updated_at=now,
                    )
                )
                state_version = session_change.scalar_one_or_none()
                if (
                    attempt_change.rowcount != 1
                    or stage_change.rowcount != 1
                    or state_version is None
                    or job_change.rowcount != 1
                ):
                    raise RuntimeError("stale cleanup finalisation")
                if result == "deleted":
                    await self.db.execute(
                        update(InterviewAttemptUpload)
                        .where(
                            InterviewAttemptUpload.attempt_id == claim.recording_id,
                            InterviewAttemptUpload.storage_uri == claim.audio_uri,
                            InterviewAttemptUpload.content_sha256
                            == claim.audio_content_hash,
                            InterviewAttemptUpload.result_state == "completed",
                        )
                        .values(result_state="deleted", completed_at=now)
                    )
                session = await self.db.get(InterviewSession, claim.session_id)
                await self.repository.append_session_events(
                    session_id=claim.session_id,
                    events=(
                        SessionEventInput(
                            event_type=event_type,
                            actor_type=(
                                actor_type
                                or (
                                    "candidate"
                                    if claim.reason == "explicit_delete"
                                    else "worker"
                                )
                            ),
                            state_version=state_version,
                            state_before=(
                                session.conversation_state if session else None
                            ),
                            state_after=(
                                session.conversation_state if session else None
                            ),
                            question_id=claim.question_id,
                            recording_id=claim.recording_id,
                            payload_json={"reason": claim.reason},
                        ),
                    ),
                )
                await self.db.flush()
        except RuntimeError:
            if result == "deleted":
                return await self._finalise_deleted_into_current_authority(
                    claim, now, actor_type=actor_type
                )
            return False
        return True

    async def _finalise_deleted_into_current_authority(
        self,
        claim: AudioCleanupClaim,
        now: datetime,
        *,
        actor_type: Literal["reconciler"] | None,
    ) -> bool:
        """Publish a proven unlink after a current processing generation won."""
        from .coach_processing_snapshot import (
            current_processing_graph_reuse_is_valid,
            exact_processing_snapshot,
        )

        attempt = await self.db.scalar(
            select(SessionRecording)
            .where(SessionRecording.id == claim.recording_id)
            .execution_options(populate_existing=True)
        )
        session = await self.db.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == claim.session_id)
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or session is None
            or attempt.session_id != claim.session_id
            or attempt.processing_generation <= claim.processing_generation
            or attempt.audio_uri != claim.audio_uri
            or attempt.audio_content_hash != claim.audio_content_hash
            or attempt.audio_retention_policy != claim.audio_retention_policy
            or attempt.audio_retention_state != "delete_pending"
            or attempt.async_job_id is None
            or attempt.attempt_state != "pending_processing"
            or session.experience_version != "conversational_v1"
            or session.deletion_state != "not_requested"
        ):
            return False
        evaluations = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptEvaluation).where(
                        InterviewAttemptEvaluation.recording_id == attempt.id,
                        InterviewAttemptEvaluation.async_job_id
                        == attempt.async_job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.diagnostics_json[
                            "processing_claim"
                        ]["processing_generation"].as_integer()
                        == attempt.processing_generation,
                    )
                )
            ).all()
        )
        evaluation = evaluations[0] if len(evaluations) == 1 else None
        job = await self.db.get(AsyncJob, attempt.async_job_id)
        if evaluation is None or job is None:
            return False
        stages = list(
            (
                await self.db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.evaluation_version_id
                        == evaluation.id,
                    )
                )
            ).all()
        )
        if len(stages) != 8:
            return False
        snapshot = exact_processing_snapshot(
            session=session,
            attempt=attempt,
            evaluation=evaluation,
            job=job,
            stages=stages,
        )
        if (
            snapshot is None
            or job.status not in {"pending", "running"}
            or not await current_processing_graph_reuse_is_valid(
                self.db,
                attempt=attempt,
                evaluation=evaluation,
                stages=stages,
                snapshot=snapshot,
            )
        ):
            return False
        current_cleanup_rows = [
            stage for stage in stages if stage.stage_name == "audio_cleanup"
        ]
        if len(current_cleanup_rows) != 1:
            return False
        current_cleanup = current_cleanup_rows[0]
        if current_cleanup.stage_state not in {"pending", "not_started"}:
            return False
        old_cleanup = await self.db.get(InterviewAttemptStage, claim.stage_id)
        old_job = await self.db.get(AsyncJob, claim.job_id)
        if (
            old_cleanup is None
            or old_job is None
            or old_cleanup.recording_id != claim.recording_id
            or old_cleanup.evaluation_version_id != claim.evaluation_version_id
            or old_cleanup.stage_name != "audio_cleanup"
            or old_cleanup.stage_state != "running"
            or old_cleanup.job_id != claim.job_id
            or old_cleanup.claim_token != claim.claim_token
            or old_cleanup.expected_processing_generation
            != claim.processing_generation
            or old_cleanup.job_deadline_at != claim.deadline_at
            or old_job.type != "coach_audio_cleanup"
            or old_job.status not in {"pending", "running"}
        ):
            return False
        prior_attempt_version = attempt.attempt_version
        prior_current_evaluation_id = attempt.current_evaluation_version_id
        prior_session_version = session.state_version
        prior_retention_version = session.retention_version
        try:
            async with self.db.begin_nested():
                attempt_change = await self.db.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == attempt.id,
                        SessionRecording.session_id == session.id,
                        SessionRecording.processing_generation
                        == attempt.processing_generation,
                        SessionRecording.current_evaluation_version_id
                        == prior_current_evaluation_id,
                        SessionRecording.async_job_id == job.id,
                        SessionRecording.attempt_version == prior_attempt_version,
                        SessionRecording.audio_uri == claim.audio_uri,
                        SessionRecording.audio_content_hash
                        == claim.audio_content_hash,
                        SessionRecording.audio_retention_policy
                        == claim.audio_retention_policy,
                        SessionRecording.audio_retention_state == "delete_pending",
                    )
                    .values(
                        audio_uri=None,
                        audio_retention_state="deleted",
                        audio_deleted_at=now,
                        attempt_version=SessionRecording.attempt_version + 1,
                    )
                )
                old_stage_change = await self.db.execute(
                    update(InterviewAttemptStage)
                    .where(
                        InterviewAttemptStage.id == claim.stage_id,
                        InterviewAttemptStage.recording_id == claim.recording_id,
                        InterviewAttemptStage.evaluation_version_id
                        == claim.evaluation_version_id,
                        InterviewAttemptStage.stage_name == "audio_cleanup",
                        InterviewAttemptStage.stage_state == "running",
                        InterviewAttemptStage.job_id == claim.job_id,
                        InterviewAttemptStage.claim_token == claim.claim_token,
                        InterviewAttemptStage.expected_processing_generation
                        == claim.processing_generation,
                        InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                    )
                    .values(
                        stage_state="completed",
                        completed_at=now,
                        last_error_code=None,
                        claim_token=None,
                    )
                )
                current_stage_change = await self.db.execute(
                    update(InterviewAttemptStage)
                    .where(
                        InterviewAttemptStage.id == current_cleanup.id,
                        InterviewAttemptStage.recording_id == attempt.id,
                        InterviewAttemptStage.evaluation_version_id == evaluation.id,
                        InterviewAttemptStage.stage_name == "audio_cleanup",
                        InterviewAttemptStage.stage_state
                        == current_cleanup.stage_state,
                        InterviewAttemptStage.job_id == job.id,
                        InterviewAttemptStage.claim_token
                        == current_cleanup.claim_token,
                        InterviewAttemptStage.expected_processing_generation
                        == attempt.processing_generation,
                        InterviewAttemptStage.job_deadline_at == snapshot.deadline,
                    )
                    .values(
                        stage_state="completed",
                        job_id=claim.job_id,
                        claim_token=None,
                        reused_from_stage_id=None,
                        started_at=old_cleanup.started_at,
                        completed_at=now,
                        job_deadline_at=claim.deadline_at,
                        last_error_code=None,
                    )
                )
                job_change = await self.db.execute(
                    update(AsyncJob)
                    .where(
                        AsyncJob.id == claim.job_id,
                        AsyncJob.type == "coach_audio_cleanup",
                        AsyncJob.status.in_(("pending", "running")),
                    )
                    .values(
                        status="done",
                        result_json='{"result":"deleted"}',
                        error=None,
                        updated_at=now,
                    )
                )
                session_change = await self.db.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session.id,
                        InterviewSession.state_version == prior_session_version,
                        InterviewSession.retention_version
                        == prior_retention_version,
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        state_version=InterviewSession.state_version + 1,
                        retention_version=InterviewSession.retention_version + 1,
                    )
                    .returning(InterviewSession.state_version)
                )
                state_version = session_change.scalar_one_or_none()
                if (
                    attempt_change.rowcount != 1
                    or old_stage_change.rowcount != 1
                    or current_stage_change.rowcount != 1
                    or job_change.rowcount != 1
                    or state_version is None
                ):
                    raise _CleanupFenceLost
                await self.db.execute(
                    update(InterviewAttemptUpload)
                    .where(
                        InterviewAttemptUpload.attempt_id == claim.recording_id,
                        InterviewAttemptUpload.storage_uri == claim.audio_uri,
                        InterviewAttemptUpload.content_sha256
                        == claim.audio_content_hash,
                        InterviewAttemptUpload.result_state == "completed",
                    )
                    .values(result_state="deleted", completed_at=now)
                )
                await self.repository.append_session_events(
                    session_id=session.id,
                    events=(
                        SessionEventInput(
                            event_type="audio_deleted",
                            actor_type=(
                                actor_type
                                or (
                                    "candidate"
                                    if claim.reason == "explicit_delete"
                                    else "worker"
                                )
                            ),
                            state_version=state_version,
                            state_before=session.conversation_state,
                            state_after=session.conversation_state,
                            question_id=claim.question_id,
                            recording_id=claim.recording_id,
                            payload_json={"reason": claim.reason},
                        ),
                    ),
                )
                await self.db.flush()
        except _CleanupFenceLost:
            return False
        return True

    async def delete_audio(self, recording_id: str) -> AudioCleanupResult:
        attempt = await self.db.get(SessionRecording, recording_id)
        if attempt is None:
            return "stale_claim"
        if attempt.audio_uri is None and attempt.audio_retention_state == "deleted":
            return "deleted"
        claim = await self._claim_cleanup(
            recording_id,
            now=datetime.utcnow(),
            reason="explicit_delete",
        )
        if claim is None:
            return "delete_failed"
        try:
            await self.db.commit()
        except BaseException:
            if claim._deletion_lease is not None:
                claim._deletion_lease.close()
            raise
        try:
            result = await self.delete_claimed_audio(claim)
        except BaseException:
            if claim._deletion_lease is not None:
                claim._deletion_lease.close()
            raise
        if result != "stale_claim":
            await self.finalise_audio_cleanup(claim, result)
        return result


CoachRetention = CoachRetentionService
