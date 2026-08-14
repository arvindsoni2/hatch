"""SQLAlchemy ORM models for the Coach module: CompanyResearch, InterviewSession, SessionQuestion, SessionRecording."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _expires_at() -> datetime:
    return datetime.utcnow() + timedelta(days=30)


class CompanyResearch(Base):
    """Cached company research results (30-day TTL)."""

    __tablename__ = "company_research"
    __table_args__ = (
        Index("idx_company_research_name", "company_name"),
        Index("idx_company_research_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_news: Mapped[list | None] = mapped_column(JSON, nullable=True)
    key_products: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tech_stack_signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=_expires_at)


class InterviewSession(Base):
    """A single mock interview practice session."""

    __tablename__ = "interview_sessions"
    __table_args__ = (
        Index("idx_interview_sessions_status", "status"),
        Index("idx_interview_sessions_application_id", "application_id"),
        Index("idx_interview_sessions_created_at", "created_at"),
        CheckConstraint(
            "report_state IN ('not_started', 'building', 'completed', 'fallback', 'failed', 'invalidated')",
            name="ck_interview_sessions_report_state",
        ),
        CheckConstraint(
            "status IN ('setup', 'active', 'completed', 'abandoned', 'failed')",
            name="ck_interview_sessions_status",
        ),
        CheckConstraint(
            "conversation_state IS NULL OR conversation_state IN "
            "('planning', 'ready', 'asking', 'listening', 'processing_answer', "
            "'awaiting_next_action', 'coaching', 'asking_follow_up', 'advancing', "
            "'paused', 'reporting', 'completed', 'recoverable_error', 'abandoned', 'failed')",
            name="ck_interview_sessions_conversation_state",
        ),
        CheckConstraint(
            "recoverable_error_scope IS NULL OR recoverable_error_scope IN "
            "('setup', 'attempt_processing', 'initial_report', 'completed_report_rebuild')",
            name="ck_interview_sessions_recoverable_error_scope",
        ),
        CheckConstraint(
            "deletion_state IN ('not_requested', 'deleting', 'failed')",
            name="ck_interview_sessions_deletion_state",
        ),
        Index(
            "idx_interview_sessions_experience_state", "experience_version", "status"
        ),
        Index("idx_interview_sessions_conversation_state", "conversation_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role_title: Mapped[str] = mapped_column(String(256), nullable=False)
    # config: {question_count, categories, recording_mode, difficulty, interviewer_persona}
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="setup"
    )  # setup|active|completed|abandoned
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Phase C columns
    coach_mode: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # text|voice|video
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    focus_areas: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Coach C1 contract, snapshot, and database-claim fields.
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_started",
        server_default=sql_text("'not_started'"),
    )
    report_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    report_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activity_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    experience_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="legacy_v1",
        server_default=sql_text("'legacy_v1'"),
    )
    conversation_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    resume_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_question_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_recording_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_root_question_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recoverable_error_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    recoverable_error_scope: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    recoverable_error_context_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    setup_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    setup_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    setup_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    setup_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    setup_claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    setup_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    setup_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    setup_max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=sql_text("3")
    )
    retention_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    deletion_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_requested",
        server_default=sql_text("'not_requested'"),
    )
    deletion_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    deletion_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deletion_command_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deletion_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deletion_claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    deletion_started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    deletion_failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deletion_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    planning_request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    session_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    session_plan_contract_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    evaluation_contract_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    report_contract_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    compatibility_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    retention_policy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    session_plan_amendment_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    report_build_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    questions: Mapped[list[SessionQuestion]] = relationship(
        "SessionQuestion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionQuestion.order_in_session",
    )
    recordings: Mapped[list[SessionRecording]] = relationship(
        "SessionRecording", back_populates="session", cascade="all, delete-orphan"
    )
    # Self-referential parent/children for session chains (Phase C)
    children: Mapped[list[InterviewSession]] = relationship(
        "InterviewSession",
        foreign_keys="[InterviewSession.parent_session_id]",
        back_populates="parent",
    )
    parent: Mapped[InterviewSession | None] = relationship(
        "InterviewSession",
        foreign_keys="[InterviewSession.parent_session_id]",
        back_populates="children",
        remote_side="InterviewSession.id",
    )


class SessionQuestion(Base):
    """A single interview question within a session."""

    __tablename__ = "session_questions"
    __table_args__ = (
        Index("idx_session_questions_session_id", "session_id"),
        Index(
            "idx_session_questions_session_asked_sequence",
            "session_id",
            "asked_sequence",
        ),
        Index("idx_session_questions_root_question", "root_question_id"),
        UniqueConstraint(
            "session_id",
            "asked_sequence",
            name="uq_session_questions_session_asked_sequence",
        ),
        CheckConstraint(
            "follow_up_depth >= 0 AND follow_up_depth <= 2",
            name="ck_session_questions_follow_up_depth",
        ),
        CheckConstraint(
            "question_kind IN ('planned', 'adaptive_follow_up')",
            name="ck_session_questions_question_kind",
        ),
        CheckConstraint(
            "question_state IN ('pending', 'asked', 'answered', 'skipped')",
            name="ck_session_questions_question_state",
        ),
        CheckConstraint(
            "follow_up_reason IS NULL OR follow_up_reason IN "
            "('clarify_example', 'measurable_result', 'personal_action', 'reasoning', "
            "'role_depth', 'resolve_ambiguity', 'evidence_consistency')",
            name="ck_session_questions_follow_up_reason",
        ),
        CheckConstraint(
            "attempts_created_count >= 0",
            name="ck_session_questions_attempts_created_count",
        ),
        CheckConstraint(
            "acceptance_generation >= 0",
            name="ck_session_questions_acceptance_generation",
        ),
        CheckConstraint(
            "pending_hint_count >= 0", name="ck_session_questions_pending_hint_count"
        ),
        CheckConstraint(
            "(question_kind = 'planned' AND follow_up_depth = 0) OR "
            "(question_kind = 'adaptive_follow_up' AND root_question_id IS NOT NULL "
            "AND parent_question_id IS NOT NULL AND follow_up_depth BETWEEN 1 AND 2)",
            name="ck_session_questions_kind_depth",
        ),
        CheckConstraint(
            "last_accepted_generation IS NULL OR "
            "last_accepted_generation <= acceptance_generation",
            name="ck_session_questions_accepted_generation_order",
        ),
        CheckConstraint(
            "accepted_recording_id IS NULL OR "
            "last_accepted_generation = acceptance_generation",
            name="ck_session_questions_accepted_generation_current",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_num: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # Technical|Behavioural|Situational|Domain|Culture|Commercial
    difficulty: Mapped[str] = mapped_column(
        String(32), default="medium"
    )  # easy|medium|hard
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_answer_diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    order_in_session: Mapped[int] = mapped_column(Integer, nullable=False)
    question_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planned",
        server_default=sql_text("'planned'"),
    )
    root_question_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_questions.id",
            ondelete="SET NULL",
            name="fk_session_questions_root_question",
        ),
        nullable=True,
    )
    parent_question_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_questions.id",
            ondelete="SET NULL",
            name="fk_session_questions_parent_question",
        ),
        nullable=True,
    )
    follow_up_depth: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    follow_up_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    follow_up_target_dimension: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    follow_up_aggregation_role: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    follow_up_source_recording_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_recordings.id",
            ondelete="SET NULL",
            name="fk_session_questions_follow_up_recording",
            use_alter=True,
        ),
        nullable=True,
    )
    follow_up_source_transcript_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "interview_transcript_versions.id",
            ondelete="SET NULL",
            name="fk_session_questions_follow_up_transcript",
            use_alter=True,
        ),
        nullable=True,
    )
    follow_up_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    follow_up_generation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("0")
    )
    question_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=sql_text("'pending'"),
    )
    accepted_recording_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_recordings.id",
            ondelete="SET NULL",
            name="fk_session_questions_accepted_recording",
            use_alter=True,
        ),
        nullable=True,
    )
    attempts_created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    acceptance_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    last_accepted_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_category_contract_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    pending_hint_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    pending_hint_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    question_contract_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    asked_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="questions"
    )
    recordings: Mapped[list[SessionRecording]] = relationship(
        "SessionRecording",
        foreign_keys="[SessionRecording.question_id]",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class SessionRecording(Base):
    """Recorded answer for a session question, including transcript and evaluation."""

    __tablename__ = "session_recordings"
    __table_args__ = (
        Index("idx_session_recordings_session_id", "session_id"),
        Index("idx_session_recordings_question_id", "question_id"),
        CheckConstraint(
            "evaluation_state IS NULL OR evaluation_state IN "
            "('pending', 'completed', 'unavailable', 'invalid', 'skipped', 'failed')",
            name="ck_session_recordings_evaluation_state",
        ),
        UniqueConstraint(
            "question_id",
            "attempt_number",
            name="uq_session_recordings_question_attempt",
        ),
        UniqueConstraint(
            "session_id",
            "client_attempt_id",
            name="uq_session_recordings_session_client_attempt",
        ),
        Index(
            "idx_session_recordings_question_attempt", "question_id", "attempt_number"
        ),
        Index(
            "idx_session_recordings_async_job_state", "async_job_id", "attempt_state"
        ),
        CheckConstraint(
            "attempt_number IS NULL OR attempt_number > 0",
            name="ck_session_recordings_attempt_number",
        ),
        CheckConstraint(
            "processing_retry_count >= 0",
            name="ck_session_recordings_processing_retry_count",
        ),
        CheckConstraint(
            "processing_retry_limit >= 0",
            name="ck_session_recordings_processing_retry_limit",
        ),
        CheckConstraint("hint_count >= 0", name="ck_session_recordings_hint_count"),
        CheckConstraint(
            "attempt_kind IS NULL OR attempt_kind IN ('primary', 'retry', 'follow_up')",
            name="ck_session_recordings_attempt_kind",
        ),
        CheckConstraint(
            "attempt_state IS NULL OR attempt_state IN "
            "('draft', 'uploaded', 'pending_processing', 'completed', "
            "'recoverable_error', 'unavailable', 'invalid', 'cancelled', "
            "'deleted', 'skipped')",
            name="ck_session_recordings_attempt_state",
        ),
        CheckConstraint(
            "processing_retry_count <= processing_retry_limit",
            name="ck_session_recordings_retry_budget",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("session_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    recording_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # audio|video|text
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # speech_metrics: {filler_count, wpm, hedging_count, duration_ms, pause_count}
    speech_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # video_metrics: {eye_contact_pct, head_stability, expression, gesture_freq}
    video_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluation_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON of AnswerEvaluation
    evaluation_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    async_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_of_recording_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_recordings.id",
            ondelete="SET NULL",
            name="fk_session_recordings_retry_of",
        ),
        nullable=True,
    )
    attempt_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    processing_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    processing_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    processing_retry_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    current_transcript_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "interview_transcript_versions.id",
            ondelete="SET NULL",
            name="fk_session_recordings_current_transcript",
            use_alter=True,
        ),
        nullable=True,
    )
    current_evaluation_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "interview_attempt_evaluations.id",
            ondelete="SET NULL",
            name="fk_session_recordings_current_evaluation",
            use_alter=True,
        ),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    audio_retention_policy: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    audio_retention_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audio_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hint_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    self_assessment_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    self_assessment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="recordings"
    )
    question: Mapped[SessionQuestion | None] = relationship(
        "SessionQuestion", foreign_keys=[question_id], back_populates="recordings"
    )


class ConversationCommandResultRecord(Base):
    """Persisted idempotent result for a conversational command."""

    __tablename__ = "coach_conversation_command_results"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "command_id", name="uq_command_results_session_command"
        ),
        Index("idx_command_results_session_command", "session_id", "command_id"),
        Index("idx_command_results_session_created", "session_id", "created_at"),
        CheckConstraint(
            "result_state IN ('completed', 'accepted_processing', 'duplicate', "
            "'invalid_state', 'version_conflict', 'idempotency_conflict', "
            "'invalid_payload', 'resource_blocked', 'not_found', "
            "'permission_denied', 'stale_claim')",
            name="ck_command_results_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    command_type: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result_state: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InterviewSessionEvent(Base):
    """Content-bounded append-only session event."""

    __tablename__ = "interview_session_events"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "sequence_number", name="uq_session_events_session_sequence"
        ),
        Index("idx_session_events_session_sequence", "session_id", "sequence_number"),
        Index("idx_session_events_session_created", "session_id", "created_at"),
        Index("idx_session_events_session_type", "session_id", "event_type"),
        CheckConstraint(
            "actor_type IN ('candidate', 'system', 'worker', 'reconciler', 'migration')",
            name="ck_session_events_actor_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state_before: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recording_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    command_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class CoachSessionEvidenceRecord(Base):
    """Immutable bounded evidence snapshot selected for one Coach session."""

    __tablename__ = "coach_session_evidence_records"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "evidence_id", name="uq_session_evidence_session_evidence"
        ),
        Index(
            "idx_session_evidence_records_session_evidence", "session_id", "evidence_id"
        ),
        CheckConstraint(
            "approval_state IN ('approved', 'confirmed', 'reviewed_final', 'reviewed', "
            "'candidate_selected_unapproved', 'draft', 'context_only')",
            name="ck_session_evidence_approval_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_text: Mapped[str] = mapped_column(Text, nullable=False)
    approval_state: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class InterviewTranscriptVersion(Base):
    """Immutable transcript version for a conversational attempt."""

    __tablename__ = "interview_transcript_versions"
    __table_args__ = (
        UniqueConstraint(
            "recording_id",
            "version_number",
            name="uq_transcript_versions_recording_version",
        ),
        Index(
            "idx_transcript_versions_recording_version",
            "recording_id",
            "version_number",
        ),
        CheckConstraint(
            "source IN ('transcription', 'candidate_text', 'candidate_edit', "
            "'recovered_transcription')",
            name="ck_transcript_versions_source",
        ),
        CheckConstraint(
            "created_by IN ('system', 'candidate')",
            name="ck_transcript_versions_created_by",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    recording_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("session_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    edit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class InterviewAttemptEvaluation(Base):
    """Versioned evaluation state for a conversational attempt."""

    __tablename__ = "interview_attempt_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "recording_id",
            "version_number",
            name="uq_attempt_evaluations_recording_version",
        ),
        Index(
            "idx_attempt_evaluations_recording_version",
            "recording_id",
            "version_number",
        ),
        CheckConstraint(
            "state IN ('pending', 'completed', 'unavailable', 'invalid', 'failed', "
            "'superseded', 'deleted')",
            name="ck_attempt_evaluations_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    recording_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("session_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    transcript_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("interview_transcript_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    answer_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rubric_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_findings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    coaching_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    follow_up_proposal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_route_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluation_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    follow_up_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    async_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InterviewAttemptStage(Base):
    """Bounded processing-stage state for one evaluation generation."""

    __tablename__ = "interview_attempt_stages"
    __table_args__ = (
        UniqueConstraint(
            "recording_id",
            "evaluation_version_id",
            "stage_name",
            name="uq_attempt_stages_recording_evaluation_stage",
        ),
        Index("idx_attempt_stages_job_state", "job_id", "stage_state"),
        CheckConstraint(
            "stage_name IN ('audio_persist', 'transcription', 'speech_analysis', "
            "'content_evaluation', 'evidence_grounding', 'follow_up_decision', "
            "'coaching_enrichment', 'audio_cleanup')",
            name="ck_attempt_stages_name",
        ),
        CheckConstraint(
            "stage_state IN ('not_started', 'pending', 'running', 'completed', "
            "'reused', 'not_applicable', 'unavailable', 'failed_retryable', "
            "'failed_terminal')",
            name="ck_attempt_stages_state",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND repair_count >= 0",
            name="ck_attempt_stages_counts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    recording_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("session_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_attempt_evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    repair_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_processing_generation: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    source_transcript_version_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    reused_from_stage_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("interview_attempt_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InterviewAttemptUpload(Base):
    """Idempotent audio upload result owned by an attempt."""

    __tablename__ = "interview_attempt_uploads"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "upload_id", name="uq_attempt_uploads_attempt_upload"
        ),
        Index("idx_attempt_uploads_attempt_upload", "attempt_id", "upload_id"),
        CheckConstraint(
            "result_state IN ('pending', 'completed', 'failed', 'deleted')",
            name="ck_attempt_uploads_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("session_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    result_state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoachSessionDeletionResult(Base):
    """Content-free hard-deletion idempotency record independent of a session."""

    __tablename__ = "coach_session_deletion_results"
    __table_args__ = (
        UniqueConstraint(
            "session_key_hash", "command_id", name="uq_deletion_results_session_command"
        ),
        CheckConstraint(
            "result_state IN ('processing', 'failed', 'completed')",
            name="ck_deletion_results_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_state: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
