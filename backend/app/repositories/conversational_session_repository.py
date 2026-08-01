"""Atomic persistence primitives for conversational Coach sessions.

Methods in this repository flush but never commit.  Their caller owns the short
transaction so state, receipts, events, and version pointers succeed or roll
back together.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from ..schemas.coach_conversation import ConversationCommandRequest, SAFE_TOKEN_RE
from ..services.coach_conversational_contracts import (
    AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS,
    EVIDENCE_GROUNDING_CONTRACT,
    ERROR_REGISTRY,
    FOLLOW_UP_CONTRACT,
    TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS,
)


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
                            InterviewAttemptStage.job_id == claim.job_id,
                            InterviewAttemptStage.expected_processing_generation
                            == claim.processing_generation,
                        )
                    )
                ).all()
                stage_by_name = {stage.stage_name: stage for stage in stages}
                terminal_states = {
                    "completed",
                    "reused",
                    "not_applicable",
                    "unavailable",
                    "failed_terminal",
                }
                if not stages or any(
                    stage.stage_state not in terminal_states for stage in stages
                ):
                    raise _StaleFinalisation
                if any(stage.job_deadline_at != claim.deadline_at for stage in stages):
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
                    for stage in stages
                ):
                    raise _StaleFinalisation

                transcript = None
                if result.transcript_version_id is not None:
                    transcript = await self._session.scalar(
                        select(InterviewTranscriptVersion).where(
                            InterviewTranscriptVersion.id
                            == result.transcript_version_id,
                            InterviewTranscriptVersion.recording_id
                            == claim.recording_id,
                            InterviewTranscriptVersion.processing_generation
                            == claim.processing_generation,
                        )
                    )
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
                            and fence.source_transcript_version_id is not None
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
                                    fence.source_transcript_version_id is not None
                                    or transcription is None
                                    or transcription.stage_state != "completed"
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
