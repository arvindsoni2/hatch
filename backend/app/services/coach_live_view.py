"""Authoritative, reconciliation-backed live view for conversational Coach."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.async_job import AsyncJob
from ..models.coach_session import (
    CoachSessionEvidenceRecord,
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from ..schemas.coach_conversation import (
    CandidateSelfAssessment,
    ConversationAnswerReviewRead,
    ConversationAttemptHistoryRead,
    ConversationCoachingReview,
    ConversationDeliveryObservation,
    ConversationDeliveryReview,
    ConversationEvidenceFinding,
    ConversationLiveView,
    ConversationReviewDimension,
    ConversationalRubricDimension,
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
from .coach_conversational_contracts import CONTENT_DIMENSIONS
from .coach_processing_snapshot import (
    exact_processing_snapshot,
    load_owned_processing_evaluation,
)
from .coach_reconciliation import reconcile_conversational_session
from .coach_retention import CoachRetentionService


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
        answer_review = await self._project_answer_review(session, active_attempt)
        attempt_history = await self._project_attempt_history(
            session, active_question
        )
        retryable_audio_cleanup_attempt_id = (
            await CoachRetentionService(
                self.db
            ).find_retryable_cancelled_upload_cleanup_attempt(session.id)
            if session.conversation_state == "asking"
            else None
        )
        projected_commands = await contextual_allowed_commands(
            self.db,
            session,
            retryable_audio_cleanup_attempt_id=retryable_audio_cleanup_attempt_id,
        )
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
                answer_review=answer_review,
                attempt_history=attempt_history,
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
                    retryable_audio_cleanup_attempt_id=(
                        retryable_audio_cleanup_attempt_id
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

    async def _current_terminal_evaluation(
        self, attempt: SessionRecording
    ) -> InterviewAttemptEvaluation | None:
        if (
            attempt.current_evaluation_version_id is None
            or attempt.evaluation_state not in {"completed", "unavailable", "invalid"}
        ):
            return None
        evaluation = await self.db.get(
            InterviewAttemptEvaluation, attempt.current_evaluation_version_id
        )
        if (
            evaluation is None
            or evaluation.recording_id != attempt.id
            or evaluation.state not in {"completed", "unavailable", "invalid"}
            or evaluation.state != attempt.evaluation_state
            or evaluation.transcript_version_id
            != attempt.current_transcript_version_id
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        return evaluation

    @staticmethod
    def _source_disclosure(
        records: list[CoachSessionEvidenceRecord],
    ) -> tuple[str | None, str | None]:
        if not records:
            return None, None
        normalized = {
            "approved": "approved",
            "confirmed": "approved",
            "reviewed_final": "approved",
            "reviewed": "reviewed",
            "candidate_selected_unapproved": "candidate_selected_unapproved",
            "draft": "draft",
        }
        rank = {
            "draft": 0,
            "candidate_selected_unapproved": 1,
            "reviewed": 2,
            "approved": 3,
        }
        approvals = [
            normalized[record.approval_state]
            for record in records
            if record.approval_state in normalized
        ]
        if not approvals:
            return None, None
        approval = min(approvals, key=rank.__getitem__)
        labels = {
            "approved": "Approved source",
            "reviewed": "Reviewed source",
            "candidate_selected_unapproved": "Candidate-selected unapproved source",
            "draft": "Draft source",
        }
        return labels[approval], approval

    async def _project_answer_review(
        self,
        session: InterviewSession,
        attempt: SessionRecording | None,
    ) -> ConversationAnswerReviewRead | None:
        if attempt is None:
            return None
        evaluation = await self._current_terminal_evaluation(attempt)
        if evaluation is None:
            return None
        rubric = evaluation.rubric_json
        if rubric is None:
            return None
        if not isinstance(rubric, Mapping):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        answer_level = rubric.get("answer_level")
        if answer_level != evaluation.answer_level:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if evaluation.state != "completed":
            if answer_level != "not_assessed":
                raise CoachLiveViewError("coach_conversation_invalid_state")
            return ConversationAnswerReviewRead(
                evaluation_id=evaluation.id,
                evaluation_state=evaluation.state,
                answer_level="not_assessed",
                dimensions={},
                delivery=ConversationDeliveryReview(
                    level="not_assessed", observations=[]
                ),
                evidence_consistency="not_assessed",
                evidence_findings=[],
                coaching=None,
                accepted_at=attempt.accepted_at,
            )
        if set(rubric) != {
            "answer_level",
            "dimensions",
            "delivery",
            "evidence_consistency",
        }:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        dimensions_raw = rubric.get("dimensions")
        if not isinstance(dimensions_raw, Mapping) or set(dimensions_raw) != set(
            CONTENT_DIMENSIONS
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        dimensions: dict[str, ConversationReviewDimension] = {}
        try:
            for name in CONTENT_DIMENSIONS:
                dimension = ConversationalRubricDimension.model_validate(
                    dimensions_raw[name]
                )
                dimensions[name] = ConversationReviewDimension(
                    level=dimension.level,
                    evidence=dimension.evidence,
                    rationale=dimension.rationale,
                    improvement=dimension.improvement,
                )
            delivery = ConversationalRubricDimension.model_validate(
                rubric.get("delivery")
            )
        except ValidationError as error:
            raise CoachLiveViewError("coach_conversation_invalid_state") from error
        delivery_observations = [
            ConversationDeliveryObservation(
                severity=observation.severity,
                label=(
                    f"{metric.replace('_', ' ').capitalize()}: "
                    f"{observation.severity.replace('_', ' ')} observation"
                ),
            )
            for metric, observation in delivery.observations.items()
        ]
        grounding = rubric.get("evidence_consistency")
        if not isinstance(grounding, Mapping) or set(grounding) != {
            "level",
            "claims",
        }:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        claims = grounding.get("claims")
        if not isinstance(claims, list) or len(claims) > 30:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        evidence_ids = {
            evidence_id
            for claim in claims
            if isinstance(claim, Mapping)
            for evidence_id in claim.get("evidence_ids", ())
            if isinstance(evidence_id, str)
        }
        records = list(
            (
                await self.db.scalars(
                    select(CoachSessionEvidenceRecord).where(
                        CoachSessionEvidenceRecord.session_id == session.id,
                        CoachSessionEvidenceRecord.evidence_id.in_(evidence_ids),
                    )
                )
            ).all()
        ) if evidence_ids else []
        records_by_id = {record.evidence_id: record for record in records}
        findings: list[ConversationEvidenceFinding] = []
        expected_claim_keys = {
            "claim_id", "claim_text", "transcript_start", "transcript_end",
            "claim_type", "materiality", "centrality", "deduplication_key",
            "status", "evidence_ids", "explanation", "candidate_action",
        }
        try:
            for claim in claims:
                if not isinstance(claim, Mapping) or set(claim) != expected_claim_keys:
                    raise CoachLiveViewError("coach_conversation_invalid_state")
                referenced_ids = claim.get("evidence_ids")
                if (
                    not isinstance(referenced_ids, list)
                    and not isinstance(referenced_ids, tuple)
                ) or any(not isinstance(item, str) for item in referenced_ids):
                    raise CoachLiveViewError("coach_conversation_invalid_state")
                referenced = [records_by_id[item] for item in referenced_ids if item in records_by_id]
                if len(referenced) != len(referenced_ids):
                    raise CoachLiveViewError("coach_conversation_invalid_state")
                source_label, source_approval = self._source_disclosure(referenced)
                findings.append(
                    ConversationEvidenceFinding(
                        claim_id=claim["claim_id"],
                        claim_text=claim["claim_text"],
                        transcript_start=claim["transcript_start"],
                        transcript_end=claim["transcript_end"],
                        status=claim["status"],
                        source_label=source_label,
                        source_approval=source_approval,
                        explanation=claim["explanation"],
                        candidate_action=claim["candidate_action"],
                    )
                )
            coaching = (
                ConversationCoachingReview.model_validate(evaluation.coaching_json)
                if evaluation.coaching_json is not None
                else None
            )
            return ConversationAnswerReviewRead(
                evaluation_id=evaluation.id,
                evaluation_state="completed",
                answer_level=answer_level,
                dimensions=dimensions,
                delivery=ConversationDeliveryReview(
                    level=delivery.level, observations=delivery_observations
                ),
                evidence_consistency=grounding["level"],
                evidence_findings=findings,
                coaching=coaching,
                accepted_at=attempt.accepted_at,
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise CoachLiveViewError("coach_conversation_invalid_state") from error

    async def _project_attempt_history(
        self,
        session: InterviewSession,
        question: SessionQuestion | None,
    ) -> list[ConversationAttemptHistoryRead]:
        if question is None:
            return []
        limit = settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION
        attempts = list(
            (
                await self.db.scalars(
                    select(SessionRecording)
                    .where(
                        SessionRecording.session_id == session.id,
                        SessionRecording.question_id == question.id,
                        SessionRecording.attempt_state.in_(
                            ("completed", "unavailable", "invalid")
                        ),
                    )
                    .order_by(SessionRecording.attempt_number, SessionRecording.id)
                    .limit(limit + 1)
                )
            ).all()
        )
        if len(attempts) > limit:
            raise CoachLiveViewError("coach_conversation_invalid_state")
        history: list[ConversationAttemptHistoryRead] = []
        for attempt in attempts:
            evaluation = await self._current_terminal_evaluation(attempt)
            if evaluation is None:
                raise CoachLiveViewError("coach_conversation_invalid_state")
            history.append(
                ConversationAttemptHistoryRead(
                    attempt_id=attempt.id,
                    attempt_number=attempt.attempt_number,
                    answer_level=evaluation.answer_level or "not_assessed",
                    accepted=attempt.accepted_at is not None,
                    transcript_available=attempt.current_transcript_version_id is not None,
                    audio_state=attempt.audio_retention_state,
                )
            )
        return history

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
        evaluation = await load_owned_processing_evaluation(self.db, attempt)
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
        ):
            raise CoachLiveViewError("coach_conversation_invalid_state")
        if state == "processing_answer" and attempt is not None:
            evaluation = await load_owned_processing_evaluation(self.db, attempt)
            job = await self.db.get(AsyncJob, attempt.async_job_id)
            stages = (
                list(
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
                if evaluation is not None
                else []
            )
            if (
                evaluation is None
                or job is None
                or exact_processing_snapshot(
                    session=session,
                    attempt=attempt,
                    evaluation=evaluation,
                    job=job,
                    stages=stages,
                )
                is None
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
        self_assessment = None
        if attempt.self_assessment_json is not None:
            assessment_json = dict(attempt.self_assessment_json)
            recorded_at_value = assessment_json.get("recorded_at")
            if not isinstance(recorded_at_value, str):
                raise CoachLiveViewError("coach_conversation_invalid_state")
            try:
                assessment_json["recorded_at"] = datetime.fromisoformat(
                    recorded_at_value
                )
            except ValueError as error:
                raise CoachLiveViewError(
                    "coach_conversation_invalid_state"
                ) from error
            self_assessment = CandidateSelfAssessment.model_validate(
                assessment_json
            )
            if (
                self_assessment.recorded_at is None
                or attempt.self_assessment_updated_at
                != self_assessment.recorded_at.replace(tzinfo=None)
            ):
                raise CoachLiveViewError("coach_conversation_invalid_state")
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
            self_assessment=self_assessment,
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
        evaluation = await load_owned_processing_evaluation(self.db, attempt)
        if evaluation is not None:
            stage = await self.db.scalar(
                select(InterviewAttemptStage)
                .where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
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
