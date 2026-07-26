"""Atomic persistence primitives for conversational Coach sessions.

Methods in this repository flush but never commit.  Their caller owns the short
transaction so state, receipts, events, and version pointers succeed or roll
back together.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coach_session import (
    ConversationCommandResultRecord,
    InterviewAttemptEvaluation,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from ..schemas.coach_conversation import ConversationCommandRequest


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


_FORBIDDEN_EVENT_CONTENT_KEYS = frozenset(
    {
        "audio",
        "audio_bytes",
        "cv",
        "cv_text",
        "evidence_excerpt",
        "evidence_text",
        "model_response",
        "prompt",
        "transcript",
    }
)


def _validate_event_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.casefold() in _FORBIDDEN_EVENT_CONTENT_KEYS:
                raise ValueError("event payload must not contain candidate content")
            _validate_event_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_event_payload(nested)


class _StaleFinalisation(Exception):
    pass


class ConversationalSessionRepository:
    """SQLite-safe conditional transaction primitives for Coach Phase 1."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

        session_row = await self._session.get(InterviewSession, session_id)
        if session_row is None:
            raise ConversationalRepositoryError("coach_session_not_found")
        if session_row.state_version != request.expected_state_version:
            raise ConversationVersionConflict(
                current_state_version=session_row.state_version,
                current_state=session_row.conversation_state,
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
        duplicate = await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.session_id == session_id,
                SessionRecording.client_attempt_id == client_attempt_id,
            )
        )
        if duplicate is not None:
            if (
                duplicate.question_id != question_id
                or duplicate.recording_type != recording_type
                or duplicate.attempt_kind != attempt_kind
            ):
                raise AttemptReservationConflict("coach_client_attempt_id_conflict")
            return AttemptReservation(duplicate, True, ())

        question = await self._session.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == question_id,
                SessionQuestion.session_id == session_id,
            )
        )
        if question is None:
            raise AttemptReservationConflict("coach_question_not_owned")
        if question.attempts_created_count >= max_attempts:
            raise AttemptLimitExhausted("coach_attempt_limit_exhausted")
        pending_hint_count = question.pending_hint_count
        pending_hint_types = tuple(question.pending_hint_types_json or ())

        session_change = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.status == "active",
                InterviewSession.conversation_state == "asking",
                InterviewSession.active_recording_id.is_(None),
                InterviewSession.state_version == expected_state_version,
                InterviewSession.deletion_state == "not_requested",
            )
            .values(
                conversation_state="listening",
                state_version=InterviewSession.state_version + 1,
                activity_version=InterviewSession.activity_version + 1,
                last_activity_at=datetime.utcnow(),
            )
        )
        if session_change.rowcount != 1:
            current = await self._session.get(InterviewSession, session_id)
            if current is not None and current.state_version != expected_state_version:
                raise ConversationVersionConflict(
                    current_state_version=current.state_version,
                    current_state=current.conversation_state,
                )
            raise AttemptReservationConflict("coach_attempt_already_active")

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
                attempts_created_count=SessionQuestion.attempts_created_count + 1,
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
                InterviewSession.active_recording_id.is_(None),
                InterviewSession.conversation_state == "listening",
            )
            .values(active_recording_id=attempt.id, active_question_id=question_id)
        )
        if active.rowcount != 1:
            raise AttemptReservationConflict("coach_attempt_already_active")
        return AttemptReservation(attempt, False, pending_hint_types)

    async def create_transcript_version(
        self,
        *,
        recording_id: str,
        source: str,
        transcript: str,
        expected_attempt_version: int,
        processing_generation: int,
    ) -> InterviewTranscriptVersion:
        normalised = unicodedata.normalize(
            "NFC", transcript.replace("\r\n", "\n").replace("\r", "\n")
        )
        if not normalised:
            raise ValueError("transcript must not be empty")
        attempt = await self._session.get(SessionRecording, recording_id)
        if (
            attempt is None
            or attempt.attempt_state == "deleted"
            or attempt.attempt_version != expected_attempt_version
        ):
            raise StaleVersion("stale attempt version")
        version_number = 1
        if attempt.current_transcript_version_id is not None:
            current_version = await self._session.scalar(
                select(InterviewTranscriptVersion.version_number).where(
                    InterviewTranscriptVersion.id
                    == attempt.current_transcript_version_id,
                    InterviewTranscriptVersion.recording_id == recording_id,
                )
            )
            if current_version is None:
                raise StaleVersion("current transcript pointer is invalid")
            version_number = current_version + 1
        version_id = str(uuid.uuid4())
        row = InterviewTranscriptVersion(
            id=version_id,
            recording_id=recording_id,
            version_number=version_number,
            transcript=normalised,
            source=source,
            content_hash=hashlib.sha256(normalised.encode("utf-8")).hexdigest(),
            created_by="candidate" if source.startswith("candidate") else "system",
            processing_generation=processing_generation,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
                changed = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.attempt_version == expected_attempt_version,
                        SessionRecording.attempt_state != "deleted",
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
            raise StaleVersion("stale attempt version") from error
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
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
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
        try:
            async with self._session.begin_nested():
                changed = await self._session.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == recording_id,
                        SessionRecording.processing_generation == expected_generation,
                        SessionRecording.attempt_state.in_(
                            ("draft", "uploaded", "recoverable_error")
                        ),
                    )
                    .values(
                        processing_generation=SessionRecording.processing_generation
                        + 1,
                        attempt_state="pending_processing",
                        async_job_id=job_id,
                        processing_started_at=datetime.utcnow(),
                    )
                )
                if changed.rowcount != 1:
                    return None
                attempt = await self._session.get(SessionRecording, recording_id)
                assert attempt is not None
                evaluation = await self._session.scalar(
                    select(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.recording_id == recording_id,
                        InterviewAttemptEvaluation.async_job_id == job_id,
                        InterviewAttemptEvaluation.state == "pending",
                    )
                    .order_by(InterviewAttemptEvaluation.version_number.desc())
                    .limit(1)
                )
                if evaluation is None:
                    raise _StaleFinalisation
                await self._session.flush()
        except _StaleFinalisation as error:
            raise StaleVersion(
                "pending evaluation does not match processing job"
            ) from error
        return AttemptProcessingClaim(
            session_id=attempt.session_id,
            question_id=attempt.question_id or "",
            recording_id=attempt.id,
            transcript_version_id=evaluation.transcript_version_id,
            evaluation_version_id=evaluation.id,
            processing_generation=expected_generation + 1,
            job_id=job_id,
            deadline_at=deadline,
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
        claim = AttemptProcessingClaim(
            session_id=attempt.session_id,
            question_id=attempt.question_id or "",
            recording_id=attempt.id,
            transcript_version_id=evaluation.transcript_version_id,
            evaluation_version_id=evaluation.id,
            processing_generation=processing_generation,
            job_id=attempt.async_job_id,
            deadline_at=datetime.utcnow(),
        )
        return AttemptProcessingSnapshot(claim, attempt.attempt_state, evaluation.state)

    async def finalise_attempt_processing(
        self, *, claim: AttemptProcessingClaim, result: AttemptProcessingResult
    ) -> bool:
        try:
            async with self._session.begin_nested():
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
                        current_transcript_version_id=result.transcript_version_id,
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
                        diagnostics_json=result.diagnostics,
                        completed_at=datetime.utcnow(),
                    )
                )
                if evaluation_change.rowcount != 1:
                    raise _StaleFinalisation
                session_change = await self._session.execute(
                    update(InterviewSession)
                    .where(
                        InterviewSession.id == claim.session_id,
                        InterviewSession.conversation_state == "processing_answer",
                        InterviewSession.active_recording_id == claim.recording_id,
                    )
                    .values(
                        conversation_state="awaiting_next_action",
                        state_version=InterviewSession.state_version + 1,
                        activity_version=InterviewSession.activity_version + 1,
                        last_activity_at=datetime.utcnow(),
                    )
                )
                if session_change.rowcount != 1:
                    raise _StaleFinalisation
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
        attempt = await self._session.scalar(
            select(SessionRecording).where(
                SessionRecording.id == attempt_id,
                SessionRecording.session_id == session_id,
                SessionRecording.question_id == question_id,
                SessionRecording.attempt_state.in_(("completed", "unavailable")),
                SessionRecording.evaluation_state.in_(("completed", "unavailable")),
            )
        )
        if attempt is None:
            return AcceptanceResult(False, attempt_id, None)
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
        if question_change.rowcount != 1:
            return AcceptanceResult(False, attempt_id, None)
        session_change = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.active_question_id == question_id,
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
            raise ConversationVersionConflict(
                current_state_version=expected_state_version,
                current_state=None,
            )
        await self._session.execute(
            update(SessionRecording)
            .where(SessionRecording.id == attempt_id)
            .values(accepted_at=datetime.utcnow())
        )
        await self._session.flush()
        return AcceptanceResult(True, attempt_id, state_version)
