"""Atomic persistence primitives for conversational Coach sessions.

Most methods flush but never commit, so their caller owns the short transaction.
Audio publication is the exception: its explicit commit method couples database
durability to filesystem compensation before a response can be returned.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Sequence

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.async_job import AsyncJob
from ..models.coach_session import (
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
from ..schemas.coach_conversation import (
    AttemptAudioUploadRead,
    ConversationCommandRequest,
    SAFE_TOKEN_RE,
)
from ..services.coach_media_storage import (
    CoachMediaError,
    OwnedAudioPublication,
    StagedAudio,
    cleanup_staged_audio,
    open_verified_audio_read_lease,
    owned_audio_path_is_file,
    publish_staged_audio,
)
from ..services.coach_conversational_contracts import (
    AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS,
    EVIDENCE_GROUNDING_CONTRACT,
    ERROR_REGISTRY,
    FOLLOW_UP_CONTRACT,
    RUBRIC_CONTRACT,
    TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS,
)


_AUDIO_PUBLICATION_COMPENSATION_ATTEMPTS = 2


class ConversationalRepositoryError(RuntimeError):
    """Base class for stable repository contract failures."""


class CommandIdempotencyConflict(ConversationalRepositoryError):
    """A command ID was reused for a semantically different request."""


class ConversationVersionConflict(ConversationalRepositoryError):
    """A new command was based on a stale session projection."""

    def __init__(self, *, current_state_version: int, current_state: str | None):
        super().__init__("coach_conversation_version_conflict")
        self.current_state_version = current_state_version
        self.current_state = current_state


class AttemptReservationConflict(ConversationalRepositoryError):
    """An attempt ID or active-attempt fence rejected a reservation."""


class AttemptLimitExhausted(ConversationalRepositoryError):
    """The monotonic per-question attempt budget is exhausted."""


class StaleVersion(ConversationalRepositoryError):
    """A conditional version-row mutation lost its ownership fence."""


@dataclass(frozen=True)
class CommandClaim:
    record_id: str
    session_id: str
    command_id: str
    request_hash: str
    is_duplicate: bool
    result_state: str
    result_json: dict[str, object] | None


@dataclass(frozen=True)
class SessionEventInput:
    event_type: str
    actor_type: Literal["candidate", "system", "worker", "reconciler", "migration"]
    state_version: int
    state_before: str | None = None
    state_after: str | None = None
    question_id: str | None = None
    recording_id: str | None = None
    command_id: str | None = None
    payload_json: dict[str, object] | None = None


@dataclass(frozen=True)
class AttemptReservation:
    attempt: SessionRecording
    is_duplicate: bool
    pending_hint_types: tuple[str, ...]


@dataclass(frozen=True)
class AttemptProcessingClaim:
    session_id: str
    question_id: str
    recording_id: str
    transcript_version_id: str | None
    evaluation_version_id: str
    processing_generation: int
    job_id: str
    deadline_at: datetime


@dataclass(frozen=True)
class _AttemptProcessingFence:
    expected_audio_content_hash: str | None
    source_transcript_version_id: str | None
    expected_session_state_version: int
    processing_contract_version: str
    claim_token: str


@dataclass(frozen=True)
class AttemptProcessingSnapshot:
    claim: AttemptProcessingClaim
    attempt_state: str
    evaluation_state: str


@dataclass(frozen=True)
class AttemptProcessingResult:
    evaluation_state: Literal["completed", "unavailable"]
    evaluation_json: dict[str, object]
    transcript_version_id: str | None
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class AcceptanceResult:
    accepted: bool
    attempt_id: str
    state_version: int | None
    current_state_version: int | None
    current_state: str | None
    evaluation_version_id: str | None
    evaluation_state: str | None


@dataclass(frozen=True)
class FollowUpAdmissionClaim:
    session_id: str
    root_question_id: str
    parent_question_id: str
    source_recording_id: str
    source_transcript_version_id: str
    expected_state_version: int
    expected_acceptance_generation: int
    question: str
    reason: str
    target_dimension: str
    aggregation_role: str
    duplicate_key: str
    context_json: dict[str, object]
    generation_json: dict[str, object]


@dataclass(frozen=True)
class FollowUpCreationResult:
    created: bool
    question_id: str | None
    state_version: int | None


def canonical_request_hash(
    request: ConversationCommandRequest, *, session_id: str
) -> str:
    """Hash the validated semantic command envelope, excluding ``command_id``."""
    canonical = {
        "session_id": session_id,
        "command_type": request.command_type,
        "expected_state_version": request.expected_state_version,
        "payload": request.payload.model_dump(
            mode="json", exclude_unset=False, exclude_none=False
        ),
        "contract_version": request.contract_version,
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_EVENT_ENUM_KEYS = frozenset(
    {
        "reason",
        "reason_code",
        "code",
        "error",
        "error_code",
        "contract",
        "contract_version",
        "state",
        "status",
        "stage",
        "stage_name",
        "scope",
        "result",
        "policy",
        "hint_type",
        "execution_mode",
    }
)
_EVENT_ENUM_LIST_KEYS = frozenset({"hint_types", "stages", "reason_codes"})
_EVENT_CONTAINER_KEYS = frozenset({"diagnostics"})
_EVENT_BOOLEAN_KEYS = frozenset(
    {"retryable", "available", "enabled", "deleted", "reused", "terminal"}
)
_EVENT_ID_KEYS = frozenset(
    {
        "attempt_id",
        "claim_id",
        "command_id",
        "evaluation_version_id",
        "job_id",
        "question_id",
        "recording_id",
        "session_id",
        "stage_id",
        "transcript_version_id",
    }
)
_SAFE_EVENT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_EVENT_PAYLOAD_MAX_DEPTH = 4
_EVENT_PAYLOAD_MAX_ITEMS = 64
_EVENT_PAYLOAD_MAX_BYTES = 1024
_EVENT_ACTORS = frozenset({"candidate", "system", "worker", "reconciler", "migration"})
_CONVERSATION_STATES = frozenset(
    {
        "planning",
        "ready",
        "asking",
        "listening",
        "processing_answer",
        "awaiting_next_action",
        "coaching",
        "asking_follow_up",
        "advancing",
        "paused",
        "reporting",
        "completed",
        "recoverable_error",
        "abandoned",
        "failed",
    }
)
_CONVERSATIONAL_EVENT_TYPES = frozenset(
    {
        "session_plan_started",
        "session_plan_completed",
        "session_plan_failed",
        "session_plan_retry_requested",
        "session_plan_rebuild_requested",
        "session_plan_rebuilt",
        "session_plan_claim_expired",
        "session_started",
        "question_presented",
        "answer_capture_started",
        "silence_warning_presented",
        "keep_speaking_selected",
        "hint_requested",
        "hint_presented",
        "answer_capture_paused",
        "answer_capture_resumed",
        "answer_capture_cancelled",
        "answer_submitted",
        "attempt_processing_started",
        "attempt_processing_retry_requested",
        "attempt_processing_completed",
        "attempt_processing_failed",
        "transcript_edited",
        "coaching_requested",
        "coaching_presented",
        "attempt_retried",
        "attempt_accepted",
        "unaccepted_attempts_excluded",
        "follow_up_suppressed_session_end",
        "self_assessment_recorded",
        "retention_policy_updated",
        "question_skipped",
        "follow_up_created",
        "follow_up_presented",
        "question_advanced",
        "session_paused",
        "session_resumed",
        "report_claimed",
        "report_completed",
        "report_fallback_completed",
        "report_rebuild_claimed",
        "report_rebuild_completed",
        "report_rebuild_failed",
        "audio_cleanup_claimed",
        "audio_deleted",
        "audio_delete_failed",
        "transcript_deleted",
        "hard_deletion_requested",
        "hard_deletion_failed",
        "hard_deletion_claim_expired",
        "session_abandoned",
    }
)
_PROCESSING_ERROR_CODES = frozenset(ERROR_REGISTRY)
_PROCESSING_REASON_CODES = _PROCESSING_ERROR_CODES | frozenset(
    AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS
)
_PROCESSING_STAGES = frozenset(
    {
        "audio_persist",
        "transcription",
        "speech_analysis",
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    }
)
_PROCESSING_STAGE_ORDER = (
    "audio_persist",
    "transcription",
    "speech_analysis",
    "content_evaluation",
    "evidence_grounding",
    "follow_up_decision",
    "coaching_enrichment",
    "audio_cleanup",
)


async def _independent_cleanup_stage_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    cleanup: InterviewAttemptStage,
    expected_generation: int,
) -> bool:
    cleanup_job = await db.get(AsyncJob, cleanup.job_id) if cleanup.job_id else None
    expected_diagnostics = _stage_immutable_diagnostics(
        stage_name="audio_cleanup",
        audio_content_hash=attempt.audio_content_hash,
        transcript_version_id=evaluation.transcript_version_id,
        transcript_content_hash=None,
        evaluation_contract_version=evaluation.evaluation_contract_version,
        evidence_contract_version=evaluation.evidence_contract_version,
        follow_up_contract_version=evaluation.follow_up_contract_version,
    )
    expected_deadline = (
        cleanup.started_at
        + timedelta(seconds=settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS)
        if cleanup.started_at is not None
        else None
    )
    if not (
        cleanup_job is not None
        and cleanup_job.type == "coach_audio_cleanup"
        and cleanup.recording_id == attempt.id
        and cleanup.evaluation_version_id == evaluation.id
        and cleanup.expected_processing_generation == expected_generation
        and cleanup.source_transcript_version_id is None
        and cleanup.reused_from_stage_id is None
        and cleanup.diagnostics_json == expected_diagnostics
        and cleanup.job_deadline_at == expected_deadline
        and cleanup.started_at is not None
    ):
        return False
    if cleanup.stage_state == "completed":
        return bool(
            cleanup.claim_token is None
            and cleanup.completed_at is not None
            and cleanup.last_error_code is None
            and cleanup_job.status == "done"
            and cleanup_job.result_json == '{"result":"deleted"}'
            and cleanup_job.error is None
            and attempt.audio_uri is None
            and attempt.audio_retention_state == "deleted"
            and attempt.audio_deleted_at is not None
        )
    if cleanup.stage_state == "failed_retryable":
        return bool(
            cleanup.claim_token is None
            and cleanup.completed_at is not None
            and cleanup.last_error_code == "coach_audio_deletion_failed"
            and cleanup_job.status == "failed"
            and cleanup_job.result_json is None
            and cleanup_job.error == "coach_audio_deletion_failed"
            and attempt.audio_uri is not None
            and attempt.audio_retention_state == "delete_failed"
        )
    if cleanup.stage_state == "running":
        return bool(
            cleanup.claim_token
            and cleanup.completed_at is None
            and cleanup.last_error_code is None
            and cleanup_job.status in {"pending", "running"}
            and attempt.audio_uri is not None
            and attempt.audio_retention_state == "delete_pending"
        )
    return False


async def partition_current_processing_stages(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stages: Sequence[InterviewAttemptStage],
    processing_job_id: str,
) -> tuple[tuple[InterviewAttemptStage, ...], InterviewAttemptStage | None] | None:
    """Validate the exact eight-row graph and isolate independent cleanup authority."""
    cleanup_rows = [stage for stage in stages if stage.stage_name == "audio_cleanup"]
    independent_expected = bool(
        attempt.recording_type == "audio"
        and attempt.audio_retention_state
        in {"delete_pending", "deleted", "delete_failed"}
    )
    if len(cleanup_rows) != 1:
        return None if independent_expected else (tuple(stages), None)
    if cleanup_rows[0].job_id == processing_job_id:
        return None if independent_expected else (tuple(stages), None)
    expected_names = set(_PROCESSING_STAGE_ORDER)
    if (
        len(stages) != 8
        or {stage.stage_name for stage in stages} != expected_names
    ):
        return None
    cleanup = cleanup_rows[0]
    processing = tuple(stage for stage in stages if stage.stage_name != "audio_cleanup")
    if not await _independent_cleanup_stage_is_valid(
        db,
        attempt=attempt,
        evaluation=evaluation,
        cleanup=cleanup,
        expected_generation=attempt.processing_generation,
    ):
        return None
    return processing, cleanup
_PROCESSING_STAGE_COUNTER_LIMITS = {
    "audio_persist": (1, 0),
    "transcription": (3, 0),
    "speech_analysis": (2, 0),
    "content_evaluation": (3, 1),
    "evidence_grounding": (3, 1),
    "follow_up_decision": (2, 1),
    "coaching_enrichment": (1, 0),
    "audio_cleanup": (1, 0),
}
_TRANSCRIPT_BOUND_STAGES = frozenset(
    {
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    }
)
_PROCESSING_DIAGNOSTIC_STATES = frozenset(
    {
        "not_started",
        "pending",
        "running",
        "completed",
        "reused",
        "not_applicable",
        "unavailable",
        "failed_retryable",
        "failed_terminal",
    }
)


def _stage_immutable_diagnostics(
    *,
    stage_name: str,
    audio_content_hash: str | None,
    transcript_version_id: str | None,
    transcript_content_hash: str | None,
    evaluation_contract_version: str,
    evidence_contract_version: str,
    follow_up_contract_version: str,
) -> dict[str, object]:
    transcript_input = stage_name in _TRANSCRIPT_BOUND_STAGES
    transcription_output = stage_name == "transcription"
    return {
        "processing_contract_version": "coach_processing_v1",
        "evaluation_contract_version": evaluation_contract_version,
        "evidence_contract_version": evidence_contract_version,
        "follow_up_contract_version": follow_up_contract_version,
        "source_audio_content_hash": audio_content_hash,
        "source_transcript_version_id": (
            transcript_version_id if transcript_input else None
        ),
        "source_transcript_content_hash": (
            transcript_content_hash if transcript_input else None
        ),
        "result_transcript_version_id": (
            transcript_version_id if transcription_output else None
        ),
        "result_transcript_content_hash": (
            transcript_content_hash if transcription_output else None
        ),
    }


def _validate_event_payload(value: object) -> None:
    """Accept only bounded structural event diagnostics, never free-form content."""
    invalid = ValueError("event payload must be content-free and bounded")
    if value is None:
        return
    if not isinstance(value, dict):
        raise invalid
    budget = [0]
    for nested_key, nested in value.items():
        if not isinstance(nested_key, str):
            raise invalid
        _validate_event_payload_value(
            nested,
            key=nested_key,
            depth=1,
            budget=budget,
            invalid=invalid,
        )
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise invalid from error
    if len(encoded) > _EVENT_PAYLOAD_MAX_BYTES:
        raise invalid


def _validate_event_payload_value(
    value: object,
    *,
    key: str,
    depth: int,
    budget: list[int],
    invalid: ValueError,
) -> None:
    budget[0] += 1
    if depth > _EVENT_PAYLOAD_MAX_DEPTH or budget[0] > _EVENT_PAYLOAD_MAX_ITEMS:
        raise invalid

    if key in _EVENT_CONTAINER_KEYS:
        if not isinstance(value, dict):
            raise invalid
        for nested_key, nested in value.items():
            if not isinstance(nested_key, str):
                raise invalid
            _validate_event_payload_value(
                nested,
                key=nested_key,
                depth=depth + 1,
                budget=budget,
                invalid=invalid,
            )
        return
    if key in _EVENT_ENUM_KEYS:
        if not isinstance(value, str) or _SAFE_EVENT_CODE.fullmatch(value) is None:
            raise invalid
        return
    if key in _EVENT_ENUM_LIST_KEYS:
        if not isinstance(value, list) or len(value) > 32:
            raise invalid
        budget[0] += len(value)
        if budget[0] > _EVENT_PAYLOAD_MAX_ITEMS:
            raise invalid
        if any(
            not isinstance(item, str) or _SAFE_EVENT_CODE.fullmatch(item) is None
            for item in value
        ):
            raise invalid
        return
    if key in _EVENT_BOOLEAN_KEYS or key.endswith(
        ("_enabled", "_available", "_retryable", "_deleted")
    ):
        if not isinstance(value, bool):
            raise invalid
        return
    if key in _EVENT_ID_KEYS:
        if not isinstance(value, str) or _SAFE_EVENT_ID.fullmatch(value) is None:
            raise invalid
        return
    if key in {"count", "version", "duration_ms"} or key.endswith(
        ("_count", "_version", "_duration_ms", "_ms")
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise invalid
        if not 0 <= value <= 1_000_000:
            raise invalid
        return
    raise invalid


def _validate_processing_diagnostics(
    diagnostics: object, *, evaluation_state: str
) -> None:
    invalid = ValueError(
        "processing diagnostics must be canonical, content-free and bounded"
    )
    try:
        _validate_event_payload(diagnostics)
    except (TypeError, ValueError, RecursionError) as error:
        raise invalid from error
    if not isinstance(diagnostics, dict):
        raise invalid

    reason_count = 0
    pending: list[dict[str, object]] = [diagnostics]
    while pending:
        current = pending.pop()
        for key, value in current.items():
            if key == "diagnostics":
                if not isinstance(value, dict):
                    raise invalid
                pending.append(value)
            elif key in {"code", "error", "error_code"}:
                if value not in _PROCESSING_ERROR_CODES:
                    raise invalid
                if evaluation_state == "unavailable" and key == "code":
                    reason_count += 1
            elif key in {"reason", "reason_code"}:
                reason_count += 1
                if value not in _PROCESSING_REASON_CODES:
                    raise invalid
            elif key == "reason_codes":
                if not isinstance(value, list) or any(
                    code not in _PROCESSING_REASON_CODES for code in value
                ):
                    raise invalid
            elif key == "stage":
                if value not in _PROCESSING_STAGES:
                    raise invalid
            elif key == "stages":
                if not isinstance(value, list) or any(
                    stage not in _PROCESSING_STAGES for stage in value
                ):
                    raise invalid
            elif key == "state" and value not in _PROCESSING_DIAGNOSTIC_STATES:
                raise invalid
    if evaluation_state == "unavailable" and reason_count != 1:
        raise invalid


def _validate_event_envelope(*, session_id: object, event: SessionEventInput) -> None:
    invalid = ValueError("event envelope is invalid")

    def valid_id(value: object, *, maximum: int, optional: bool = False) -> bool:
        if value is None:
            return optional
        if (
            not isinstance(value, str)
            or len(value) > maximum
            or _SAFE_EVENT_ID.fullmatch(value) is None
        ):
            return False
        return True

    if not valid_id(session_id, maximum=36):
        raise invalid
    if not isinstance(event.event_type, str) or event.event_type not in (
        _CONVERSATIONAL_EVENT_TYPES
    ):
        raise invalid
    if not isinstance(event.actor_type, str) or event.actor_type not in _EVENT_ACTORS:
        raise invalid
    if isinstance(event.state_version, bool) or not isinstance(
        event.state_version, int
    ):
        raise invalid
    if not 0 <= event.state_version <= 1_000_000_000:
        raise invalid
    if any(
        state is not None
        and (not isinstance(state, str) or state not in _CONVERSATION_STATES)
        for state in (event.state_before, event.state_after)
    ):
        raise invalid
    if not valid_id(event.question_id, maximum=36, optional=True):
        raise invalid
    if not valid_id(event.recording_id, maximum=36, optional=True):
        raise invalid
    if event.command_id is not None and (
        not isinstance(event.command_id, str)
        or SAFE_TOKEN_RE.fullmatch(event.command_id) is None
    ):
        raise invalid


class _StaleFinalisation(Exception):
    pass


def _audio_upload_request_hash(
    *,
    session_id: str,
    attempt_id: str,
    upload_id: str,
    content_sha256: str,
    byte_size: int,
    mime_type: str,
) -> str:
    encoded = json.dumps(
        {
            "attempt_id": attempt_id,
            "byte_size": byte_size,
            "content_sha256": content_sha256,
            "contract_version": "coach_attempt_audio_upload_v1",
            "mime_type": mime_type,
            "session_id": session_id,
            "upload_id": upload_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _audio_upload_read(
    row: InterviewAttemptUpload, retention_state: str | None
) -> AttemptAudioUploadRead:
    return AttemptAudioUploadRead.model_validate(
        {
            "attempt_id": row.attempt_id,
            "upload_id": row.upload_id,
            "result": row.result_state,
            "content_sha256": row.content_sha256,
            "byte_size": row.byte_size,
            "mime_type": row.mime_type,
            "audio_retention_state": retention_state,
            "contract_version": "coach_attempt_audio_upload_v1",
        }
    )


class ConversationalSessionRepository:
    """SQLite-safe conditional transaction primitives for Coach Phase 1."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        max_transcript_characters: int | None = None,
    ) -> None:
        self._session = session
        configured_limit = (
            settings.HATCH_COACH_MAX_TRANSCRIPT_CHARACTERS
            if max_transcript_characters is None
            else max_transcript_characters
        )
        if isinstance(configured_limit, bool) or not isinstance(configured_limit, int):
            raise ValueError("transcript code-point limit must be a positive integer")
        if configured_limit < 1:
            raise ValueError("transcript code-point limit must be a positive integer")
        self._max_transcript_characters = configured_limit
        self._audio_publication: OwnedAudioPublication | None = None

    async def get_completed_audio_upload(
        self, *, attempt_id: str, upload_id: str, content_hash: str | None
    ) -> InterviewAttemptUpload | None:
        """Return a completed upload only when it matches the attempt hash."""
        if not content_hash:
            return None
        return await self._session.scalar(
            select(InterviewAttemptUpload).where(
                InterviewAttemptUpload.attempt_id == attempt_id,
                InterviewAttemptUpload.upload_id == upload_id,
                InterviewAttemptUpload.result_state == "completed",
                InterviewAttemptUpload.content_sha256 == content_hash,
            )
        )

    def _discard_audio_stage(self, staged: StagedAudio, *, code: str) -> None:
        try:
            cleanup_staged_audio(staged)
        except CoachMediaError:
            code = "coach_attempt_upload_conflict"
        raise ConversationalRepositoryError(code)

    async def _rollback_audio_upload(self) -> None:
        rollback_failed = False
        propagated_error: BaseException | None = None
        try:
            await self._session.rollback()
        except BaseException as error:
            rollback_failed = True
            if not isinstance(error, Exception):
                propagated_error = error
            try:
                await self._session.close()
            except BaseException as close_error:
                if (
                    propagated_error is None
                    and not isinstance(close_error, Exception)
                ):
                    propagated_error = close_error
        compensation_failed = False
        publication = self._audio_publication
        if publication is not None:
            for _ in range(_AUDIO_PUBLICATION_COMPENSATION_ATTEMPTS):
                try:
                    publication.compensate()
                except BaseException as error:
                    compensation_failed = True
                    if propagated_error is None and not isinstance(error, Exception):
                        propagated_error = error
                else:
                    self._audio_publication = None
                    compensation_failed = False
                    break
        if propagated_error is not None:
            raise propagated_error
        if rollback_failed or compensation_failed:
            raise ConversationalRepositoryError(
                "coach_attempt_upload_conflict"
            ) from None

    async def commit_audio_upload(self) -> None:
        """Commit the narrow upload transaction or compensate its owned inode."""
        try:
            await self._session.commit()
        except BaseException as error:
            rollback_error: BaseException | None = None
            try:
                await self._rollback_audio_upload()
            except BaseException as failure:
                rollback_error = failure
            if rollback_error is not None and not isinstance(
                rollback_error, Exception
            ):
                raise rollback_error
            if not isinstance(error, Exception):
                raise
            raise ConversationalRepositoryError(
                "coach_attempt_upload_conflict"
            ) from None
        publication = self._audio_publication
        self._audio_publication = None
        if publication is not None:
            try:
                publication.release()
            except CoachMediaError:
                # The receipt and file are now durable. A best-effort handle
                # release cannot truthfully turn that completed upload into a
                # failed client operation.
                pass

    async def persist_audio_upload(
        self,
        *,
        session_id: str,
        attempt_id: str,
        upload_id: str,
        declared_sha256: str,
        staged: StagedAudio,
        destination: Path,
    ) -> AttemptAudioUploadRead:
        """Persist one owned audio upload and replay completed duplicates."""
        if staged.content_sha256 != declared_sha256:
            self._discard_audio_stage(
                staged, code="coach_attempt_upload_hash_mismatch"
            )
        request_hash = _audio_upload_request_hash(
            session_id=session_id,
            attempt_id=attempt_id,
            upload_id=upload_id,
            content_sha256=declared_sha256,
            byte_size=staged.byte_size,
            mime_type=staged.mime_type,
        )
        existing = await self._session.scalar(
            select(InterviewAttemptUpload)
            .join(
                SessionRecording,
                SessionRecording.id == InterviewAttemptUpload.attempt_id,
            )
            .where(
                InterviewAttemptUpload.attempt_id == attempt_id,
                InterviewAttemptUpload.upload_id == upload_id,
                SessionRecording.session_id == session_id,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                self._discard_audio_stage(
                    staged, code="coach_audio_upload_idempotency_conflict"
                )
            attempt = await self._session.get(SessionRecording, attempt_id)
            if (
                existing.result_state != "completed"
                or attempt is None
                or attempt.session_id != session_id
                or attempt.audio_uri != existing.storage_uri
                or Path(existing.storage_uri) != destination
                or not owned_audio_path_is_file(destination)
            ):
                self._discard_audio_stage(
                    staged, code="coach_attempt_upload_conflict"
                )
            try:
                cleanup_staged_audio(staged)
            except CoachMediaError:
                raise ConversationalRepositoryError(
                    "coach_attempt_upload_conflict"
                ) from None
            return _audio_upload_read(existing, attempt.audio_retention_state)

        session_row = await self._session.get(InterviewSession, session_id)
        attempt = await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.id == attempt_id,
                SessionRecording.session_id == session_id,
            )
        )
        if session_row is None or attempt is None:
            self._discard_audio_stage(staged, code="coach_attempt_upload_missing")
        if (
            session_row.experience_version != "conversational_v1"
            or session_row.status != "active"
            or session_row.conversation_state != "listening"
            or session_row.active_recording_id != attempt_id
            or session_row.deletion_state != "not_requested"
            or attempt.recording_type != "audio"
            or attempt.attempt_state != "draft"
            or attempt.audio_uri is not None
            or attempt.audio_content_hash is not None
            or attempt.audio_retention_policy
            not in {"delete_after_processing", "retain_until_deleted"}
        ):
            completed = await self._session.scalar(
                select(InterviewAttemptUpload).where(
                    InterviewAttemptUpload.attempt_id == attempt_id,
                    InterviewAttemptUpload.upload_id == upload_id,
                )
            )
            if completed is not None:
                if completed.request_hash != request_hash:
                    self._discard_audio_stage(
                        staged, code="coach_audio_upload_idempotency_conflict"
                    )
                if (
                    completed.result_state == "completed"
                    and attempt.audio_uri == completed.storage_uri
                    and Path(completed.storage_uri) == destination
                    and owned_audio_path_is_file(destination)
                ):
                    try:
                        cleanup_staged_audio(staged)
                    except CoachMediaError:
                        raise ConversationalRepositoryError(
                            "coach_attempt_upload_conflict"
                        ) from None
                    return _audio_upload_read(
                        completed, attempt.audio_retention_state
                    )
            self._discard_audio_stage(staged, code="coach_attempt_upload_conflict")

        retention_state = (
            "retained"
            if attempt.audio_retention_policy == "retain_until_deleted"
            else "temporary"
        )
        claim_id = str(uuid.uuid4())
        try:
            inserted = await self._session.execute(
                sqlite_insert(InterviewAttemptUpload)
                .values(
                    id=claim_id,
                    attempt_id=attempt_id,
                    upload_id=upload_id,
                    request_hash=request_hash,
                    content_sha256=declared_sha256,
                    byte_size=staged.byte_size,
                    mime_type=staged.mime_type,
                    storage_uri=str(destination),
                    result_state="pending",
                )
                .on_conflict_do_nothing(index_elements=("attempt_id", "upload_id"))
                .returning(InterviewAttemptUpload.id)
            )
            won_claim = inserted.scalar_one_or_none() is not None
            if not won_claim:
                await self._session.rollback()
                duplicate = None
                for _ in range(5):
                    duplicate = await self._session.scalar(
                        select(InterviewAttemptUpload).where(
                            InterviewAttemptUpload.attempt_id == attempt_id,
                            InterviewAttemptUpload.upload_id == upload_id,
                        )
                    )
                    if duplicate is not None:
                        break
                    await self._session.rollback()
                    await asyncio.sleep(0)
                if duplicate is None or duplicate.result_state != "completed":
                    self._discard_audio_stage(
                        staged, code="coach_attempt_upload_conflict"
                    )
                if duplicate.request_hash != request_hash:
                    self._discard_audio_stage(
                        staged, code="coach_audio_upload_idempotency_conflict"
                    )
                replay_attempt = await self._session.get(
                    SessionRecording, attempt_id
                )
                if (
                    replay_attempt is None
                    or replay_attempt.session_id != session_id
                    or replay_attempt.audio_uri != duplicate.storage_uri
                    or Path(duplicate.storage_uri) != destination
                    or not owned_audio_path_is_file(destination)
                ):
                    self._discard_audio_stage(
                        staged, code="coach_attempt_upload_conflict"
                    )
                try:
                    cleanup_staged_audio(staged)
                except CoachMediaError:
                    raise ConversationalRepositoryError(
                        "coach_attempt_upload_conflict"
                    ) from None
                return _audio_upload_read(
                    duplicate, replay_attempt.audio_retention_state
                )
            changed = await self._session.execute(
                update(SessionRecording)
                .where(
                    SessionRecording.id == attempt_id,
                    SessionRecording.session_id == session_id,
                    SessionRecording.recording_type == "audio",
                    SessionRecording.attempt_state == "draft",
                    SessionRecording.audio_uri.is_(None),
                    SessionRecording.audio_content_hash.is_(None),
                )
                .values(
                    attempt_state="uploaded",
                    attempt_version=SessionRecording.attempt_version + 1,
                    audio_uri=str(destination),
                    audio_content_hash=declared_sha256,
                    audio_retention_state=retention_state,
                )
            )
            if changed.rowcount != 1:
                raise ConversationalRepositoryError("coach_attempt_upload_conflict")
            await self._session.flush()
            self._audio_publication = publish_staged_audio(staged, destination)
            completed = await self._session.execute(
                update(InterviewAttemptUpload)
                .where(
                    InterviewAttemptUpload.id == claim_id,
                    InterviewAttemptUpload.attempt_id == attempt_id,
                    InterviewAttemptUpload.upload_id == upload_id,
                    InterviewAttemptUpload.request_hash == request_hash,
                    InterviewAttemptUpload.result_state == "pending",
                )
                .values(result_state="completed", completed_at=datetime.utcnow())
            )
            if completed.rowcount != 1:
                raise ConversationalRepositoryError("coach_attempt_upload_conflict")
            await self._session.flush()
            row = await self._session.get(InterviewAttemptUpload, claim_id)
            assert row is not None
            return _audio_upload_read(row, retention_state)
        except BaseException as error:
            rollback_error: BaseException | None = None
            try:
                await self._rollback_audio_upload()
            except BaseException as failure:
                rollback_error = failure
            cleanup_error: BaseException | None = None
            try:
                cleanup_staged_audio(staged)
            except BaseException as failure:
                cleanup_error = failure
            if rollback_error is not None and not isinstance(
                rollback_error, Exception
            ):
                raise rollback_error
            if cleanup_error is not None and not isinstance(cleanup_error, Exception):
                raise cleanup_error
            if not isinstance(error, Exception):
                raise
            if (
                isinstance(error, ConversationalRepositoryError)
                and rollback_error is None
                and cleanup_error is None
            ):
                raise
            raise ConversationalRepositoryError(
                "coach_attempt_upload_conflict"
            ) from None

    async def abandon_conversational_session(self, *, session_id: str) -> bool:
        session_row = await self._session.get(InterviewSession, session_id)
        if session_row is None or session_row.experience_version != "conversational_v1":
            return False
        if (
            session_row.status == "abandoned"
            and session_row.conversation_state == "abandoned"
        ):
            return True
        if (
            session_row.status not in {"setup", "active"}
            or session_row.deletion_state != "not_requested"
        ):
            return False
        prior_state = session_row.conversation_state
        prior_version = session_row.state_version
        try:
            async with self._session.begin_nested():
                changed = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == session_row.status,
                        InterviewSession.conversation_state == prior_state,
                        InterviewSession.state_version == prior_version,
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        status="abandoned",
                        conversation_state="abandoned",
                        state_version=InterviewSession.state_version + 1,
                        setup_generation=InterviewSession.setup_generation + 1,
                        setup_job_id=None,
                        setup_claim_token=None,
                        setup_claimed_at=None,
                        setup_claim_expires_at=None,
                        setup_started_at=None,
                        report_state="not_started",
                        report_job_id=None,
                        report_started_at=None,
                        report_build_reason=None,
                        active_question_id=None,
                        active_root_question_id=None,
                        active_recording_id=None,
                        resume_state=None,
                        recoverable_error_code=None,
                        recoverable_error_scope=None,
                        recoverable_error_context_json=None,
                        last_activity_at=datetime.utcnow(),
                    )
                )
                if changed.rowcount != 1:
                    raise _StaleFinalisation
                await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.session_id == session_id,
                        or_(
                            SessionRecording.async_job_id.is_not(None),
                            SessionRecording.attempt_state.in_(
                                (
                                    "draft",
                                    "uploaded",
                                    "pending_processing",
                                    "recoverable_error",
                                )
                            ),
                        ),
                    )
                    .values(
                        processing_generation=(
                            SessionRecording.processing_generation + 1
                        ),
                        async_job_id=None,
                    )
                )
                await self.append_session_events(
                    session_id=session_id,
                    events=(
                        SessionEventInput(
                            event_type="session_abandoned",
                            actor_type="candidate",
                            state_version=prior_version + 1,
                            state_before=prior_state,
                            state_after="abandoned",
                        ),
                    ),
                )
                await self._session.flush()
        except _StaleFinalisation:
            return False
        return True

    async def get_command_result(
        self, *, session_id: str, command_id: str
    ) -> ConversationCommandResultRecord | None:
        return await self._session.scalar(
            select(ConversationCommandResultRecord).where(
                ConversationCommandResultRecord.session_id == session_id,
                ConversationCommandResultRecord.command_id == command_id,
            )
        )

    async def claim_conversation_command(
        self,
        *,
        session_id: str,
        request: ConversationCommandRequest,
        request_hash: str,
    ) -> CommandClaim:
        """Replay duplicates before applying the new-command version fence."""
        existing = await self.get_command_result(
            session_id=session_id, command_id=request.command_id
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise CommandIdempotencyConflict("coach_command_idempotency_conflict")
            return self._command_claim(existing, duplicate=True)

        serialized = await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(state_version=InterviewSession.state_version)
            .returning(
                InterviewSession.state_version,
                InterviewSession.conversation_state,
            )
        )
        current = serialized.one_or_none()
        if current is None:
            raise ConversationalRepositoryError("coach_session_not_found")

        # A competing transaction may have completed this exact command while
        # this transaction waited for SQLite's writer lock.
        existing = await self.get_command_result(
            session_id=session_id, command_id=request.command_id
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise CommandIdempotencyConflict("coach_command_idempotency_conflict")
            return self._command_claim(existing, duplicate=True)

        current_state_version, current_state = current
        if current_state_version != request.expected_state_version:
            raise ConversationVersionConflict(
                current_state_version=current_state_version,
                current_state=current_state,
            )

        receipt_id = str(uuid.uuid4())
        inserted = await self._session.execute(
            sqlite_insert(ConversationCommandResultRecord)
            .values(
                id=receipt_id,
                session_id=session_id,
                command_id=request.command_id,
                command_type=request.command_type,
                request_hash=request_hash,
                expected_state_version=request.expected_state_version,
                result_state="accepted_processing",
                created_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(index_elements=("session_id", "command_id"))
            .returning(ConversationCommandResultRecord.id)
        )
        won_claim = inserted.scalar_one_or_none() is not None
        receipt = await self.get_command_result(
            session_id=session_id, command_id=request.command_id
        )
        assert receipt is not None
        if receipt.request_hash != request_hash:
            raise CommandIdempotencyConflict("coach_command_idempotency_conflict")
        return self._command_claim(receipt, duplicate=not won_claim)

    async def complete_conversation_command(
        self,
        *,
        claim: CommandClaim,
        result: dict[str, object],
        result_state: Literal["completed", "accepted_processing"] = "completed",
    ) -> bool:
        changed = await self._session.execute(
            update(ConversationCommandResultRecord)
            .where(
                ConversationCommandResultRecord.id == claim.record_id,
                ConversationCommandResultRecord.session_id == claim.session_id,
                ConversationCommandResultRecord.command_id == claim.command_id,
                ConversationCommandResultRecord.request_hash == claim.request_hash,
                ConversationCommandResultRecord.result_state == "accepted_processing",
            )
            .values(
                result_state=result_state,
                result_json=result,
                completed_at=datetime.utcnow(),
            )
        )
        await self._session.flush()
        return changed.rowcount == 1

    async def fail_conversation_command(
        self,
        *,
        claim: CommandClaim,
        result_state: Literal[
            "invalid_state",
            "version_conflict",
            "idempotency_conflict",
            "invalid_payload",
            "resource_blocked",
            "not_found",
            "permission_denied",
            "stale_claim",
        ],
        result: dict[str, object],
    ) -> bool:
        return await self._finish_command_receipt(
            claim=claim, result_state=result_state, result=result
        )

    async def _finish_command_receipt(
        self, *, claim: CommandClaim, result_state: str, result: dict[str, object]
    ) -> bool:
        changed = await self._session.execute(
            update(ConversationCommandResultRecord)
            .where(
                ConversationCommandResultRecord.id == claim.record_id,
                ConversationCommandResultRecord.session_id == claim.session_id,
                ConversationCommandResultRecord.command_id == claim.command_id,
                ConversationCommandResultRecord.request_hash == claim.request_hash,
                ConversationCommandResultRecord.result_state == "accepted_processing",
            )
            .values(
                result_state=result_state,
                result_json=result,
                completed_at=datetime.utcnow(),
            )
        )
        await self._session.flush()
        return changed.rowcount == 1

    @staticmethod
    def _command_claim(
        record: ConversationCommandResultRecord, *, duplicate: bool
    ) -> CommandClaim:
        return CommandClaim(
            record_id=record.id,
            session_id=record.session_id,
            command_id=record.command_id,
            request_hash=record.request_hash,
            is_duplicate=duplicate,
            result_state=record.result_state,
            result_json=record.result_json,
        )

    async def append_session_events(
        self, *, session_id: str, events: Sequence[SessionEventInput]
    ) -> tuple[InterviewSessionEvent, ...]:
        if not events:
            return ()
        for event in events:
            _validate_event_envelope(session_id=session_id, event=event)
            _validate_event_payload(event.payload_json)

        allocation = await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(event_version=InterviewSession.event_version + len(events))
            .returning(InterviewSession.event_version)
        )
        new_event_version = allocation.scalar_one_or_none()
        if new_event_version is None:
            raise ConversationalRepositoryError("coach_session_not_found")
        first_sequence = new_event_version - len(events) + 1
        rows = tuple(
            InterviewSessionEvent(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence_number=first_sequence + offset,
                event_type=event.event_type,
                state_before=event.state_before,
                state_after=event.state_after,
                state_version=event.state_version,
                question_id=event.question_id,
                recording_id=event.recording_id,
                command_id=event.command_id,
                actor_type=event.actor_type,
                payload_json=event.payload_json,
            )
            for offset, event in enumerate(events)
        )
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def reserve_conversational_attempt(
        self,
        *,
        session_id: str,
        question_id: str,
        client_attempt_id: str,
        recording_type: str,
        expected_state_version: int,
        attempt_kind: str,
        max_attempts: int,
        processing_retry_limit: int,
        audio_retention_policy: str,
    ) -> AttemptReservation:
        duplicate = await self.get_attempt_by_client_id(
            session_id=session_id,
            client_attempt_id=client_attempt_id,
        )
        if duplicate is not None:
            if (
                duplicate.question_id != question_id
                or duplicate.recording_type != recording_type
            ):
                raise AttemptReservationConflict("coach_client_attempt_id_conflict")
            return AttemptReservation(duplicate, True, ())

        session_row = await self._session.get(InterviewSession, session_id)
        if session_row is None:
            raise AttemptReservationConflict("coach_session_not_found")
        if session_row.state_version != expected_state_version:
            raise ConversationVersionConflict(
                current_state_version=session_row.state_version,
                current_state=session_row.conversation_state,
            )
        if (
            session_row.experience_version != "conversational_v1"
            or session_row.status != "active"
            or session_row.conversation_state != "asking"
            or session_row.active_question_id != question_id
            or session_row.active_recording_id is not None
            or session_row.deletion_state != "not_requested"
        ):
            raise AttemptReservationConflict("coach_question_not_active")

        question = await self._session.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == question_id,
                SessionQuestion.session_id == session_id,
            )
        )
        if question is None:
            raise AttemptReservationConflict("coach_question_not_owned")
        if (
            question.question_state != "asked"
            or question.accepted_recording_id is not None
        ):
            raise AttemptReservationConflict("coach_question_not_active")
        if question.attempts_created_count >= max_attempts:
            raise AttemptLimitExhausted("coach_attempt_limit_exhausted")
        pending_hint_count = question.pending_hint_count
        pending_hint_types = tuple(question.pending_hint_types_json or ())
        try:
            transaction_lock = await self._session.execute(
                update(InterviewSession)
                .where(
                    InterviewSession.id == session_id,
                    InterviewSession.experience_version == "conversational_v1",
                    InterviewSession.status == "active",
                    InterviewSession.conversation_state == "asking",
                    InterviewSession.active_question_id == question_id,
                    InterviewSession.active_recording_id.is_(None),
                    InterviewSession.state_version == expected_state_version,
                    InterviewSession.deletion_state == "not_requested",
                )
                .values(state_version=InterviewSession.state_version)
            )
            if transaction_lock.rowcount != 1:
                raise _StaleFinalisation
            async with self._session.begin_nested():
                counter = await self._session.execute(
                    update(SessionQuestion)
                    .where(
                        SessionQuestion.id == question_id,
                        SessionQuestion.session_id == session_id,
                        SessionQuestion.question_state == "asked",
                        SessionQuestion.accepted_recording_id.is_(None),
                        SessionQuestion.attempts_created_count < max_attempts,
                    )
                    .values(
                        attempts_created_count=SessionQuestion.attempts_created_count
                        + 1,
                        pending_hint_count=0,
                        pending_hint_types_json=None,
                    )
                    .returning(SessionQuestion.attempts_created_count)
                )
                attempt_number = counter.scalar_one_or_none()
                if attempt_number is None:
                    raise AttemptLimitExhausted("coach_attempt_limit_exhausted")

                attempt = SessionRecording(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    question_id=question_id,
                    recording_type=recording_type,
                    attempt_number=attempt_number,
                    attempt_kind=attempt_kind,
                    attempt_state="draft",
                    processing_retry_limit=processing_retry_limit,
                    audio_retention_policy=audio_retention_policy,
                    audio_retention_state=(
                        "not_applicable" if recording_type == "text" else "pending"
                    ),
                    client_attempt_id=client_attempt_id,
                    hint_count=pending_hint_count,
                )
                self._session.add(attempt)
                await self._session.flush()
                active = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.conversation_state == "asking",
                        InterviewSession.active_question_id == question_id,
                        InterviewSession.active_recording_id.is_(None),
                        InterviewSession.state_version == expected_state_version,
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        conversation_state="listening",
                        active_recording_id=attempt.id,
                        state_version=InterviewSession.state_version + 1,
                        last_activity_at=datetime.utcnow(),
                    )
                )
                if active.rowcount != 1:
                    raise _StaleFinalisation
        except _StaleFinalisation as error:
            current = await self._session.get(InterviewSession, session_id)
            if current is not None and current.state_version != expected_state_version:
                raise ConversationVersionConflict(
                    current_state_version=current.state_version,
                    current_state=current.conversation_state,
                ) from error
            raise AttemptReservationConflict("coach_attempt_already_active") from error
        return AttemptReservation(attempt, False, pending_hint_types)

    async def get_attempt_by_client_id(
        self,
        *,
        session_id: str,
        client_attempt_id: str,
    ) -> SessionRecording | None:
        """Resolve a client-attempt identity independently of live pointers."""
        return await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.session_id == session_id,
                SessionRecording.client_attempt_id == client_attempt_id,
            )
        )

    async def create_transcript_version(
        self,
        *,
        recording_id: str,
        source: str,
        transcript: str,
        expected_attempt_version: int,
        processing_generation: int,
    ) -> InterviewTranscriptVersion:
        if source not in {"candidate_text", "candidate_edit"}:
            raise ValueError("candidate transcript source required")
        normalised = unicodedata.normalize(
            "NFC", transcript.replace("\r\n", "\n").replace("\r", "\n")
        )
        if not normalised:
            raise ValueError("transcript must not be empty")
        if len(normalised) > self._max_transcript_characters:
            raise ValueError("transcript exceeds configured code-point limit")
        attempt = await self._session.get(SessionRecording, recording_id)
        if (
            attempt is None
            or attempt.attempt_state == "deleted"
            or attempt.attempt_version != expected_attempt_version
        ):
            raise StaleVersion("stale attempt version")
        version_id = str(uuid.uuid4())
        current_transcript_version_id = attempt.current_transcript_version_id
        try:
            async with self._session.begin_nested():
                ownership_lock = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.attempt_version == expected_attempt_version,
                        SessionRecording.attempt_state != "deleted",
                        SessionRecording.current_transcript_version_id
                        == current_transcript_version_id,
                    )
                    .values(attempt_version=SessionRecording.attempt_version)
                )
                if ownership_lock.rowcount != 1:
                    raise _StaleFinalisation
                if current_transcript_version_id is None:
                    orphan = await self._session.scalar(
                        select(InterviewTranscriptVersion.id)
                        .where(InterviewTranscriptVersion.recording_id == recording_id)
                        .limit(1)
                    )
                    if orphan is not None:
                        raise _StaleFinalisation
                    version_number = 1
                else:
                    current_version_number = await self._session.scalar(
                        select(InterviewTranscriptVersion.version_number).where(
                            InterviewTranscriptVersion.id
                            == current_transcript_version_id,
                            InterviewTranscriptVersion.recording_id == recording_id,
                        )
                    )
                    if current_version_number is None:
                        raise _StaleFinalisation
                    version_number = current_version_number + 1
                row = InterviewTranscriptVersion(
                    id=version_id,
                    recording_id=recording_id,
                    version_number=version_number,
                    transcript=normalised,
                    source=source,
                    content_hash=hashlib.sha256(normalised.encode("utf-8")).hexdigest(),
                    created_by="candidate",
                    processing_generation=processing_generation,
                )
                self._session.add(row)
                await self._session.flush()
                changed = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.attempt_version == expected_attempt_version,
                        SessionRecording.attempt_state != "deleted",
                        SessionRecording.current_transcript_version_id
                        == current_transcript_version_id,
                    )
                    .values(
                        attempt_version=SessionRecording.attempt_version + 1,
                        current_transcript_version_id=version_id,
                        transcript=normalised,
                    )
                )
                if changed.rowcount != 1:
                    raise _StaleFinalisation
                await self._session.flush()
        except _StaleFinalisation as error:
            raise StaleVersion("stale transcript pointer or attempt version") from error
        return row

    async def create_worker_transcript_version(
        self,
        *,
        recording_id: str,
        transcript: str,
        expected_job_id: str,
        expected_processing_generation: int,
        expected_audio_content_hash: str,
        expected_evaluation_version_id: str,
        expected_claim_token: str,
    ) -> InterviewTranscriptVersion | None:
        """Promote an audio transcript only while the exact worker claim is live."""
        normalised = unicodedata.normalize(
            "NFC", transcript.replace("\r\n", "\n").replace("\r", "\n")
        )
        if not normalised:
            raise ValueError("transcript must not be empty")
        if len(normalised) > self._max_transcript_characters:
            raise ValueError("transcript exceeds configured code-point limit")
        attempt = await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.id == recording_id,
                SessionRecording.recording_type == "audio",
                SessionRecording.attempt_state == "pending_processing",
                SessionRecording.async_job_id == expected_job_id,
                SessionRecording.processing_generation
                == expected_processing_generation,
                SessionRecording.audio_content_hash == expected_audio_content_hash,
                SessionRecording.current_transcript_version_id.is_(None),
            )
        )
        if attempt is None:
            return None
        evaluation = await self._session.scalar(
            select(InterviewAttemptEvaluation).where(
                InterviewAttemptEvaluation.id == expected_evaluation_version_id,
                InterviewAttemptEvaluation.recording_id == recording_id,
                InterviewAttemptEvaluation.async_job_id == expected_job_id,
                InterviewAttemptEvaluation.state == "pending",
                InterviewAttemptEvaluation.transcript_version_id.is_(None),
                InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                    "claim_token"
                ].as_string()
                == expected_claim_token,
            )
        )
        if evaluation is None:
            return None
        try:
            async with self._session.begin_nested():
                attempt_lock = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.recording_type == "audio",
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.async_job_id == expected_job_id,
                        SessionRecording.processing_generation
                        == expected_processing_generation,
                        SessionRecording.audio_content_hash
                        == expected_audio_content_hash,
                        SessionRecording.current_transcript_version_id.is_(None),
                    )
                    .values(attempt_version=SessionRecording.attempt_version)
                )
                evaluation_lock = await self._session.execute(
                    update(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.id == expected_evaluation_version_id,
                        InterviewAttemptEvaluation.recording_id == recording_id,
                        InterviewAttemptEvaluation.async_job_id == expected_job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.transcript_version_id.is_(None),
                        InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                            "claim_token"
                        ].as_string()
                        == expected_claim_token,
                    )
                    .values(state=InterviewAttemptEvaluation.state)
                )
                if attempt_lock.rowcount != 1 or evaluation_lock.rowcount != 1:
                    raise _StaleFinalisation
                orphan = await self._session.scalar(
                    select(InterviewTranscriptVersion.id)
                    .where(InterviewTranscriptVersion.recording_id == recording_id)
                    .limit(1)
                )
                if orphan is not None:
                    raise _StaleFinalisation
                row = InterviewTranscriptVersion(
                    id=str(uuid.uuid4()),
                    recording_id=recording_id,
                    version_number=1,
                    transcript=normalised,
                    source="transcription",
                    content_hash=hashlib.sha256(normalised.encode("utf-8")).hexdigest(),
                    created_by="system",
                    processing_generation=expected_processing_generation,
                )
                self._session.add(row)
                await self._session.flush()
                attempt_change = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.recording_type == "audio",
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.async_job_id == expected_job_id,
                        SessionRecording.processing_generation
                        == expected_processing_generation,
                        SessionRecording.audio_content_hash
                        == expected_audio_content_hash,
                        SessionRecording.current_transcript_version_id.is_(None),
                    )
                    .values(
                        current_transcript_version_id=row.id,
                        transcript=normalised,
                    )
                )
                evaluation_change = await self._session.execute(
                    update(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.id == evaluation.id,
                        InterviewAttemptEvaluation.recording_id == recording_id,
                        InterviewAttemptEvaluation.async_job_id == expected_job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.transcript_version_id.is_(None),
                        InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                            "claim_token"
                        ].as_string()
                        == expected_claim_token,
                    )
                    .values(transcript_version_id=row.id)
                )
                if attempt_change.rowcount != 1 or evaluation_change.rowcount != 1:
                    raise _StaleFinalisation
                await self._session.flush()
        except _StaleFinalisation:
            return None
        return row

    async def create_evaluation_version(
        self,
        *,
        recording_id: str,
        transcript_version_id: str | None,
        evaluation_version: int,
        processing_generation: int,
        contract_version: str,
        state: str,
        async_job_id: str | None = None,
    ) -> InterviewAttemptEvaluation:
        attempt = await self._session.get(SessionRecording, recording_id)
        if attempt is None or attempt.attempt_state == "deleted":
            raise StaleVersion("attempt is unavailable")
        if transcript_version_id is not None:
            transcript = await self._session.scalar(
                select(InterviewTranscriptVersion.id).where(
                    InterviewTranscriptVersion.id == transcript_version_id,
                    InterviewTranscriptVersion.recording_id == recording_id,
                )
            )
            if transcript is None:
                raise StaleVersion("transcript is not owned by attempt")
        row = InterviewAttemptEvaluation(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            transcript_version_id=transcript_version_id,
            version_number=evaluation_version,
            state=state,
            evaluation_contract_version=contract_version,
            evidence_contract_version=EVIDENCE_GROUNDING_CONTRACT,
            follow_up_contract_version=FOLLOW_UP_CONTRACT,
            async_job_id=async_job_id,
            diagnostics_json={"processing_generation": processing_generation},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def claim_retry_processing(
        self,
        *,
        recording_id: str,
        job_id: str,
        deadline: datetime,
        expected_session_state_version: int,
    ) -> AttemptProcessingClaim | None:
        """Atomically consume one manual retry and create its complete stage graph."""
        from ..services.coach_attempt_pipeline import (
            AttemptPipelineError,
            select_restart_stage,
        )

        attempt = await self._session.get(SessionRecording, recording_id)
        if attempt is None or attempt.attempt_state != "recoverable_error":
            return None
        session = await self._session.get(InterviewSession, attempt.session_id)
        recorded_error = (
            ERROR_REGISTRY.get(session.recoverable_error_code)
            if session is not None and session.recoverable_error_code is not None
            else None
        )
        if (
            session is None
            or session.experience_version != "conversational_v1"
            or session.status != "active"
            or session.conversation_state != "recoverable_error"
            or session.recoverable_error_scope != "attempt_processing"
            or session.state_version != expected_session_state_version
            or session.deletion_state != "not_requested"
            or session.active_recording_id != attempt.id
            or session.active_question_id != attempt.question_id
            or attempt.async_job_id is not None
            or recorded_error is None
        ):
            return None
        if attempt.processing_retry_count >= attempt.processing_retry_limit:
            raise ConversationalRepositoryError(
                "coach_attempt_retry_budget_exhausted"
            )
        retry_source = (
            await self._session.get(
                InterviewTranscriptVersion, attempt.current_transcript_version_id
            )
            if attempt.current_transcript_version_id is not None
            else None
        )
        if retry_source is None and (
            attempt.recording_type == "text"
            or not attempt.audio_uri
            or not attempt.audio_content_hash
        ):
            raise ConversationalRepositoryError(
                "coach_attempt_retry_source_unavailable"
            )
        from ..services.coach_processing_snapshot import (
            load_retryable_processing_snapshot,
        )

        retry_snapshot = await load_retryable_processing_snapshot(
            self._session,
            session=session,
            attempt=attempt,
        )
        if retry_snapshot is None:
            return None
        prior_evaluation = retry_snapshot.evaluation
        prior_stages = list(retry_snapshot.stages)
        partition = await partition_current_processing_stages(
            self._session,
            attempt=attempt,
            evaluation=prior_evaluation,
            stages=prior_stages,
            processing_job_id=prior_evaluation.async_job_id or "",
        )
        if partition is None:
            return None
        processing_prior_stages, independent_cleanup = partition
        if (
            independent_cleanup is not None
            and independent_cleanup.stage_state == "running"
        ):
            return None
        job = await self._session.scalar(
            select(AsyncJob).where(
                AsyncJob.id == job_id,
                AsyncJob.type == "coach_attempt_processing",
                AsyncJob.status == "pending",
            )
        )
        if job is None:
            return None
        prior_claim = (prior_evaluation.diagnostics_json or {}).get(
            "processing_claim"
        )
        if (
            not isinstance(prior_claim, dict)
            or prior_claim.get("processing_generation")
            != attempt.processing_generation
            or prior_claim.get("processing_contract_version")
            != "coach_processing_v1"
            or prior_claim.get("source_audio_content_hash")
            != attempt.audio_content_hash
            or prior_evaluation.evaluation_contract_version != RUBRIC_CONTRACT
            or prior_evaluation.evidence_contract_version
            != EVIDENCE_GROUNDING_CONTRACT
            or prior_evaluation.follow_up_contract_version != FOLLOW_UP_CONTRACT
        ):
            return None
        prior_by_name = {stage.stage_name: stage for stage in prior_stages}
        if (
            len(prior_stages) != len(_PROCESSING_STAGE_ORDER)
            or set(prior_by_name) != set(_PROCESSING_STAGE_ORDER)
            or any(
                stage.stage_state in {"pending", "running"}
                for stage in processing_prior_stages
            )
            or not any(
                stage.stage_state == "failed_retryable"
                for stage in processing_prior_stages
            )
        ):
            return None

        transcript = (
            await self._session.get(
                InterviewTranscriptVersion, attempt.current_transcript_version_id
            )
            if attempt.current_transcript_version_id is not None
            else None
        )
        if transcript is None and (
            attempt.recording_type == "text"
            or not attempt.audio_uri
            or not attempt.audio_content_hash
        ):
            raise ConversationalRepositoryError(
                "coach_attempt_retry_source_unavailable"
            )
        if transcript is not None and (
            transcript.recording_id != attempt.id
            or not transcript.content_hash
            or prior_evaluation.transcript_version_id != transcript.id
        ):
            return None
        expected_prior_diagnostics = {
            stage_name: _stage_immutable_diagnostics(
                stage_name=stage_name,
                audio_content_hash=attempt.audio_content_hash,
                transcript_version_id=(transcript.id if transcript is not None else None),
                transcript_content_hash=(
                    transcript.content_hash if transcript is not None else None
                ),
                evaluation_contract_version=prior_evaluation.evaluation_contract_version,
                evidence_contract_version=prior_evaluation.evidence_contract_version,
                follow_up_contract_version=prior_evaluation.follow_up_contract_version,
            )
            for stage_name in _PROCESSING_STAGE_ORDER
        }
        try:
            prior_deadline = datetime.fromisoformat(prior_claim["job_deadline_at"])
        except (KeyError, TypeError, ValueError):
            return None
        prior_claim_token = prior_claim.get("claim_token")
        if (
            prior_evaluation.async_job_id is None
            or not isinstance(prior_claim_token, str)
            or not prior_claim_token
            or any(
                stage.job_id != prior_evaluation.async_job_id
                or stage.claim_token != prior_claim_token
                or stage.job_deadline_at != prior_deadline
                or stage.source_transcript_version_id
                != (
                    transcript.id
                    if transcript is not None
                    and stage.stage_name in _TRANSCRIPT_BOUND_STAGES
                    else None
                )
                for stage in processing_prior_stages
            )
        ):
            return None

        async def reuse_chain_is_valid(
            stage: InterviewAttemptStage,
            evaluation: InterviewAttemptEvaluation,
            visited: set[str],
        ) -> bool:
            from ..services.coach_processing_snapshot import (
                reused_stage_lineage_is_valid,
            )

            result_transcript = (
                await self._session.get(
                    InterviewTranscriptVersion, evaluation.transcript_version_id
                )
                if evaluation.transcript_version_id is not None
                else None
            )
            return await reused_stage_lineage_is_valid(
                self._session,
                attempt=attempt,
                evaluation=evaluation,
                stage=stage,
                result_transcript=result_transcript,
                visited=frozenset(visited),
            )

        valid_prior_result: dict[str, bool] = {}
        for stage_name, stage in prior_by_name.items():
            if stage is independent_cleanup:
                valid_prior_result[stage_name] = True
                continue
            reuse_is_valid = stage.stage_state != "reused" or await reuse_chain_is_valid(
                stage, prior_evaluation, set()
            )
            if stage.stage_state == "reused" and not reuse_is_valid:
                return None
            valid_prior_result[stage_name] = (
                stage.diagnostics_json == expected_prior_diagnostics[stage_name]
                and reuse_is_valid
            )
        effective_prior_states = {
            stage_name: (
                "not_started"
                if stage.stage_state in {"completed", "reused"}
                and not valid_prior_result[stage_name]
                else stage.stage_state
            )
            for stage_name, stage in prior_by_name.items()
        }
        audio_transcript_is_usable = bool(
            transcript is not None
            and prior_by_name["transcription"].stage_state
            in {"completed", "reused"}
            and valid_prior_result["transcription"]
        )
        has_audio_source = bool(
            attempt.audio_uri
            and attempt.audio_content_hash
            and valid_prior_result["audio_persist"]
        )
        try:
            restart_stage = select_restart_stage(
                effective_prior_states,
                {
                    "recording_type": attempt.recording_type,
                    "has_usable_transcript": (
                        transcript is not None
                        if attempt.recording_type == "text"
                        else audio_transcript_is_usable
                    ),
                    "has_audio_source": has_audio_source,
                },
            )
        except AttemptPipelineError as error:
            raise ConversationalRepositoryError(error.code) from error
        if restart_stage in {"transcription", "speech_analysis"}:
            upload_exists = await self._session.scalar(
                select(InterviewAttemptUpload.id).where(
                    InterviewAttemptUpload.attempt_id == attempt.id,
                    InterviewAttemptUpload.result_state == "completed",
                    InterviewAttemptUpload.content_sha256
                    == attempt.audio_content_hash,
                    InterviewAttemptUpload.storage_uri == attempt.audio_uri,
                )
            )
            if upload_exists is None:
                raise ConversationalRepositoryError(
                    "coach_attempt_retry_source_unavailable"
                )
            try:
                with open_verified_audio_read_lease(
                    Path(settings.HATCH_COACH_MEDIA_ROOT),
                    Path(attempt.audio_uri),
                    attempt.audio_content_hash,
                ):
                    pass
            except CoachMediaError:
                raise ConversationalRepositoryError(
                    "coach_attempt_retry_source_unavailable"
                ) from None

        invalidated = {
            "transcription": {
                "transcription",
                "content_evaluation",
                "evidence_grounding",
                "follow_up_decision",
                "coaching_enrichment",
            },
            "speech_analysis": {"speech_analysis"},
            "content_evaluation": {
                "content_evaluation",
                "evidence_grounding",
                "follow_up_decision",
                "coaching_enrichment",
            },
            "evidence_grounding": {
                "evidence_grounding",
                "follow_up_decision",
            },
            "follow_up_decision": {"follow_up_decision"},
            "coaching_enrichment": {"coaching_enrichment"},
        }[restart_stage]
        next_generation = attempt.processing_generation + 1
        next_evaluation_version = int(
            await self._session.scalar(
                select(func.max(InterviewAttemptEvaluation.version_number)).where(
                    InterviewAttemptEvaluation.recording_id == attempt.id
                )
            )
            or 0
        ) + 1
        claim_token = str(uuid.uuid4())
        source_transcript_id = transcript.id if transcript is not None else None
        claim_snapshot = {
            "processing_generation": next_generation,
            "job_deadline_at": deadline.isoformat(),
            "source_audio_content_hash": attempt.audio_content_hash,
            "source_transcript_version_id": source_transcript_id,
            "expected_session_state_version": expected_session_state_version,
            "processing_contract_version": "coach_processing_v1",
            "claim_token": claim_token,
        }
        now = datetime.utcnow()
        try:
            async with self._session.begin_nested():
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session.id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.conversation_state == "recoverable_error",
                        InterviewSession.recoverable_error_scope
                        == "attempt_processing",
                        InterviewSession.state_version
                        == expected_session_state_version,
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.active_question_id == attempt.question_id,
                        InterviewSession.active_recording_id == attempt.id,
                    )
                    .values(
                        conversation_state="processing_answer",
                        recoverable_error_scope=None,
                        recoverable_error_code=None,
                        recoverable_error_context_json=None,
                        state_version=InterviewSession.state_version + 1,
                        last_activity_at=now,
                    )
                )
                attempt_change = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == attempt.id,
                        SessionRecording.session_id == session.id,
                        SessionRecording.question_id == attempt.question_id,
                        SessionRecording.attempt_state == "recoverable_error",
                        SessionRecording.async_job_id.is_(None),
                        SessionRecording.processing_generation
                        == attempt.processing_generation,
                        SessionRecording.processing_retry_count
                        == attempt.processing_retry_count,
                        SessionRecording.processing_retry_count
                        < SessionRecording.processing_retry_limit,
                        SessionRecording.current_transcript_version_id
                        == source_transcript_id,
                        SessionRecording.current_evaluation_version_id
                        == attempt.current_evaluation_version_id,
                        SessionRecording.audio_content_hash
                        == attempt.audio_content_hash,
                        ~exists().where(
                            InterviewAttemptStage.recording_id == attempt.id,
                            InterviewAttemptStage.stage_name == "audio_cleanup",
                            InterviewAttemptStage.stage_state == "running",
                        ),
                    )
                    .values(
                        processing_generation=next_generation,
                        processing_retry_count=SessionRecording.processing_retry_count
                        + 1,
                        attempt_state="pending_processing",
                        evaluation_state="pending",
                        evaluation_json=None,
                        async_job_id=job.id,
                        processing_started_at=now,
                        processing_completed_at=None,
                    )
                )
                if session_change.rowcount != 1 or attempt_change.rowcount != 1:
                    raise _StaleFinalisation
                evaluation = InterviewAttemptEvaluation(
                    id=str(uuid.uuid4()),
                    recording_id=attempt.id,
                    transcript_version_id=source_transcript_id,
                    version_number=next_evaluation_version,
                    state="pending",
                    evaluation_contract_version=RUBRIC_CONTRACT,
                    evidence_contract_version=EVIDENCE_GROUNDING_CONTRACT,
                    follow_up_contract_version=FOLLOW_UP_CONTRACT,
                    async_job_id=job.id,
                    diagnostics_json={"processing_claim": claim_snapshot},
                )
                self._session.add(evaluation)
                await self._session.flush()
                for stage_name in _PROCESSING_STAGE_ORDER:
                    prior_stage = prior_by_name[stage_name]
                    if (
                        stage_name == "audio_cleanup"
                        and independent_cleanup is not None
                    ):
                        self._session.add(
                            InterviewAttemptStage(
                                id=str(uuid.uuid4()),
                                recording_id=attempt.id,
                                evaluation_version_id=evaluation.id,
                                stage_name="audio_cleanup",
                                stage_state=independent_cleanup.stage_state,
                                job_id=independent_cleanup.job_id,
                                claim_token=independent_cleanup.claim_token,
                                expected_processing_generation=next_generation,
                                source_transcript_version_id=None,
                                reused_from_stage_id=None,
                                job_deadline_at=independent_cleanup.job_deadline_at,
                                started_at=independent_cleanup.started_at,
                                completed_at=independent_cleanup.completed_at,
                                attempt_count=independent_cleanup.attempt_count,
                                repair_count=independent_cleanup.repair_count,
                                last_error_code=independent_cleanup.last_error_code,
                                diagnostics_json=_stage_immutable_diagnostics(
                                    stage_name="audio_cleanup",
                                    audio_content_hash=attempt.audio_content_hash,
                                    transcript_version_id=source_transcript_id,
                                    transcript_content_hash=(
                                        transcript.content_hash
                                        if transcript is not None
                                        else None
                                    ),
                                    evaluation_contract_version=RUBRIC_CONTRACT,
                                    evidence_contract_version=EVIDENCE_GROUNDING_CONTRACT,
                                    follow_up_contract_version=FOLLOW_UP_CONTRACT,
                                ),
                            )
                        )
                        continue
                    not_applicable = (
                        attempt.recording_type == "text"
                        and stage_name
                        in {
                            "audio_persist",
                            "transcription",
                            "speech_analysis",
                            "audio_cleanup",
                        }
                    )
                    reusable = (
                        not not_applicable
                        and stage_name not in invalidated
                        and stage_name != "audio_cleanup"
                        and prior_stage.stage_state in {"completed", "reused"}
                        and valid_prior_result[stage_name]
                    )
                    preserved_terminal_speech = (
                        stage_name == "speech_analysis"
                        and stage_name not in invalidated
                        and prior_stage.stage_state
                        in {"unavailable", "failed_terminal"}
                        and valid_prior_result[stage_name]
                    )
                    stage_state = (
                        "not_applicable"
                        if not_applicable
                        else "reused"
                        if reusable
                        else prior_stage.stage_state
                        if preserved_terminal_speech
                        else "pending"
                    )
                    self._session.add(
                        InterviewAttemptStage(
                            id=str(uuid.uuid4()),
                            recording_id=attempt.id,
                            evaluation_version_id=evaluation.id,
                            stage_name=stage_name,
                            stage_state=stage_state,
                            job_id=job.id,
                            claim_token=claim_token,
                            expected_processing_generation=next_generation,
                            source_transcript_version_id=(
                                source_transcript_id
                                if stage_name in _TRANSCRIPT_BOUND_STAGES
                                else None
                            ),
                            reused_from_stage_id=(
                                prior_stage.id if reusable else None
                            ),
                            job_deadline_at=deadline,
                            completed_at=(
                                now
                                if stage_state
                                in {
                                    "reused",
                                    "not_applicable",
                                    "unavailable",
                                    "failed_terminal",
                                }
                                else None
                            ),
                            last_error_code=(
                                prior_stage.last_error_code
                                if preserved_terminal_speech
                                else None
                            ),
                            diagnostics_json=_stage_immutable_diagnostics(
                                stage_name=stage_name,
                                audio_content_hash=attempt.audio_content_hash,
                                transcript_version_id=source_transcript_id,
                                transcript_content_hash=(
                                    transcript.content_hash
                                    if transcript is not None
                                    else None
                                ),
                                evaluation_contract_version=RUBRIC_CONTRACT,
                                evidence_contract_version=EVIDENCE_GROUNDING_CONTRACT,
                                follow_up_contract_version=FOLLOW_UP_CONTRACT,
                            ),
                        )
                    )
                await self._session.flush()
        except _StaleFinalisation:
            return None
        return AttemptProcessingClaim(
            session_id=session.id,
            question_id=attempt.question_id or "",
            recording_id=attempt.id,
            transcript_version_id=source_transcript_id,
            evaluation_version_id=evaluation.id,
            processing_generation=next_generation,
            job_id=job.id,
            deadline_at=deadline,
        )

    async def claim_attempt_processing(
        self,
        *,
        recording_id: str,
        expected_generation: int,
        job_id: str,
        deadline: datetime,
    ) -> AttemptProcessingClaim | None:
        attempt = await self._session.get(SessionRecording, recording_id)
        if (
            attempt is None
            or attempt.processing_generation != expected_generation
            or attempt.attempt_state not in {"draft", "uploaded", "recoverable_error"}
        ):
            return None
        source_transcript_version_id = attempt.current_transcript_version_id
        current_evaluation_version_id = attempt.current_evaluation_version_id
        if attempt.recording_type == "text" and source_transcript_version_id is None:
            return None
        source_audio_content_hash = attempt.audio_content_hash
        if attempt.recording_type == "audio" and not source_audio_content_hash:
            return None
        session_row = await self._session.get(InterviewSession, attempt.session_id)
        retry_claim = attempt.attempt_state == "recoverable_error"
        required_parent_state = "recoverable_error" if retry_claim else "listening"
        if (
            session_row is None
            or session_row.experience_version != "conversational_v1"
            or session_row.status != "active"
            or session_row.conversation_state != required_parent_state
            or (
                retry_claim
                and session_row.recoverable_error_scope != "attempt_processing"
            )
            or session_row.deletion_state != "not_requested"
            or session_row.active_question_id != attempt.question_id
            or session_row.active_recording_id != attempt.id
        ):
            return None
        next_generation = expected_generation + 1
        claim_token = str(uuid.uuid4())
        claim_snapshot = {
            "processing_generation": next_generation,
            "job_deadline_at": deadline.isoformat(),
            "source_audio_content_hash": source_audio_content_hash,
            "source_transcript_version_id": source_transcript_version_id,
            "expected_session_state_version": session_row.state_version,
            "processing_contract_version": "coach_processing_v1",
            "claim_token": claim_token,
        }
        try:
            async with self._session.begin_nested():
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session_row.id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.conversation_state == required_parent_state,
                        *(
                            (
                                InterviewSession.recoverable_error_scope
                                == "attempt_processing",
                            )
                            if retry_claim
                            else ()
                        ),
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.active_question_id == attempt.question_id,
                        InterviewSession.active_recording_id == attempt.id,
                        InterviewSession.state_version == session_row.state_version,
                    )
                    .values(state_version=InterviewSession.state_version)
                )
                if session_change.rowcount != 1:
                    raise _StaleFinalisation
                changed = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.processing_generation == expected_generation,
                        SessionRecording.attempt_state.in_(
                            ("draft", "uploaded", "recoverable_error")
                        ),
                        SessionRecording.current_transcript_version_id
                        == source_transcript_version_id,
                        SessionRecording.audio_content_hash
                        == source_audio_content_hash,
                        SessionRecording.current_evaluation_version_id
                        == current_evaluation_version_id,
                    )
                    .values(
                        processing_generation=next_generation,
                        attempt_state="pending_processing",
                        evaluation_state="pending",
                        async_job_id=job_id,
                        submitted_at=datetime.utcnow(),
                        processing_started_at=datetime.utcnow(),
                        processing_completed_at=None,
                    )
                )
                if changed.rowcount != 1:
                    raise _StaleFinalisation
                evaluation = await self._session.scalar(
                    select(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.recording_id == recording_id,
                        InterviewAttemptEvaluation.async_job_id == job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.transcript_version_id
                        == source_transcript_version_id,
                        InterviewAttemptEvaluation.diagnostics_json[
                            "processing_generation"
                        ].as_integer()
                        == next_generation,
                    )
                    .order_by(InterviewAttemptEvaluation.version_number.desc())
                    .limit(1)
                )
                if evaluation is None:
                    raise _StaleFinalisation
                evaluation_change = await self._session.execute(
                    update(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.id == evaluation.id,
                        InterviewAttemptEvaluation.recording_id == recording_id,
                        InterviewAttemptEvaluation.async_job_id == job_id,
                        InterviewAttemptEvaluation.state == "pending",
                    )
                    .values(diagnostics_json={"processing_claim": claim_snapshot})
                )
                if evaluation_change.rowcount != 1:
                    raise _StaleFinalisation
                await self._session.flush()
        except _StaleFinalisation:
            return None
        return AttemptProcessingClaim(
            session_id=attempt.session_id,
            question_id=attempt.question_id or "",
            recording_id=attempt.id,
            transcript_version_id=evaluation.transcript_version_id,
            evaluation_version_id=evaluation.id,
            processing_generation=next_generation,
            job_id=job_id,
            deadline_at=deadline,
        )

    async def _get_attempt_processing_fence(
        self, claim: AttemptProcessingClaim
    ) -> _AttemptProcessingFence | None:
        evaluation = await self._session.scalar(
            select(InterviewAttemptEvaluation).where(
                InterviewAttemptEvaluation.id == claim.evaluation_version_id,
                InterviewAttemptEvaluation.recording_id == claim.recording_id,
                InterviewAttemptEvaluation.async_job_id == claim.job_id,
            )
        )
        claim_data = (
            (evaluation.diagnostics_json or {}).get("processing_claim")
            if evaluation is not None
            else None
        )
        if not isinstance(claim_data, dict):
            return None
        try:
            deadline_at = datetime.fromisoformat(claim_data["job_deadline_at"])
            expected_session_state_version = claim_data[
                "expected_session_state_version"
            ]
            processing_contract_version = claim_data["processing_contract_version"]
            claim_token = claim_data["claim_token"]
        except (KeyError, TypeError, ValueError):
            return None
        if (
            deadline_at != claim.deadline_at
            or claim_data.get("processing_generation") != claim.processing_generation
            or type(expected_session_state_version) is not int
            or not isinstance(processing_contract_version, str)
            or not isinstance(claim_token, str)
            or not claim_token
        ):
            return None
        source_audio_content_hash = claim_data.get("source_audio_content_hash")
        source_transcript_version_id = claim_data.get("source_transcript_version_id")
        if (
            source_audio_content_hash is not None
            and not isinstance(source_audio_content_hash, str)
        ) or (
            source_transcript_version_id is not None
            and not isinstance(source_transcript_version_id, str)
        ):
            return None
        return _AttemptProcessingFence(
            expected_audio_content_hash=source_audio_content_hash,
            source_transcript_version_id=source_transcript_version_id,
            expected_session_state_version=expected_session_state_version,
            processing_contract_version=processing_contract_version,
            claim_token=claim_token,
        )

    async def get_attempt_processing_snapshot(
        self, *, recording_id: str, processing_generation: int
    ) -> AttemptProcessingSnapshot | None:
        attempt = await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.id == recording_id,
                SessionRecording.processing_generation == processing_generation,
                SessionRecording.attempt_state == "pending_processing",
            )
        )
        if attempt is None or attempt.async_job_id is None:
            return None
        evaluation = await self._session.scalar(
            select(InterviewAttemptEvaluation)
            .where(
                InterviewAttemptEvaluation.recording_id == recording_id,
                InterviewAttemptEvaluation.async_job_id == attempt.async_job_id,
                InterviewAttemptEvaluation.state == "pending",
            )
            .order_by(InterviewAttemptEvaluation.version_number.desc())
            .limit(1)
        )
        if evaluation is None:
            return None
        claim_data = (evaluation.diagnostics_json or {}).get("processing_claim")
        if not isinstance(claim_data, dict):
            return None
        try:
            deadline_at = datetime.fromisoformat(claim_data["job_deadline_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if claim_data.get("processing_generation") != processing_generation:
            return None
        claim = AttemptProcessingClaim(
            session_id=attempt.session_id,
            question_id=attempt.question_id or "",
            recording_id=attempt.id,
            transcript_version_id=evaluation.transcript_version_id,
            evaluation_version_id=evaluation.id,
            processing_generation=processing_generation,
            job_id=attempt.async_job_id,
            deadline_at=deadline_at,
        )
        return AttemptProcessingSnapshot(claim, attempt.attempt_state, evaluation.state)

    async def persist_attempt_stage_counters(
        self,
        *,
        claim: AttemptProcessingClaim,
        stage_name: str,
        attempt_count: int,
        repair_count: int,
    ) -> bool:
        """Conditionally persist internal work without spending manual retries."""
        limits = _PROCESSING_STAGE_COUNTER_LIMITS.get(stage_name)
        now = datetime.utcnow()
        if (
            limits is None
            or type(attempt_count) is not int
            or type(repair_count) is not int
            or attempt_count < 1
            or repair_count < 0
            or attempt_count > limits[0]
            or repair_count > limits[1]
            or now > claim.deadline_at
        ):
            return False
        fence = await self._get_attempt_processing_fence(claim)
        if (
            fence is None
            or fence.processing_contract_version != "coach_processing_v1"
        ):
            return False
        expected_source = (
            claim.transcript_version_id
            if stage_name in _TRANSCRIPT_BOUND_STAGES
            else None
        )
        current_session = exists().where(
            InterviewSession.id == claim.session_id,
            InterviewSession.experience_version == "conversational_v1",
            InterviewSession.status == "active",
            InterviewSession.conversation_state == "processing_answer",
            InterviewSession.deletion_state == "not_requested",
            InterviewSession.active_question_id == claim.question_id,
            InterviewSession.active_recording_id == claim.recording_id,
        )
        current_attempt = exists().where(
            SessionRecording.id == claim.recording_id,
            SessionRecording.session_id == claim.session_id,
            SessionRecording.question_id == claim.question_id,
            SessionRecording.async_job_id == claim.job_id,
            SessionRecording.processing_generation == claim.processing_generation,
            SessionRecording.attempt_state == "pending_processing",
            SessionRecording.evaluation_state == "pending",
            SessionRecording.audio_content_hash == fence.expected_audio_content_hash,
            SessionRecording.current_transcript_version_id
            == claim.transcript_version_id,
        )
        current_evaluation = exists().where(
            InterviewAttemptEvaluation.id == claim.evaluation_version_id,
            InterviewAttemptEvaluation.recording_id == claim.recording_id,
            InterviewAttemptEvaluation.async_job_id == claim.job_id,
            InterviewAttemptEvaluation.transcript_version_id
            == claim.transcript_version_id,
            InterviewAttemptEvaluation.state == "pending",
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"]
            ["processing_generation"].as_integer()
            == claim.processing_generation,
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"]
            ["job_deadline_at"].as_string()
            == claim.deadline_at.isoformat(),
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"]
            ["processing_contract_version"].as_string()
            == fence.processing_contract_version,
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"]
            ["claim_token"].as_string()
            == fence.claim_token,
        )
        current_job = exists().where(
            AsyncJob.id == claim.job_id,
            AsyncJob.type == "coach_attempt_processing",
            AsyncJob.status.in_(("pending", "running")),
        )
        changed = await self._session.execute(
            update(InterviewAttemptStage)
            .where(
                InterviewAttemptStage.recording_id == claim.recording_id,
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id,
                InterviewAttemptStage.stage_name == stage_name,
                InterviewAttemptStage.stage_state.in_(("pending", "running")),
                InterviewAttemptStage.job_id == claim.job_id,
                InterviewAttemptStage.claim_token == fence.claim_token,
                InterviewAttemptStage.expected_processing_generation
                == claim.processing_generation,
                InterviewAttemptStage.source_transcript_version_id
                == expected_source,
                InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                InterviewAttemptStage.job_deadline_at >= now,
                InterviewAttemptStage.attempt_count <= attempt_count,
                InterviewAttemptStage.repair_count <= repair_count,
                current_session,
                current_attempt,
                current_evaluation,
                current_job,
            )
            .values(
                attempt_count=attempt_count,
                repair_count=repair_count,
                started_at=func.coalesce(
                    InterviewAttemptStage.started_at,
                    now,
                ),
            )
        )
        return changed.rowcount == 1

    async def finalise_attempt_processing(
        self, *, claim: AttemptProcessingClaim, result: AttemptProcessingResult
    ) -> bool:
        _validate_processing_diagnostics(
            result.diagnostics, evaluation_state=result.evaluation_state
        )
        try:
            async with self._session.begin_nested():
                if datetime.utcnow() > claim.deadline_at:
                    raise _StaleFinalisation
                fence = await self._get_attempt_processing_fence(claim)
                if (
                    fence is None
                    or fence.processing_contract_version != "coach_processing_v1"
                ):
                    raise _StaleFinalisation
                parent_is_current = await self._session.scalar(
                    select(InterviewSession.id).where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.conversation_state == "processing_answer",
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.active_question_id == claim.question_id,
                        InterviewSession.active_recording_id == claim.recording_id,
                    )
                )
                if parent_is_current is None:
                    raise _StaleFinalisation
                claim_snapshot = {
                    "processing_generation": claim.processing_generation,
                    "job_deadline_at": claim.deadline_at.isoformat(),
                    "source_audio_content_hash": fence.expected_audio_content_hash,
                    "source_transcript_version_id": fence.source_transcript_version_id,
                    "expected_session_state_version": (
                        fence.expected_session_state_version
                    ),
                    "processing_contract_version": fence.processing_contract_version,
                    "claim_token": fence.claim_token,
                }
                attempt = await self._session.scalar(
                    select(SessionRecording).where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.question_id == claim.question_id,
                        SessionRecording.async_job_id == claim.job_id,
                        SessionRecording.processing_generation
                        == claim.processing_generation,
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.evaluation_state == "pending",
                        SessionRecording.audio_content_hash
                        == fence.expected_audio_content_hash,
                    )
                )
                if attempt is None:
                    raise _StaleFinalisation
                evaluation = await self._session.scalar(
                    select(InterviewAttemptEvaluation).where(
                        InterviewAttemptEvaluation.id == claim.evaluation_version_id,
                        InterviewAttemptEvaluation.recording_id == claim.recording_id,
                        InterviewAttemptEvaluation.async_job_id == claim.job_id,
                        InterviewAttemptEvaluation.state == "pending",
                    )
                )
                if (
                    evaluation is None
                    or (evaluation.diagnostics_json or {}).get("processing_claim")
                    != claim_snapshot
                ):
                    raise _StaleFinalisation
                stages = (
                    await self._session.scalars(
                        select(InterviewAttemptStage).where(
                            InterviewAttemptStage.recording_id == claim.recording_id,
                            InterviewAttemptStage.evaluation_version_id
                            == claim.evaluation_version_id,
                        )
                    )
                ).all()
                if attempt.audio_retention_state in {
                    "delete_pending",
                    "deleted",
                    "delete_failed",
                } and (
                    len(stages) != len(_PROCESSING_STAGE_ORDER)
                    or {stage.stage_name for stage in stages}
                    != set(_PROCESSING_STAGE_ORDER)
                ):
                    raise _StaleFinalisation
                partition = await partition_current_processing_stages(
                    self._session,
                    attempt=attempt,
                    evaluation=evaluation,
                    stages=stages,
                    processing_job_id=claim.job_id,
                )
                if partition is None:
                    raise _StaleFinalisation
                processing_stages, independent_cleanup = partition
                terminal_states = {
                    "completed",
                    "reused",
                    "not_applicable",
                    "unavailable",
                    "failed_terminal",
                }
                terminal_processing_stages = (
                    processing_stages
                    if independent_cleanup is not None
                    else tuple(
                        stage
                        for stage in stages
                        if stage.job_id == claim.job_id
                        and stage.expected_processing_generation
                        == claim.processing_generation
                    )
                )
                stage_by_name = {
                    stage.stage_name: stage for stage in terminal_processing_stages
                }
                if not terminal_processing_stages or any(
                    stage.stage_state not in terminal_states
                    for stage in terminal_processing_stages
                ):
                    raise _StaleFinalisation
                if any(
                    stage.job_deadline_at != claim.deadline_at
                    or (
                        independent_cleanup is not None
                        and (
                            stage.job_id != claim.job_id
                            or stage.expected_processing_generation
                            != claim.processing_generation
                            or stage.claim_token != fence.claim_token
                        )
                    )
                    for stage in terminal_processing_stages
                ):
                    raise _StaleFinalisation
                transcript_bound_stages = {
                    "content_evaluation",
                    "evidence_grounding",
                    "follow_up_decision",
                    "coaching_enrichment",
                }
                if any(
                    stage.stage_name in transcript_bound_stages
                    and stage.source_transcript_version_id
                    != result.transcript_version_id
                    for stage in terminal_processing_stages
                ):
                    raise _StaleFinalisation

                from ..services.coach_processing_snapshot import (
                    ProcessingSnapshot,
                    current_processing_graph_reuse_is_valid,
                )

                if not await current_processing_graph_reuse_is_valid(
                    self._session,
                    attempt=attempt,
                    evaluation=evaluation,
                    stages=terminal_processing_stages,
                    snapshot=ProcessingSnapshot(
                        claim=claim_snapshot,
                        deadline=claim.deadline_at,
                        transcript_version_id=evaluation.transcript_version_id,
                    ),
                ):
                    raise _StaleFinalisation
                audio_retry_reuse = bool(
                    attempt.recording_type == "audio"
                    and fence.source_transcript_version_id is not None
                )
                transcript = None
                if result.transcript_version_id is not None:
                    transcript_query = select(InterviewTranscriptVersion).where(
                            InterviewTranscriptVersion.id
                            == result.transcript_version_id,
                            InterviewTranscriptVersion.recording_id
                            == claim.recording_id,
                        )
                    if not audio_retry_reuse:
                        transcript_query = transcript_query.where(
                            InterviewTranscriptVersion.processing_generation
                            == claim.processing_generation
                        )
                    transcript = await self._session.scalar(transcript_query)
                if result.evaluation_state == "completed":
                    if (
                        result.transcript_version_id is None
                        or transcript is None
                        or (
                            attempt.recording_type == "text"
                            and result.transcript_version_id
                            != fence.source_transcript_version_id
                        )
                        or (
                            attempt.recording_type == "audio"
                            and (
                                fence.source_transcript_version_id is not None
                                and not audio_retry_reuse
                            )
                        )
                        or attempt.current_transcript_version_id
                        != result.transcript_version_id
                        or evaluation.transcript_version_id
                        != result.transcript_version_id
                        or stage_by_name.get("content_evaluation") is None
                        or stage_by_name["content_evaluation"].stage_state
                        != "completed"
                        or stage_by_name.get("evidence_grounding") is None
                        or stage_by_name["evidence_grounding"].stage_state
                        not in {"completed", "unavailable"}
                        or stage_by_name.get("follow_up_decision") is None
                        or stage_by_name["follow_up_decision"].stage_state
                        not in {"completed", "unavailable", "not_applicable"}
                    ):
                        raise _StaleFinalisation
                else:
                    reason = result.diagnostics.get(
                        "reason_code",
                        result.diagnostics.get(
                            "reason", result.diagnostics.get("code")
                        ),
                    )
                    transcription = stage_by_name.get("transcription")
                    downstream = {
                        "content_evaluation",
                        "evidence_grounding",
                        "follow_up_decision",
                        "coaching_enrichment",
                    }
                    if result.transcript_version_id is None:
                        created_transcript = await self._session.scalar(
                            select(InterviewTranscriptVersion.id).where(
                                InterviewTranscriptVersion.recording_id
                                == claim.recording_id,
                                InterviewTranscriptVersion.processing_generation
                                == claim.processing_generation,
                            )
                        )
                        if (
                            attempt.recording_type != "audio"
                            or evaluation.transcript_version_id is not None
                            or attempt.current_transcript_version_id is not None
                            or created_transcript is not None
                            or reason not in AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS
                            or transcription is None
                            or transcription.stage_state
                            not in {"unavailable", "failed_terminal"}
                            or transcription.last_error_code != reason
                            or any(
                                name in downstream
                                and stage.stage_state in {"completed", "reused"}
                                for name, stage in stage_by_name.items()
                            )
                        ):
                            raise _StaleFinalisation
                    else:
                        content_evaluation = stage_by_name.get("content_evaluation")
                        if (
                            transcript is None
                            or evaluation.transcript_version_id
                            != result.transcript_version_id
                            or attempt.current_transcript_version_id
                            != result.transcript_version_id
                            or (
                                attempt.recording_type == "text"
                                and result.transcript_version_id
                                != fence.source_transcript_version_id
                            )
                            or (
                                attempt.recording_type == "audio"
                                and (
                                    (
                                        fence.source_transcript_version_id is not None
                                        and not audio_retry_reuse
                                    )
                                    or transcription is None
                                    or transcription.stage_state
                                    not in {"completed", "reused"}
                                )
                            )
                            or reason not in TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS
                            or content_evaluation is None
                            or content_evaluation.stage_state
                            not in {"unavailable", "failed_terminal"}
                            or content_evaluation.last_error_code != reason
                            or any(
                                name
                                in {
                                    "evidence_grounding",
                                    "follow_up_decision",
                                    "coaching_enrichment",
                                }
                                and stage.stage_state in {"completed", "reused"}
                                for name, stage in stage_by_name.items()
                            )
                        ):
                            raise _StaleFinalisation

                prior_current_id = attempt.current_evaluation_version_id
                if (
                    prior_current_id is not None
                    and prior_current_id != claim.evaluation_version_id
                ):
                    prior_change = await self._session.execute(
                        update(InterviewAttemptEvaluation)
                        .where(
                            InterviewAttemptEvaluation.id == prior_current_id,
                            InterviewAttemptEvaluation.recording_id
                            == claim.recording_id,
                            InterviewAttemptEvaluation.state.in_(
                                ("completed", "unavailable", "invalid", "failed")
                            ),
                        )
                        .values(state="superseded")
                    )
                    if prior_change.rowcount != 1:
                        raise _StaleFinalisation
                attempt_change = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.question_id == claim.question_id,
                        SessionRecording.async_job_id == claim.job_id,
                        SessionRecording.processing_generation
                        == claim.processing_generation,
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.evaluation_state == "pending",
                        SessionRecording.audio_content_hash
                        == fence.expected_audio_content_hash,
                        SessionRecording.current_transcript_version_id
                        == result.transcript_version_id,
                    )
                    .values(
                        attempt_state=result.evaluation_state,
                        evaluation_state=result.evaluation_state,
                        evaluation_json=json.dumps(
                            result.evaluation_json,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        current_evaluation_version_id=claim.evaluation_version_id,
                        processing_completed_at=datetime.utcnow(),
                        async_job_id=None,
                    )
                )
                if attempt_change.rowcount != 1:
                    raise _StaleFinalisation
                evaluation_change = await self._session.execute(
                    update(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.id == claim.evaluation_version_id,
                        InterviewAttemptEvaluation.recording_id == claim.recording_id,
                        InterviewAttemptEvaluation.async_job_id == claim.job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.transcript_version_id
                        == result.transcript_version_id,
                    )
                    .values(
                        state=result.evaluation_state,
                        rubric_json=result.evaluation_json,
                        diagnostics_json={
                            "processing_claim": claim_snapshot,
                            "result": result.diagnostics,
                        },
                        completed_at=datetime.utcnow(),
                    )
                )
                if evaluation_change.rowcount != 1:
                    raise _StaleFinalisation
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.conversation_state == "processing_answer",
                        InterviewSession.active_question_id == claim.question_id,
                        InterviewSession.active_recording_id == claim.recording_id,
                    )
                    .values(
                        conversation_state="awaiting_next_action",
                        state_version=InterviewSession.state_version + 1,
                        activity_version=InterviewSession.activity_version + 1,
                        last_activity_at=datetime.utcnow(),
                    )
                    .returning(InterviewSession.state_version)
                )
                state_version = session_change.scalar_one_or_none()
                if state_version is None:
                    raise _StaleFinalisation
                await self.append_session_events(
                    session_id=claim.session_id,
                    events=(
                        SessionEventInput(
                            event_type=(
                                "attempt_processing_completed"
                                if result.evaluation_state == "completed"
                                else "attempt_processing_failed"
                            ),
                            actor_type="worker",
                            state_version=state_version,
                            state_before="processing_answer",
                            state_after="awaiting_next_action",
                            question_id=claim.question_id,
                            recording_id=claim.recording_id,
                            payload_json={"state": result.evaluation_state},
                        ),
                    ),
                )
                await self._session.flush()
        except _StaleFinalisation:
            return False
        return True

    async def finalise_invalid_attempt_media(
        self, *, claim: AttemptProcessingClaim, reason: str = "invalid_audio"
    ) -> bool:
        """Fence invalid media as a terminal, non-acceptable attempt."""
        if reason != "invalid_audio":
            return False
        try:
            async with self._session.begin_nested():
                if datetime.utcnow() > claim.deadline_at:
                    raise _StaleFinalisation
                fence = await self._get_attempt_processing_fence(claim)
                if (
                    fence is None
                    or fence.expected_audio_content_hash is None
                    or fence.source_transcript_version_id is not None
                    or fence.processing_contract_version != "coach_processing_v1"
                ):
                    raise _StaleFinalisation
                evaluation = await self._session.get(
                    InterviewAttemptEvaluation, claim.evaluation_version_id
                )
                expected_claim = {
                    "processing_generation": claim.processing_generation,
                    "job_deadline_at": claim.deadline_at.isoformat(),
                    "source_audio_content_hash": fence.expected_audio_content_hash,
                    "source_transcript_version_id": fence.source_transcript_version_id,
                    "expected_session_state_version": fence.expected_session_state_version,
                    "processing_contract_version": fence.processing_contract_version,
                    "claim_token": fence.claim_token,
                }
                if (
                    evaluation is None
                    or (evaluation.diagnostics_json or {}).get("processing_claim") != expected_claim
                ):
                    raise _StaleFinalisation
                stages = (
                    await self._session.scalars(
                        select(InterviewAttemptStage).where(
                            InterviewAttemptStage.recording_id == claim.recording_id,
                            InterviewAttemptStage.evaluation_version_id == claim.evaluation_version_id,
                            InterviewAttemptStage.job_id == claim.job_id,
                            InterviewAttemptStage.expected_processing_generation == claim.processing_generation,
                            InterviewAttemptStage.claim_token == fence.claim_token,
                            InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                        )
                    )
                ).all()
                stage_by_name = {stage.stage_name: stage for stage in stages}
                required_stages = {
                    "audio_persist", "transcription", "speech_analysis",
                    "content_evaluation", "evidence_grounding", "follow_up_decision",
                    "coaching_enrichment", "audio_cleanup",
                }
                transcript_exists = await self._session.scalar(
                    select(InterviewTranscriptVersion.id).where(
                        InterviewTranscriptVersion.recording_id == claim.recording_id,
                        InterviewTranscriptVersion.processing_generation
                        == claim.processing_generation,
                    )
                )
                downstream = {"content_evaluation", "evidence_grounding", "follow_up_decision", "coaching_enrichment"}
                terminal = {"completed", "reused", "not_applicable", "unavailable", "failed_terminal"}
                if (
                    set(stage_by_name) != required_stages
                    or len(stages) != 8
                    or transcript_exists is not None
                    or any(stage.stage_state not in terminal for stage in stages)
                    or any(stage.source_transcript_version_id is not None for stage in stages)
                    or stage_by_name["audio_persist"].stage_state != "unavailable"
                    or stage_by_name["audio_persist"].last_error_code != reason
                    or stage_by_name["transcription"].stage_state != "unavailable"
                    or stage_by_name["transcription"].last_error_code != reason
                    or any(stage_by_name[name].stage_state in {"completed", "reused"} for name in downstream)
                ):
                    raise _StaleFinalisation
                prior_current_id = await self._session.scalar(
                    select(SessionRecording.current_evaluation_version_id).where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.question_id == claim.question_id,
                        SessionRecording.async_job_id == claim.job_id,
                        SessionRecording.processing_generation == claim.processing_generation,
                        SessionRecording.attempt_state == "pending_processing",
                    )
                )
                if (
                    prior_current_id is not None
                    and prior_current_id != claim.evaluation_version_id
                ):
                    superseded = await self._session.execute(
                        update(InterviewAttemptEvaluation)
                        .where(
                            InterviewAttemptEvaluation.id == prior_current_id,
                            InterviewAttemptEvaluation.recording_id == claim.recording_id,
                            InterviewAttemptEvaluation.state.in_(
                                ("completed", "unavailable", "invalid", "failed")
                            ),
                        )
                        .values(state="superseded")
                    )
                    if superseded.rowcount != 1:
                        raise _StaleFinalisation
                attempt_change = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.question_id == claim.question_id,
                        SessionRecording.async_job_id == claim.job_id,
                        SessionRecording.processing_generation == claim.processing_generation,
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.evaluation_state == "pending",
                        SessionRecording.recording_type == "audio",
                        SessionRecording.audio_content_hash == fence.expected_audio_content_hash,
                        SessionRecording.current_transcript_version_id.is_(None),
                    )
                    .values(
                        attempt_state="invalid", evaluation_state="invalid",
                        evaluation_json=json.dumps({"answer_level": "not_assessed"}),
                        current_evaluation_version_id=claim.evaluation_version_id,
                        async_job_id=None, processing_completed_at=datetime.utcnow(),
                    )
                )
                evaluation_change = await self._session.execute(
                    update(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.id == claim.evaluation_version_id,
                        InterviewAttemptEvaluation.recording_id == claim.recording_id,
                        InterviewAttemptEvaluation.async_job_id == claim.job_id,
                        InterviewAttemptEvaluation.state == "pending",
                        InterviewAttemptEvaluation.transcript_version_id.is_(None),
                        InterviewAttemptEvaluation.diagnostics_json
                        == {"processing_claim": expected_claim},
                    )
                    .values(
                        state="invalid",
                        diagnostics_json={
                            "processing_claim": expected_claim,
                            "result": {"reason": reason},
                        },
                        completed_at=datetime.utcnow(),
                    )
                )
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.status == "active",
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.conversation_state == "processing_answer",
                        InterviewSession.active_question_id == claim.question_id,
                        InterviewSession.active_recording_id == claim.recording_id,
                        InterviewSession.deletion_state == "not_requested",
                    )
                    .values(
                        status="failed",
                        conversation_state="failed",
                        state_version=InterviewSession.state_version + 1,
                        activity_version=InterviewSession.activity_version + 1,
                        last_activity_at=datetime.utcnow(),
                    )
                    .returning(InterviewSession.state_version)
                )
                state_version = session_change.scalar_one_or_none()
                if attempt_change.rowcount != 1 or evaluation_change.rowcount != 1 or state_version is None:
                    raise _StaleFinalisation
                await self.append_session_events(
                    session_id=claim.session_id,
                    events=(
                        SessionEventInput(
                            event_type="attempt_processing_failed",
                            actor_type="worker",
                            state_version=state_version,
                            state_before="processing_answer",
                            state_after="failed",
                            question_id=claim.question_id,
                            recording_id=claim.recording_id,
                            payload_json={"state": "invalid", "reason": reason},
                        ),
                    ),
                )
        except _StaleFinalisation:
            return False
        return True

    async def accept_attempt(
        self,
        *,
        session_id: str,
        question_id: str,
        attempt_id: str,
        expected_state_version: int,
    ) -> AcceptanceResult:
        session_row = await self._session.get(InterviewSession, session_id)
        attempt = await self._session.get(SessionRecording, attempt_id)
        evaluation_id = (
            attempt.current_evaluation_version_id if attempt is not None else None
        )
        evaluation = (
            await self._session.get(InterviewAttemptEvaluation, evaluation_id)
            if evaluation_id is not None
            else None
        )
        reported_evaluation_state = (
            evaluation.state
            if evaluation is not None
            else (attempt.evaluation_state if attempt is not None else None)
        )

        def rejected() -> AcceptanceResult:
            return AcceptanceResult(
                False,
                attempt_id,
                None,
                session_row.state_version if session_row is not None else None,
                session_row.conversation_state if session_row is not None else None,
                evaluation_id,
                reported_evaluation_state,
            )

        if (
            session_row is None
            or session_row.experience_version != "conversational_v1"
            or session_row.status != "active"
            or session_row.deletion_state != "not_requested"
            or session_row.state_version != expected_state_version
            or session_row.active_question_id != question_id
            or session_row.conversation_state
            not in {"awaiting_next_action", "coaching"}
            or attempt is None
            or attempt.session_id != session_id
            or attempt.question_id != question_id
            or attempt.attempt_state not in {"completed", "unavailable"}
            or attempt.evaluation_state not in {"completed", "unavailable"}
            or evaluation is None
            or evaluation.recording_id != attempt_id
            or evaluation.state not in {"completed", "unavailable"}
            or evaluation.state != attempt.evaluation_state
            or ((evaluation.diagnostics_json or {}).get("processing_claim") or {}).get(
                "processing_generation"
            )
            != attempt.processing_generation
        ):
            return rejected()
        if evaluation.transcript_version_id != attempt.current_transcript_version_id:
            return rejected()
        if attempt.current_transcript_version_id is not None:
            transcript = await self._session.scalar(
                select(InterviewTranscriptVersion.id).where(
                    InterviewTranscriptVersion.id
                    == attempt.current_transcript_version_id,
                    InterviewTranscriptVersion.recording_id == attempt_id,
                    InterviewTranscriptVersion.processing_generation
                    == attempt.processing_generation,
                )
            )
            if transcript is None:
                return rejected()
            if attempt.attempt_state == "unavailable":
                result_diagnostics = (evaluation.diagnostics_json or {}).get(
                    "result"
                ) or {}
                reason = result_diagnostics.get(
                    "reason_code",
                    result_diagnostics.get("reason", result_diagnostics.get("code")),
                )
                content_evaluation = await self._session.scalar(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == attempt_id,
                        InterviewAttemptStage.evaluation_version_id == evaluation_id,
                        InterviewAttemptStage.stage_name == "content_evaluation",
                        InterviewAttemptStage.stage_state.in_(
                            ("unavailable", "failed_terminal")
                        ),
                        InterviewAttemptStage.last_error_code == reason,
                    )
                )
                completed_downstream = await self._session.scalar(
                    select(InterviewAttemptStage.id).where(
                        InterviewAttemptStage.recording_id == attempt_id,
                        InterviewAttemptStage.evaluation_version_id == evaluation_id,
                        InterviewAttemptStage.stage_name.in_(
                            (
                                "evidence_grounding",
                                "follow_up_decision",
                                "coaching_enrichment",
                            )
                        ),
                        InterviewAttemptStage.stage_state.in_(("completed", "reused")),
                    )
                )
                transcription_completed = True
                if attempt.recording_type == "audio":
                    transcription_completed = (
                        await self._session.scalar(
                            select(InterviewAttemptStage.id).where(
                                InterviewAttemptStage.recording_id == attempt_id,
                                InterviewAttemptStage.evaluation_version_id
                                == evaluation_id,
                                InterviewAttemptStage.stage_name == "transcription",
                                InterviewAttemptStage.stage_state == "completed",
                            )
                        )
                        is not None
                    )
                if (
                    reason not in TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS
                    or content_evaluation is None
                    or completed_downstream is not None
                    or not transcription_completed
                ):
                    return rejected()
        elif attempt.attempt_state == "completed":
            return rejected()
        else:
            result_diagnostics = (evaluation.diagnostics_json or {}).get("result") or {}
            reason = result_diagnostics.get(
                "reason_code", result_diagnostics.get("reason")
            )
            transcription = await self._session.scalar(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == attempt_id,
                    InterviewAttemptStage.evaluation_version_id == evaluation_id,
                    InterviewAttemptStage.stage_name == "transcription",
                    InterviewAttemptStage.stage_state.in_(
                        ("unavailable", "failed_terminal")
                    ),
                    InterviewAttemptStage.last_error_code == reason,
                )
            )
            created_transcript = await self._session.scalar(
                select(InterviewTranscriptVersion.id).where(
                    InterviewTranscriptVersion.recording_id == attempt_id,
                    InterviewTranscriptVersion.processing_generation
                    == attempt.processing_generation,
                )
            )
            completed_downstream = await self._session.scalar(
                select(InterviewAttemptStage.id).where(
                    InterviewAttemptStage.recording_id == attempt_id,
                    InterviewAttemptStage.evaluation_version_id == evaluation_id,
                    InterviewAttemptStage.stage_name.in_(
                        (
                            "content_evaluation",
                            "evidence_grounding",
                            "follow_up_decision",
                            "coaching_enrichment",
                        )
                    ),
                    InterviewAttemptStage.stage_state.in_(("completed", "reused")),
                )
            )
            if (
                attempt.recording_type != "audio"
                or reason not in AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS
                or transcription is None
                or created_transcript is not None
                or completed_downstream is not None
            ):
                return rejected()

        try:
            async with self._session.begin_nested():
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.active_question_id == question_id,
                        InterviewSession.conversation_state.in_(
                            ("awaiting_next_action", "coaching")
                        ),
                        InterviewSession.state_version == expected_state_version,
                    )
                    .values(
                        active_recording_id=attempt_id,
                        state_version=InterviewSession.state_version + 1,
                        activity_version=InterviewSession.activity_version + 1,
                    )
                    .returning(InterviewSession.state_version)
                )
                state_version = session_change.scalar_one_or_none()
                if state_version is None:
                    raise _StaleFinalisation
                current_evaluation = await self._session.scalar(
                    select(InterviewAttemptEvaluation).where(
                        InterviewAttemptEvaluation.id == evaluation_id,
                        InterviewAttemptEvaluation.recording_id == attempt_id,
                        InterviewAttemptEvaluation.transcript_version_id
                        == attempt.current_transcript_version_id,
                        InterviewAttemptEvaluation.state == attempt.evaluation_state,
                    )
                )
                if current_evaluation is None:
                    raise _StaleFinalisation
                question_change = await self._session.execute(
                    update(SessionQuestion)
                    .where(
                        SessionQuestion.id == question_id,
                        SessionQuestion.session_id == session_id,
                        SessionQuestion.question_state == "asked",
                        SessionQuestion.accepted_recording_id.is_(None),
                        and_(
                            SessionQuestion.last_accepted_generation.is_(None)
                            | (
                                SessionQuestion.last_accepted_generation
                                < SessionQuestion.acceptance_generation
                            )
                        ),
                    )
                    .values(
                        accepted_recording_id=attempt_id,
                        last_accepted_generation=SessionQuestion.acceptance_generation,
                        question_state="answered",
                    )
                )
                attempt_change = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == attempt_id,
                        SessionRecording.session_id == session_id,
                        SessionRecording.question_id == question_id,
                        SessionRecording.current_transcript_version_id
                        == attempt.current_transcript_version_id,
                        SessionRecording.current_evaluation_version_id == evaluation_id,
                        SessionRecording.processing_generation
                        == attempt.processing_generation,
                        SessionRecording.attempt_state == attempt.attempt_state,
                        SessionRecording.evaluation_state == attempt.evaluation_state,
                        SessionRecording.accepted_at.is_(None),
                    )
                    .values(accepted_at=datetime.utcnow())
                )
                if question_change.rowcount != 1 or attempt_change.rowcount != 1:
                    raise _StaleFinalisation
                await self.append_session_events(
                    session_id=session_id,
                    events=(
                        SessionEventInput(
                            event_type="attempt_accepted",
                            actor_type="candidate",
                            state_version=state_version,
                            question_id=question_id,
                            recording_id=attempt_id,
                            payload_json={"state": "accepted"},
                        ),
                    ),
                )
                await self._session.flush()
        except _StaleFinalisation:
            await self._session.refresh(session_row)
            return AcceptanceResult(
                False,
                attempt_id,
                None,
                session_row.state_version,
                session_row.conversation_state,
                evaluation_id,
                reported_evaluation_state,
            )
        return AcceptanceResult(
            True,
            attempt_id,
            state_version,
            state_version,
            session_row.conversation_state,
            evaluation_id,
            evaluation.state,
        )

    async def create_follow_up_question(
        self, *, claim: FollowUpAdmissionClaim
    ) -> FollowUpCreationResult:
        reason_mapping = {
            "clarify_example": ("specificity", "gap_repair"),
            "measurable_result": ("impact", "gap_repair"),
            "personal_action": ("specificity", "gap_repair"),
            "reasoning": ("role_depth", "primary_evidence"),
            "role_depth": ("role_depth", "primary_evidence"),
            "resolve_ambiguity": ("clarity", "gap_repair"),
            "evidence_consistency": (
                "evidence_consistency",
                "primary_evidence",
            ),
        }
        question_text = unicodedata.normalize("NFC", claim.question).strip()
        duplicate_key = (
            unicodedata.normalize("NFKC", claim.duplicate_key).strip().casefold()
        )
        try:
            bounded_json = all(
                len(
                    json.dumps(
                        value,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                )
                <= 16_384
                for value in (claim.context_json, claim.generation_json)
            )
        except (TypeError, ValueError, RecursionError):
            bounded_json = False
        if (
            not question_text
            or len(question_text) > 1_000
            or not duplicate_key
            or len(duplicate_key) > 256
            or reason_mapping.get(claim.reason)
            != (claim.target_dimension, claim.aggregation_role)
            or not isinstance(claim.context_json, dict)
            or not isinstance(claim.generation_json, dict)
            or not bounded_json
        ):
            return FollowUpCreationResult(False, None, None)

        try:
            async with self._session.begin_nested():
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.status == "active",
                        InterviewSession.deletion_state == "not_requested",
                        InterviewSession.state_version == claim.expected_state_version,
                        InterviewSession.conversation_state.in_(
                            ("awaiting_next_action", "coaching", "asking_follow_up")
                        ),
                    )
                    .values(state_version=InterviewSession.state_version)
                )
                if session_change.rowcount != 1:
                    raise _StaleFinalisation
                parent = await self._session.scalar(
                    select(SessionQuestion).where(
                        SessionQuestion.id == claim.parent_question_id,
                        SessionQuestion.session_id == claim.session_id,
                        SessionQuestion.question_state == "answered",
                        SessionQuestion.accepted_recording_id
                        == claim.source_recording_id,
                        SessionQuestion.acceptance_generation
                        == claim.expected_acceptance_generation,
                        SessionQuestion.last_accepted_generation
                        == claim.expected_acceptance_generation,
                    )
                )
                root = await self._session.scalar(
                    select(SessionQuestion).where(
                        SessionQuestion.id == claim.root_question_id,
                        SessionQuestion.session_id == claim.session_id,
                        SessionQuestion.question_kind == "planned",
                        SessionQuestion.question_state != "skipped",
                    )
                )
                attempt = await self._session.scalar(
                    select(SessionRecording).where(
                        SessionRecording.id == claim.source_recording_id,
                        SessionRecording.session_id == claim.session_id,
                        SessionRecording.question_id == claim.parent_question_id,
                        SessionRecording.current_transcript_version_id
                        == claim.source_transcript_version_id,
                        SessionRecording.current_evaluation_version_id.is_not(None),
                        SessionRecording.attempt_state.in_(
                            ("completed", "unavailable")
                        ),
                        SessionRecording.accepted_at.is_not(None),
                    )
                )
                transcript = await self._session.scalar(
                    select(InterviewTranscriptVersion.id).where(
                        InterviewTranscriptVersion.id
                        == claim.source_transcript_version_id,
                        InterviewTranscriptVersion.recording_id
                        == claim.source_recording_id,
                    )
                )
                if (
                    parent is None
                    or root is None
                    or attempt is None
                    or transcript is None
                    or parent.follow_up_depth >= 2
                    or (parent.question_kind == "planned" and parent.id != root.id)
                    or (
                        parent.question_kind == "adaptive_follow_up"
                        and parent.root_question_id != root.id
                    )
                ):
                    raise _StaleFinalisation
                follow_up_count = await self._session.scalar(
                    select(func.count(SessionQuestion.id)).where(
                        SessionQuestion.session_id == claim.session_id,
                        SessionQuestion.root_question_id == root.id,
                        SessionQuestion.question_kind == "adaptive_follow_up",
                    )
                )
                duplicate = await self._session.scalar(
                    select(SessionQuestion.id)
                    .where(
                        SessionQuestion.session_id == claim.session_id,
                        SessionQuestion.question_kind == "adaptive_follow_up",
                        SessionQuestion.follow_up_generation_json[
                            "duplicate_key"
                        ].as_string()
                        == duplicate_key,
                    )
                    .limit(1)
                )
                if (
                    int(follow_up_count or 0)
                    >= settings.HATCH_COACH_MAX_FOLLOWUPS_PER_ROOT
                    or duplicate is not None
                ):
                    raise _StaleFinalisation
                maxima = (
                    await self._session.execute(
                        select(
                            func.max(SessionQuestion.question_num),
                            func.max(SessionQuestion.order_in_session),
                        ).where(SessionQuestion.session_id == claim.session_id)
                    )
                ).one()
                question_id = str(uuid.uuid4())
                generation_json = dict(claim.generation_json)
                generation_json["duplicate_key"] = duplicate_key
                self._session.add(
                    SessionQuestion(
                        id=question_id,
                        session_id=claim.session_id,
                        question_num=int(maxima[0] or 0) + 1,
                        text=question_text,
                        category=parent.category,
                        difficulty=parent.difficulty,
                        order_in_session=int(maxima[1] or 0) + 1,
                        question_kind="adaptive_follow_up",
                        root_question_id=root.id,
                        parent_question_id=parent.id,
                        follow_up_depth=parent.follow_up_depth + 1,
                        follow_up_reason=claim.reason,
                        follow_up_target_dimension=claim.target_dimension,
                        follow_up_aggregation_role=claim.aggregation_role,
                        follow_up_source_recording_id=claim.source_recording_id,
                        follow_up_source_transcript_version_id=(
                            claim.source_transcript_version_id
                        ),
                        follow_up_context_json=dict(claim.context_json),
                        follow_up_generation_json=generation_json,
                        source_deleted=False,
                        question_state="pending",
                    )
                )
                await self._session.flush()
                await self.append_session_events(
                    session_id=claim.session_id,
                    events=(
                        SessionEventInput(
                            event_type="follow_up_created",
                            actor_type="system",
                            state_version=claim.expected_state_version,
                            question_id=question_id,
                            recording_id=claim.source_recording_id,
                            payload_json={"reason": claim.reason},
                        ),
                    ),
                )
                await self._session.flush()
        except _StaleFinalisation:
            return FollowUpCreationResult(False, None, claim.expected_state_version)
        return FollowUpCreationResult(True, question_id, claim.expected_state_version)
