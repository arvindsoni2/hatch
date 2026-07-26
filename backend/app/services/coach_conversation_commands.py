"""Idempotent command orchestration for the conversational Coach foundation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import (
    InterviewAttemptStage,
    InterviewSession,
    SessionQuestion,
    SessionRecording,
)
from ..repositories.conversational_session_repository import (
    AttemptLimitExhausted,
    AttemptProcessingClaim,
    AttemptProcessingResult,
    AttemptReservationConflict,
    CommandIdempotencyConflict,
    ConversationVersionConflict,
    ConversationalRepositoryError,
    ConversationalSessionRepository,
    SessionEventInput,
    canonical_request_hash,
)
from ..schemas.coach_conversation import (
    BeginAnswerPayload,
    CancelAttemptPayload,
    ConversationCommandRequest,
    ConversationCommandResult,
    FinishAnswerPayload,
    KeepSpeakingPayload,
    RequestHintPayload,
    RetryAnswerPayload,
    UpdateRetentionPayload,
)
from .async_job_service import AsyncJobService
from .coach_conversation_state import allowed_commands, require_transition
from .coach_conversational_contracts import (
    CONVERSATION_COMMAND_RESULT_CONTRACT,
    ERROR_REGISTRY,
    RUBRIC_CONTRACT,
)
from .coach_session_plan import SessionPlanError, claim_session_setup

PROCESSING_CONTRACT = "coach_processing_v1"


class ConversationCommandError(ValueError):
    """A stable, frontend-safe command failure."""

    def __init__(
        self,
        code: str,
        *,
        current_state_version: int | None = None,
        current_state: str | None = None,
    ) -> None:
        if code not in ERROR_REGISTRY:
            code = "coach_conversation_invalid_state"
        self.code = code
        self.definition = ERROR_REGISTRY[code]
        self.current_state_version = current_state_version
        self.current_state = current_state
        super().__init__(code)


class DeterministicEvaluationStub:
    """Terminal technical fallback used until the evaluator arrives in PR3."""

    async def evaluate(self, claim: AttemptProcessingClaim) -> AttemptProcessingResult:
        return AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={
                "answer_level": "not_assessed",
                "contract_version": RUBRIC_CONTRACT,
            },
            transcript_version_id=claim.transcript_version_id,
            diagnostics={
                "code": "coach_evaluation_unavailable",
                "execution_mode": "deterministic_stub",
            },
        )


class ConversationCommandService:
    """Execute one validated command in a caller-independent transaction."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        evaluator: DeterministicEvaluationStub | None = None,
        after_commit: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.db = db
        self.repository = ConversationalSessionRepository(db)
        self.evaluator = evaluator or DeterministicEvaluationStub()
        self.after_commit = after_commit
        self._post_commit_job_id: str | None = None

    async def execute(
        self,
        *,
        user_id: str,
        session_id: str,
        request: ConversationCommandRequest,
    ) -> ConversationCommandResult:
        if user_id != "local":
            raise ConversationCommandError("coach_conversation_invalid_state")
        request_hash = canonical_request_hash(request, session_id=session_id)
        self._post_commit_job_id = None
        try:
            claim = await self.repository.claim_conversation_command(
                session_id=session_id,
                request=request,
                request_hash=request_hash,
            )
            if claim.is_duplicate:
                if claim.result_json is None:
                    raise ConversationCommandError("coach_conversation_invalid_state")
                result = ConversationCommandResult.model_validate(claim.result_json)
                await self.db.commit()
                return result

            session = await self.db.get(InterviewSession, session_id)
            if (
                session is None
                or session.experience_version != "conversational_v1"
                or session.deletion_state != "not_requested"
            ):
                raise ConversationCommandError("coach_conversation_invalid_state")
            result = await self._dispatch(session, request)
            completed = await self.repository.complete_conversation_command(
                claim=claim,
                result=result.model_dump(mode="json"),
                result_state=(
                    "accepted_processing"
                    if result.result == "accepted_processing"
                    else "completed"
                ),
            )
            if not completed:
                raise ConversationCommandError("coach_conversation_invalid_state")
            await self.db.commit()
            if self._post_commit_job_id is not None and self.after_commit is not None:
                await self.after_commit(self._post_commit_job_id)
            return result
        except ConversationVersionConflict as error:
            await self.db.rollback()
            raise ConversationCommandError(
                "coach_conversation_version_conflict",
                current_state_version=error.current_state_version,
                current_state=error.current_state,
            ) from error
        except CommandIdempotencyConflict as error:
            await self.db.rollback()
            raise ConversationCommandError(
                "coach_command_idempotency_conflict"
            ) from error
        except (AttemptLimitExhausted, AttemptReservationConflict) as error:
            await self.db.rollback()
            code = str(error)
            if code == "coach_client_attempt_id_conflict":
                code = "coach_attempt_client_id_conflict"
            raise ConversationCommandError(code) from error
        except ConversationCommandError:
            await self.db.rollback()
            raise
        except IntegrityError as error:
            await self.db.rollback()
            duplicate = await self.repository.get_command_result(
                session_id=session_id, command_id=request.command_id
            )
            if duplicate is not None and duplicate.request_hash == request_hash:
                if duplicate.result_json is not None:
                    return ConversationCommandResult.model_validate(
                        duplicate.result_json
                    )
            raise ConversationCommandError(
                "coach_command_idempotency_conflict"
            ) from error
        except (ConversationalRepositoryError, ValueError) as error:
            await self.db.rollback()
            code = str(error)
            raise ConversationCommandError(code) from error

    async def _dispatch(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        if request.command_type == "begin_answer":
            assert isinstance(request.payload, BeginAnswerPayload)
            return await self._begin_answer(session, request, request.payload)
        require_transition(session, request.command_type)
        if request.command_type == "start":
            return await self._start(session, request)
        if request.command_type == "finish_answer":
            assert isinstance(request.payload, FinishAnswerPayload)
            return await self._finish_answer(session, request, request.payload)
        if request.command_type == "keep_speaking":
            assert isinstance(request.payload, KeepSpeakingPayload)
            return await self._keep_speaking(session, request, request.payload)
        if request.command_type == "pause":
            return await self._pause(session, request)
        if request.command_type == "resume":
            return await self._resume(session, request)
        if request.command_type == "cancel_attempt":
            assert isinstance(request.payload, CancelAttemptPayload)
            return await self._cancel_attempt(session, request, request.payload)
        if request.command_type == "retry_answer":
            assert isinstance(request.payload, RetryAnswerPayload)
            return await self._retry_answer(session, request, request.payload)
        if request.command_type in {"retry_setup", "rebuild_plan"}:
            return await self._claim_setup(session, request)
        if request.command_type == "request_hint":
            assert isinstance(request.payload, RequestHintPayload)
            return await self._request_hint(session, request, request.payload)
        if request.command_type == "update_retention":
            assert isinstance(request.payload, UpdateRetentionPayload)
            return await self._update_retention(session, request, request.payload)
        if request.command_type == "skip_question":
            return await self._skip_question(session, request)
        raise ConversationCommandError("coach_conversation_invalid_state")

    async def _change_session_state(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        *,
        values: dict[str, object],
        required_state: str | None = None,
    ) -> int:
        state = required_state or session.conversation_state
        changed = await self.db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session.id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.status == session.status,
                InterviewSession.conversation_state == state,
                InterviewSession.state_version == request.expected_state_version,
                InterviewSession.deletion_state == "not_requested",
            )
            .values(
                **values,
                state_version=InterviewSession.state_version + 1,
                last_activity_at=datetime.utcnow(),
            )
            .returning(InterviewSession.state_version)
        )
        state_version = changed.scalar_one_or_none()
        if state_version is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        await self.db.refresh(session)
        return state_version

    async def _start(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        question = await self.db.scalar(
            select(SessionQuestion)
            .where(
                SessionQuestion.session_id == session.id,
                SessionQuestion.question_state == "pending",
            )
            .order_by(SessionQuestion.order_in_session, SessionQuestion.id)
            .limit(1)
        )
        if question is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        changed = await self.db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session.id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.status == "setup",
                InterviewSession.conversation_state == "ready",
                InterviewSession.state_version == request.expected_state_version,
                InterviewSession.deletion_state == "not_requested",
            )
            .values(
                status="active",
                started_at=func.coalesce(
                    InterviewSession.started_at, datetime.utcnow()
                ),
                active_question_id=question.id,
                active_root_question_id=question.id,
                conversation_state="asking",
                state_version=InterviewSession.state_version + 1,
                last_activity_at=datetime.utcnow(),
            )
            .returning(InterviewSession.state_version)
        )
        state_version = changed.scalar_one_or_none()
        if state_version is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        presented = await self.db.execute(
            update(SessionQuestion)
            .where(
                SessionQuestion.id == question.id,
                SessionQuestion.session_id == session.id,
                SessionQuestion.question_state == "pending",
                SessionQuestion.asked_sequence.is_(None),
            )
            .values(question_state="asked", asked_sequence=1)
        )
        if presented.rowcount != 1:
            raise ConversationCommandError("coach_conversation_invalid_state")
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="session_started",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before="ready",
                    state_after="asking",
                    question_id=question.id,
                    command_id=request.command_id,
                ),
                SessionEventInput(
                    event_type="question_presented",
                    actor_type="system",
                    state_version=state_version,
                    state_before="ready",
                    state_after="asking",
                    question_id=question.id,
                    command_id=request.command_id,
                ),
            ),
        )
        await self.db.refresh(session)
        return self._result(session, request)

    async def _begin_answer(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: BeginAnswerPayload,
    ) -> ConversationCommandResult:
        if session.active_question_id is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        question = await self.db.get(SessionQuestion, session.active_question_id)
        if question is None or question.session_id != session.id:
            raise ConversationCommandError("coach_conversation_invalid_state")
        reservation = await self.repository.reserve_conversational_attempt(
            session_id=session.id,
            question_id=question.id,
            client_attempt_id=payload.client_attempt_id,
            recording_type=payload.recording_type,
            expected_state_version=request.expected_state_version,
            attempt_kind="primary" if question.attempts_created_count == 0 else "retry",
            max_attempts=settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION,
            processing_retry_limit=(
                settings.HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT
            ),
            audio_retention_policy=(session.retention_policy_json or {}).get(
                "audio", "delete_after_processing"
            ),
        )
        await self.db.refresh(session)
        if not reservation.is_duplicate:
            await self.repository.append_session_events(
                session_id=session.id,
                events=(
                    SessionEventInput(
                        event_type="answer_capture_started",
                        actor_type="candidate",
                        state_version=session.state_version,
                        state_before="asking",
                        state_after="listening",
                        question_id=question.id,
                        recording_id=reservation.attempt.id,
                        command_id=request.command_id,
                        payload_json=(
                            {"hint_types": list(reservation.pending_hint_types)}
                            if reservation.pending_hint_types
                            else None
                        ),
                    ),
                ),
            )
        return self._result(
            session,
            request,
            result="duplicate" if reservation.is_duplicate else "completed",
            active_attempt_id=reservation.attempt.id,
        )

    async def _finish_answer(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: FinishAnswerPayload,
    ) -> ConversationCommandResult:
        if payload.transcript is None or payload.upload_id is not None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        attempt = await self.db.get(SessionRecording, payload.attempt_id)
        if (
            attempt is None
            or attempt.session_id != session.id
            or attempt.question_id != session.active_question_id
            or attempt.id != session.active_recording_id
            or attempt.recording_type != "text"
            or attempt.attempt_state != "draft"
        ):
            raise ConversationCommandError("coach_attempt_not_active")
        await self.repository.create_transcript_version(
            recording_id=attempt.id,
            source="candidate_text",
            transcript=payload.transcript,
            expected_attempt_version=attempt.attempt_version,
            processing_generation=attempt.processing_generation + 1,
        )
        job = await AsyncJobService.create(self.db, "coach_attempt_processing")
        deadline = datetime.utcnow() + timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS
        )
        claim = await self.repository.claim_attempt_processing(
            recording_id=attempt.id,
            expected_generation=attempt.processing_generation,
            job_id=job.id,
            deadline=deadline,
            evaluation_contract_version=RUBRIC_CONTRACT,
            processing_contract_version=PROCESSING_CONTRACT,
        )
        if claim is None:
            raise ConversationCommandError("coach_attempt_stale_claim")
        transitioned = await self.db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session.id,
                InterviewSession.conversation_state == "listening",
                InterviewSession.active_recording_id == attempt.id,
                InterviewSession.active_question_id == attempt.question_id,
                InterviewSession.state_version == request.expected_state_version,
            )
            .values(
                conversation_state="processing_answer",
                state_version=InterviewSession.state_version + 1,
                activity_version=InterviewSession.activity_version + 1,
                last_activity_at=datetime.utcnow(),
            )
            .returning(InterviewSession.state_version)
        )
        processing_state_version = transitioned.scalar_one_or_none()
        if processing_state_version is None:
            raise ConversationCommandError("coach_attempt_stale_claim")
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="answer_submitted",
                    actor_type="candidate",
                    state_version=processing_state_version,
                    state_before="listening",
                    state_after="processing_answer",
                    question_id=attempt.question_id,
                    recording_id=attempt.id,
                    command_id=request.command_id,
                ),
                SessionEventInput(
                    event_type="attempt_processing_started",
                    actor_type="system",
                    state_version=processing_state_version,
                    state_before="listening",
                    state_after="processing_answer",
                    question_id=attempt.question_id,
                    recording_id=attempt.id,
                    command_id=request.command_id,
                ),
            ),
        )
        await self._persist_stub_stages(claim)
        stub_result = await self.evaluator.evaluate(claim)
        finalised = await self.repository.finalise_attempt_processing(
            claim=claim, result=stub_result
        )
        if not finalised:
            raise ConversationCommandError("coach_attempt_stale_claim")
        job.status = "done"
        job.result_json = '{"status":"unavailable"}'
        await self.db.refresh(session)
        return self._result(session, request)

    async def _keep_speaking(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: KeepSpeakingPayload,
    ) -> ConversationCommandResult:
        attempt = await self._require_active_attempt(session, payload.attempt_id)
        if attempt.attempt_state not in {"draft", "uploaded"}:
            raise ConversationCommandError("coach_attempt_not_active")
        state_version = await self._change_session_state(
            session, request, values={}, required_state="listening"
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="keep_speaking_selected",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before="listening",
                    state_after="listening",
                    question_id=attempt.question_id,
                    recording_id=attempt.id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _pause(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        prior = session.conversation_state
        if prior is None or (
            prior == "recoverable_error"
            and session.recoverable_error_scope != "attempt_processing"
        ):
            raise ConversationCommandError("coach_conversation_invalid_state")
        state_version = await self._change_session_state(
            session,
            request,
            values={
                "resume_state": prior,
                "conversation_state": "paused",
                "paused_at": datetime.utcnow(),
            },
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="session_paused",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before=prior,
                    state_after="paused",
                    question_id=session.active_question_id,
                    recording_id=session.active_recording_id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _resume(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        resume_state = session.resume_state
        if resume_state not in {
            "asking",
            "listening",
            "awaiting_next_action",
            "coaching",
            "recoverable_error",
        }:
            raise ConversationCommandError("coach_conversation_invalid_state")
        state_version = await self._change_session_state(
            session,
            request,
            values={
                "conversation_state": resume_state,
                "resume_state": None,
                "paused_at": None,
            },
            required_state="paused",
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="session_resumed",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before="paused",
                    state_after=resume_state,
                    question_id=session.active_question_id,
                    recording_id=session.active_recording_id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _cancel_attempt(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: CancelAttemptPayload,
    ) -> ConversationCommandResult:
        attempt = await self._require_active_attempt(session, payload.attempt_id)
        if attempt.attempt_state not in {"draft", "uploaded"}:
            raise ConversationCommandError("coach_attempt_not_active")
        attempt.attempt_state = "cancelled"
        attempt.async_job_id = None
        state_version = await self._change_session_state(
            session,
            request,
            values={"conversation_state": "asking", "active_recording_id": None},
            required_state="listening",
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="answer_capture_cancelled",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before="listening",
                    state_after="asking",
                    question_id=attempt.question_id,
                    recording_id=attempt.id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _retry_answer(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: RetryAnswerPayload,
    ) -> ConversationCommandResult:
        question_id = session.active_question_id
        if question_id is None or (
            payload.question_id is not None and payload.question_id != question_id
        ):
            raise ConversationCommandError("coach_conversation_invalid_state")
        if (
            session.conversation_state == "recoverable_error"
            and session.recoverable_error_scope != "attempt_processing"
        ):
            raise ConversationCommandError("coach_conversation_invalid_state")
        question = await self.db.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == question_id,
                SessionQuestion.session_id == session.id,
            )
        )
        if (
            question is None
            or question.question_state != "asked"
            or question.accepted_recording_id is not None
        ):
            raise ConversationCommandError("coach_conversation_invalid_state")
        attempts = (
            await self.db.scalars(
                select(SessionRecording).where(
                    SessionRecording.session_id == session.id,
                    SessionRecording.question_id == question_id,
                )
            )
        ).all()
        if not attempts or any(
            attempt.attempt_state == "pending_processing"
            or attempt.async_job_id is not None
            for attempt in attempts
        ):
            raise ConversationCommandError("coach_conversation_invalid_state")
        if (
            question.attempts_created_count
            >= settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION
        ):
            raise ConversationCommandError("coach_attempt_limit_exhausted")
        prior = session.conversation_state
        prior_recording_id = session.active_recording_id
        state_version = await self._change_session_state(
            session,
            request,
            values={
                "conversation_state": "asking",
                "active_recording_id": None,
                "recoverable_error_code": None,
                "recoverable_error_scope": None,
                "recoverable_error_context_json": None,
            },
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="attempt_retried",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before=prior,
                    state_after="asking",
                    question_id=question_id,
                    recording_id=prior_recording_id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _claim_setup(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        try:
            claim = await claim_session_setup(
                self.db,
                session_id=session.id,
                rebuild=request.command_type == "rebuild_plan",
            )
        except SessionPlanError as error:
            raise ConversationCommandError(error.code) from error
        await self.db.refresh(session)
        self._post_commit_job_id = claim.job_id
        return self._result(
            session,
            request,
            result="accepted_processing",
            async_job_id=claim.job_id,
        )

    async def _request_hint(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: RequestHintPayload,
    ) -> ConversationCommandResult:
        question_id = session.active_question_id
        if question_id is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        recording_id: str | None = None
        if session.conversation_state == "listening":
            attempt = await self._require_active_attempt(
                session, session.active_recording_id
            )
            if attempt.attempt_state not in {"draft", "uploaded"}:
                raise ConversationCommandError("coach_attempt_not_active")
            attempt.hint_count += 1
            recording_id = attempt.id
        else:
            if session.active_recording_id is not None:
                raise ConversationCommandError("coach_conversation_invalid_state")
            question = await self.db.scalar(
                select(SessionQuestion).where(
                    SessionQuestion.id == question_id,
                    SessionQuestion.session_id == session.id,
                    SessionQuestion.question_state == "asked",
                )
            )
            if question is None:
                raise ConversationCommandError("coach_conversation_invalid_state")
            hint_types = list(question.pending_hint_types_json or ())
            hint_types.append(payload.hint_type)
            question.pending_hint_count += 1
            question.pending_hint_types_json = hint_types
        state_version = await self._change_session_state(session, request, values={})
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="hint_presented",
                    actor_type="system",
                    state_version=state_version,
                    state_before=session.conversation_state,
                    state_after=session.conversation_state,
                    question_id=question_id,
                    recording_id=recording_id,
                    command_id=request.command_id,
                    payload_json={"hint_type": payload.hint_type},
                ),
            ),
        )
        return self._result(session, request)

    async def _update_retention(
        self,
        session: InterviewSession,
        request: ConversationCommandRequest,
        payload: UpdateRetentionPayload,
    ) -> ConversationCommandResult:
        policy = dict(session.retention_policy_json or {})
        policy.update({"audio": payload.audio, "transcript": "retain"})
        state_version = await self._change_session_state(
            session,
            request,
            values={
                "retention_policy_json": policy,
                "retention_version": InterviewSession.retention_version + 1,
                "session_plan_amendment_version": (
                    InterviewSession.session_plan_amendment_version + 1
                ),
            },
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="retention_policy_updated",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before=session.conversation_state,
                    state_after=session.conversation_state,
                    command_id=request.command_id,
                    payload_json={"policy": payload.audio},
                ),
            ),
        )
        return self._result(session, request)

    async def _skip_question(
        self, session: InterviewSession, request: ConversationCommandRequest
    ) -> ConversationCommandResult:
        question_id = session.active_question_id
        if question_id is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        question = await self.db.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == question_id,
                SessionQuestion.session_id == session.id,
                SessionQuestion.question_state == "asked",
                SessionQuestion.accepted_recording_id.is_(None),
            )
        )
        if question is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        next_question = await self.db.scalar(
            select(SessionQuestion)
            .where(
                SessionQuestion.session_id == session.id,
                SessionQuestion.question_state == "pending",
                SessionQuestion.id != question_id,
            )
            .order_by(SessionQuestion.order_in_session, SessionQuestion.id)
            .limit(1)
        )
        if next_question is None:
            raise ConversationCommandError("coach_conversation_invalid_state")
        asked_count = await self.db.scalar(
            select(func.count(SessionQuestion.id)).where(
                SessionQuestion.session_id == session.id,
                SessionQuestion.asked_sequence.is_not(None),
            )
        )
        question.question_state = "skipped"
        question.pending_hint_count = 0
        question.pending_hint_types_json = None
        next_question.question_state = "asked"
        next_question.asked_sequence = int(asked_count or 0) + 1
        state_version = await self._change_session_state(
            session,
            request,
            values={
                "active_question_id": next_question.id,
                "active_root_question_id": next_question.id,
                "active_recording_id": None,
                "conversation_state": "asking",
                "activity_version": InterviewSession.activity_version + 1,
            },
            required_state="asking",
        )
        await self.repository.append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="question_skipped",
                    actor_type="candidate",
                    state_version=state_version,
                    state_before="asking",
                    state_after="asking",
                    question_id=question.id,
                    command_id=request.command_id,
                ),
                SessionEventInput(
                    event_type="question_advanced",
                    actor_type="system",
                    state_version=state_version,
                    state_before="asking",
                    state_after="asking",
                    question_id=next_question.id,
                    command_id=request.command_id,
                ),
                SessionEventInput(
                    event_type="question_presented",
                    actor_type="system",
                    state_version=state_version,
                    state_before="asking",
                    state_after="asking",
                    question_id=next_question.id,
                    command_id=request.command_id,
                ),
            ),
        )
        return self._result(session, request)

    async def _require_active_attempt(
        self, session: InterviewSession, attempt_id: str | None
    ) -> SessionRecording:
        if attempt_id is None or attempt_id != session.active_recording_id:
            raise ConversationCommandError("coach_attempt_not_active")
        attempt = await self.db.scalar(
            select(SessionRecording).where(
                SessionRecording.id == attempt_id,
                SessionRecording.session_id == session.id,
                SessionRecording.question_id == session.active_question_id,
            )
        )
        if attempt is None:
            raise ConversationCommandError("coach_attempt_not_active")
        return attempt

    async def _persist_stub_stages(self, claim: AttemptProcessingClaim) -> None:
        transcript_bound = {
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        }
        for stage_name in (
            "audio_persist",
            "transcription",
            "speech_analysis",
            "content_evaluation",
            "evidence_grounding",
            "follow_up_decision",
            "coaching_enrichment",
        ):
            unavailable = stage_name == "content_evaluation"
            self.db.add(
                InterviewAttemptStage(
                    id=str(uuid.uuid4()),
                    recording_id=claim.recording_id,
                    evaluation_version_id=claim.evaluation_version_id,
                    stage_name=stage_name,
                    stage_state="unavailable" if unavailable else "not_applicable",
                    job_id=claim.job_id,
                    claim_token=claim.claim_token,
                    expected_processing_generation=claim.processing_generation,
                    source_transcript_version_id=(
                        claim.transcript_version_id
                        if stage_name in transcript_bound
                        else None
                    ),
                    job_deadline_at=claim.deadline_at,
                    completed_at=datetime.utcnow(),
                    last_error_code=(
                        "coach_evaluation_unavailable" if unavailable else None
                    ),
                )
            )
        await self.db.flush()

    @staticmethod
    def _result(
        session: InterviewSession,
        request: ConversationCommandRequest,
        *,
        result: str = "completed",
        active_attempt_id: str | None = None,
        async_job_id: str | None = None,
    ) -> ConversationCommandResult:
        return ConversationCommandResult.model_validate(
            {
                "command_id": request.command_id,
                "result": result,
                "session_id": session.id,
                "state": session.conversation_state,
                "state_version": session.state_version,
                "active_question_id": session.active_question_id,
                "active_attempt_id": (
                    active_attempt_id
                    if active_attempt_id is not None
                    else session.active_recording_id
                ),
                "async_job_id": async_job_id,
                "allowed_commands": list(allowed_commands(session)),
                "contract_version": CONVERSATION_COMMAND_RESULT_CONTRACT,
            }
        )
