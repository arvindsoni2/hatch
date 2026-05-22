"""SQLAlchemy ORM models for the Coach module: CompanyResearch, InterviewSession, SessionQuestion, SessionRecording."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role_title: Mapped[str] = mapped_column(String(256), nullable=False)
    # config: {question_count, categories, recording_mode, difficulty, interviewer_persona}
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="setup")  # setup|active|completed|abandoned
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    questions: Mapped[list[SessionQuestion]] = relationship(
        "SessionQuestion", back_populates="session", cascade="all, delete-orphan",
        order_by="SessionQuestion.order_in_session"
    )
    recordings: Mapped[list[SessionRecording]] = relationship(
        "SessionRecording", back_populates="session", cascade="all, delete-orphan"
    )


class SessionQuestion(Base):
    """A single interview question within a session."""

    __tablename__ = "session_questions"
    __table_args__ = (
        Index("idx_session_questions_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_num: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # Technical|Behavioural|Situational|Domain|Culture|Commercial
    difficulty: Mapped[str] = mapped_column(String(32), default="medium")  # easy|medium|hard
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_in_session: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped[InterviewSession] = relationship("InterviewSession", back_populates="questions")
    recordings: Mapped[list[SessionRecording]] = relationship(
        "SessionRecording", back_populates="question", cascade="all, delete-orphan"
    )


class SessionRecording(Base):
    """Recorded answer for a session question, including transcript and evaluation."""

    __tablename__ = "session_recordings"
    __table_args__ = (
        Index("idx_session_recordings_session_id", "session_id"),
        Index("idx_session_recordings_question_id", "question_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_questions.id", ondelete="SET NULL"), nullable=True
    )
    recording_type: Mapped[str] = mapped_column(String(16), nullable=False)  # audio|video|text
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # speech_metrics: {filler_count, wpm, hedging_count, duration_ms, pause_count}
    speech_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # video_metrics: {eye_contact_pct, head_stability, expression, gesture_freq}
    video_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluation_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON of AnswerEvaluation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped[InterviewSession] = relationship("InterviewSession", back_populates="recordings")
    question: Mapped[SessionQuestion | None] = relationship("SessionQuestion", back_populates="recordings")
