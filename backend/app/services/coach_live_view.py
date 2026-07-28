"""Authoritative, reconciliation-backed live view for conversational Coach."""

from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from ..schemas.coach_conversation import (
    ConversationLiveView,
    ConversationalQuestionRead,
    InterviewAttemptRead,
    ProcessingProjection,
    ProgressProjection,
    RecoverableErrorProjection,
    RetentionStatus,
    SilencePolicy,
    TranscriptVersionRead,
    VALID_STATUS_STATE_PAIRS,
)
from .coach_command_projection import contextual_allowed_commands
from .coach_conversational_contracts import ERROR_REGISTRY, LIVE_VIEW_CONTRACT
from .coach_reconciliation import reconcile_conversational_session


class CoachLiveViewError(ValueError):
    """A registry-backed safe failure while reading live state."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_REGISTRY:
            code = "coach_conversation_invalid_state"
        self.code = code
        self.definition = ERROR_REGISTRY[code]
        super().__init__(code)


class CoachLiveViewService:
    """Reconcile, verify, and project one local conversational session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_live_view(
        self, *, user_id: str, session_id: str
    ) -> ConversationLiveView:
        # The local-first application has one established owner identity and no
        # persisted user column. Hide absent, foreign-mode, and deleting rows behind
        # the same safe error boundary.
        session = await self._load_safe_owned_session(user_id, session_id)
        await reconcile_conversational_session(self.db, session.id)
        self.db.expire_all()
        session = await self._load_safe_owned_session(user_id, session_id)

        active_question = await self._question(session, session.active_question_id)
        root_question = await self._question(session, session.active_root_question_id)
        active_attempt = await self._attempt(session)
        await self._verify_invariants(session, active_question, active_attempt)

        questions = list(
            (
                await self.db.scalars(
                    select(SessionQuestion)
                    .where(SessionQuestion.session_id == session.id)
                    .order_by(SessionQuestion.order_in_session, SessionQuestion.id)
                    .limit(37)
                )
            ).all()
        )
        if len(questions) > 36:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        await self._validate_projection_json(session, questions, active_attempt)
        projected_commands = await contextual_allowed_commands(self.db, session)
        try:
            return ConversationLiveView(
                session_id=session.id,
                experience_version="conversational_v1",
                status=session.status,
                conversation_state=session.conversation_state,
                state_version=session.state_version,
                activity_version=session.activity_version,
                retention_version=session.retention_version,
                active_question=self._project_question(active_question),
                root_question=self._project_question(root_question),
                active_attempt=await self._project_attempt(active_attempt),
                processing=await self._project_processing(active_attempt),
                progress=self._project_progress(
                    questions, session.active_root_question_id
                ),
                retention=RetentionStatus(
                    audio_policy=(session.retention_policy_json or {}).get(
                        "audio", "delete_after_processing"
                    ),
                    current_audio_state=(
                        active_attempt.audio_retention_state
                        if active_attempt is not None
                        else None
                    ),
                ),
                allowed_commands=list(projected_commands),
                silence_policy=SilencePolicy(
                    warning_ms=settings.HATCH_COACH_SILENCE_WARNING_MS,
                    finish_prompt_ms=settings.HATCH_COACH_SILENCE_FINISH_PROMPT_MS,
                ),
                recoverable_error=self._project_error(session),
                report_state=session.report_state,
                contract_version=LIVE_VIEW_CONTRACT,
            )
        except ValidationError as error:
            raise CoachLiveViewError("coach_conversation_invalid_state") from error

    @staticmethod
    def _bounded_json(value: object, *, root: type | tuple[type, ...]) -> bool:
        if not isinstance(value, root):
            return False
        items = 0

        def visit(node: object, depth: int) -> bool:
            nonlocal items
            if depth > 8 or items > 512:
                return False
            if node is None or type(node) in {str, int, float, bool}:
                items += 1
                return True
            if isinstance(node, Mapping):
                items += len(node)
                return all(
                    isinstance(key, str) and visit(child, depth + 1)
                    for key, child in node.items()
                )
            if isinstance(node, list):
                items += len(node)
                return all(visit(child, depth + 1) for child in node)
            return False

        if not visit(value, 0):
            return False
        try:
            return (
                len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
                <= 65_536
            )
        except (TypeError, ValueError, RecursionError):
            return False

    async def _validate_projection_json(
        self,
        session: InterviewSession,
        questions: list[SessionQuestion],
        attempt: SessionRecording | None,
    ) -> None:
        mapping_values = (
            session.retention_policy_json,
            session.recoverable_error_context_json,
            *(question.follow_up_context_json for question in questions),
            *(question.follow_up_generation_json for question in questions),
        )
        if any(
            value is not None and not self._bounded_json(value, root=Mapping)
            for value in mapping_values
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if any(
            question.pending_hint_types_json is not None
            and (
                not self._bounded_json(question.pending_hint_types_json, root=list)
                or not all(
                    isinstance(item, str) for item in question.pending_hint_types_json
                )
            )
            for question in questions
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if attempt is None:
            return
        if attempt.self_assessment_json is not None and not self._bounded_json(
            attempt.self_assessment_json, root=Mapping
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if attempt.current_evaluation_version_id is None:
            return
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, attempt.current_evaluation_version_id
        )
        if evaluation is None:
            return
        if any(
            value is not None and not self._bounded_json(value, root=Mapping)
            for value in (
                evaluation.rubric_json,
                evaluation.evidence_findings_json,
                evaluation.coaching_json,
                evaluation.follow_up_proposal_json,
                evaluation.diagnostics_json,
                evaluation.model_route_json,
            )
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        stages = (
            await self.db.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                )
            )
        ).all()
        if any(
            stage.diagnostics_json is not None
            and not self._bounded_json(stage.diagnostics_json, root=Mapping)
            for stage in stages
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")

    async def _load_safe_owned_session(
        self, user_id: str, session_id: str
    ) -> InterviewSession:
        if user_id != "local":
            raise CoachLiveViewError("coach_conversation_invalid_state")
        session = await self.db.scalar(
            select(InterviewSession).where(
                InterviewSession.id == session_id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.deletion_state == "not_requested",
            )
        )
        if session is None:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        return session

    async def _question(
        self, session: InterviewSession, question_id: str | None
    ) -> SessionQuestion | None:
        if question_id is None:
            return None
        return await self.db.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == question_id,
                SessionQuestion.session_id == session.id,
            )
        )

    async def _attempt(self, session: InterviewSession) -> SessionRecording | None:
        if session.active_recording_id is None:
            return None
        return await self.db.scalar(
            select(SessionRecording).where(
                SessionRecording.id == session.active_recording_id,
                SessionRecording.session_id == session.id,
            )
        )

    async def _verify_invariants(
        self,
        session: InterviewSession,
        question: SessionQuestion | None,
        attempt: SessionRecording | None,
    ) -> None:
        pair = (session.conversation_state, session.status)
        if pair not in VALID_STATUS_STATE_PAIRS:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        state = session.conversation_state
        if state == "asking" and (
            question is None
            or question.question_state != "asked"
            or question.accepted_recording_id is not None
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "asking" and question is not None:
            processing_attempt = await self.db.scalar(
                select(SessionRecording.id).where(
                    SessionRecording.session_id == session.id,
                    SessionRecording.question_id == question.id,
                    SessionRecording.attempt_state == "pending_processing",
                )
            )
            if processing_attempt is not None:
                raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "listening" and (
            question is None
            or attempt is None
            or attempt.question_id != question.id
            or attempt.attempt_state not in {"draft", "uploaded"}
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "processing_answer" and (
            question is None
            or attempt is None
            or attempt.question_id != question.id
            or attempt.attempt_state != "pending_processing"
            or attempt.evaluation_state != "pending"
            or attempt.async_job_id is None
            or attempt.current_evaluation_version_id is None
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "awaiting_next_action":
            if (
                question is None
                or attempt is None
                or attempt.question_id != question.id
                or attempt.attempt_state not in {"completed", "unavailable"}
                or attempt.evaluation_state != attempt.attempt_state
                or attempt.current_evaluation_version_id is None
            ):
                raise CoachLiveViewError("coach_conversation_invalid_state")
            evaluation = await self.db.get(
                InterviewAttemptEvaluation, attempt.current_evaluation_version_id
            )
            if (
                evaluation is None
                or evaluation.recording_id != attempt.id
                or evaluation.state != attempt.evaluation_state
            ):
                raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "paused" and session.resume_state not in {
            "asking",
            "listening",
            "awaiting_next_action",
            "coaching",
            "recoverable_error",
        }:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "reporting" and not (
            session.report_state == "building"
            and session.report_build_reason == "initial_completion"
            and session.report_job_id is not None
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "completed" and session.report_state not in {
            "completed",
            "fallback",
            "invalidated",
            "building",
            "failed",
        }:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "recoverable_error" and (
            session.recoverable_error_scope is None
            or session.recoverable_error_code not in ERROR_REGISTRY
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")

    @staticmethod
    def _project_question(
        question: SessionQuestion | None,
    ) -> ConversationalQuestionRead | None:
        if question is None:
            return None
        attempt_limit = settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION
        if (
            len(question.text) > 10_000
            or question.attempts_created_count > attempt_limit
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        return ConversationalQuestionRead(
            id=question.id,
            text=question.text,
            category=question.category,
            difficulty=question.difficulty,
            question_kind=question.question_kind,
            question_state=question.question_state,
            root_question_id=question.root_question_id,
            parent_question_id=question.parent_question_id,
            follow_up_depth=question.follow_up_depth,
            follow_up_reason=question.follow_up_reason,
            attempts_created_count=question.attempts_created_count,
            attempt_limit=attempt_limit,
            attempts_remaining=attempt_limit - question.attempts_created_count,
        )

    async def _project_attempt(
        self, attempt: SessionRecording | None
    ) -> InterviewAttemptRead | None:
        if attempt is None:
            return None
        if (
            attempt.question_id is None
            or attempt.attempt_number is None
            or attempt.attempt_state is None
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        transcript_projection = None
        if attempt.current_transcript_version_id is not None:
            transcript = await self.db.scalar(
                select(InterviewTranscriptVersion).where(
                    InterviewTranscriptVersion.id
                    == attempt.current_transcript_version_id,
                    InterviewTranscriptVersion.recording_id == attempt.id,
                )
            )
            if (
                transcript is None
                or transcript.transcript is None
                or len(transcript.transcript)
                > settings.HATCH_COACH_MAX_TRANSCRIPT_CHARACTERS
            ):
                raise CoachLiveViewError("coach_conversation_invalid_state")
            transcript_projection = TranscriptVersionRead(
                id=transcript.id,
                version_number=transcript.version_number,
                transcript=transcript.transcript,
                source=transcript.source,
                edit_reason=transcript.edit_reason,
                created_by=transcript.created_by,
                processing_generation=transcript.processing_generation,
                created_at=transcript.created_at,
            )
        retry_count = attempt.processing_retry_count
        retry_limit = attempt.processing_retry_limit
        return InterviewAttemptRead(
            id=attempt.id,
            question_id=attempt.question_id,
            recording_type=attempt.recording_type,
            attempt_number=attempt.attempt_number,
            attempt_state=attempt.attempt_state,
            attempt_version=attempt.attempt_version,
            processing_generation=attempt.processing_generation,
            processing_retry_count=retry_count,
            processing_retry_limit=retry_limit,
            processing_retries_remaining=retry_limit - retry_count,
            audio_retention_policy=attempt.audio_retention_policy,
            audio_retention_state=attempt.audio_retention_state,
            transcript_version=transcript_projection,
        )

    async def _project_processing(
        self, attempt: SessionRecording | None
    ) -> ProcessingProjection:
        if attempt is None:
            return ProcessingProjection(
                job_id=None,
                stage=None,
                state="not_started",
                retryable=False,
                retry_count=0,
                retry_limit=0,
                retries_remaining=0,
            )
        stage = None
        if attempt.current_evaluation_version_id is not None:
            stage = await self.db.scalar(
                select(InterviewAttemptStage)
                .where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id
                    == attempt.current_evaluation_version_id,
                )
                .order_by(
                    case(
                        (InterviewAttemptStage.stage_state == "running", 0),
                        (InterviewAttemptStage.stage_state == "pending", 1),
                        else_=2,
                    ),
                    InterviewAttemptStage.started_at.desc(),
                    InterviewAttemptStage.id,
                )
                .limit(1)
            )
        retry_count = attempt.processing_retry_count
        retry_limit = attempt.processing_retry_limit
        if stage is not None:
            state = stage.stage_state
            stage_name = stage.stage_name
            job_id = stage.job_id or attempt.async_job_id
        else:
            state = {
                "pending_processing": "pending",
                "completed": "completed",
                "unavailable": "unavailable",
                "recoverable_error": "failed_retryable",
                "invalid": "failed_terminal",
            }.get(attempt.attempt_state or "", "not_started")
            stage_name = None
            job_id = attempt.async_job_id
        return ProcessingProjection(
            job_id=job_id,
            stage=stage_name,
            state=state,
            retryable=state == "failed_retryable",
            retry_count=retry_count,
            retry_limit=retry_limit,
            retries_remaining=retry_limit - retry_count,
        )

    @staticmethod
    def _project_progress(
        questions: list[SessionQuestion], active_root_question_id: str | None
    ) -> ProgressProjection:
        planned = [q for q in questions if q.question_kind == "planned"]
        follow_ups = [q for q in questions if q.question_kind == "adaptive_follow_up"]
        completed_states = {"answered", "skipped"}
        position = next(
            (
                index
                for index, question in enumerate(planned, start=1)
                if question.id == active_root_question_id
            ),
            None,
        )
        return ProgressProjection(
            planned_questions_total=len(planned),
            planned_questions_completed=sum(
                q.question_state in completed_states for q in planned
            ),
            follow_ups_completed=sum(
                q.question_state in completed_states for q in follow_ups
            ),
            current_planned_position=position,
        )

    @staticmethod
    def _project_error(
        session: InterviewSession,
    ) -> RecoverableErrorProjection | None:
        if session.conversation_state != "recoverable_error":
            return None
        code = session.recoverable_error_code
        scope = session.recoverable_error_scope
        if code not in ERROR_REGISTRY or scope is None:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        return RecoverableErrorProjection(code=code, scope=scope, details={})
