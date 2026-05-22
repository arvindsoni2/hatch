"""SQLAlchemy ORM models for application tracking: Application, InterviewRound, FollowUp."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Application(Base):
    """Tracks a job application through its lifecycle."""

    __tablename__ = "applications"
    __table_args__ = (
        Index("idx_applications_status", "status"),
        Index("idx_applications_job_id", "job_id"),
        Index("idx_applications_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_postings.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    applied_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cv_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cover_letter_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recruiter_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recruiter_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recruiter_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agency_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    salary_offered: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Agentic pipeline fields
    agent_created: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(16), default="pending")
    # 'pending' | 'approved' | 'rejected'

    # v2 A/B testing fields
    cv_variant: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cl_variant: Mapped[str | None] = mapped_column(String(8), nullable=True)
    response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    response_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    interviews: Mapped[list[InterviewRound]] = relationship(
        "InterviewRound",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    follow_ups: Mapped[list[FollowUp]] = relationship(
        "FollowUp",
        back_populates="application",
        cascade="all, delete-orphan",
    )


class InterviewRound(Base):
    """Represents a single interview round within an application."""

    __tablename__ = "interview_rounds"
    __table_args__ = (
        Index("idx_interview_rounds_app_id", "application_id"),
        Index("idx_interview_rounds_scheduled_at", "scheduled_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="phone_screen")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    interviewer_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    prep_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    questions_asked: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    application: Mapped[Application] = relationship("Application", back_populates="interviews")


class FollowUp(Base):
    """Represents a follow-up task associated with an application."""

    __tablename__ = "follow_ups"
    __table_args__ = (
        Index("idx_follow_ups_app_id", "application_id"),
        Index("idx_follow_ups_due_date", "due_date"),
        Index("idx_follow_ups_completed", "completed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Relationships
    application: Mapped[Application] = relationship("Application", back_populates="follow_ups")
