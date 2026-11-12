"""ORM models owned by the Coach readiness feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class CoachCompetencyOverride(Base):
    """User-authored rename or hide instruction for a competency."""

    __tablename__ = "coach_competency_overrides"
    __table_args__ = (
        Index("idx_coach_competency_overrides_application_id", "application_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    original: Mapped[str] = mapped_column(String(200), nullable=False)
    replacement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CoachInterviewDebrief(Base):
    """User-authored debrief for one real interview round."""

    __tablename__ = "coach_interview_debriefs"
    __table_args__ = (
        Index(
            "idx_coach_interview_debriefs_status",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    interview_round_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_rounds.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="saved", nullable=False)
    overall: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expectation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    questions_json: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_differently: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposals_json: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CoachPatternDismissal(Base):
    """A dismissed pattern fingerprint; no content is stored."""

    __tablename__ = "coach_pattern_dismissals"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class CoachFocusArea(Base):
    """A candidate-chosen practice goal; at most three are active."""

    __tablename__ = "coach_focus_areas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','achieved','archived')",
            name="ck_coach_focus_areas_status",
        ),
        CheckConstraint(
            "active_slot IS NULL OR active_slot IN (1,2,3)",
            name="ck_coach_focus_areas_slot",
        ),
        CheckConstraint(
            "(status = 'active') = (active_slot IS NOT NULL)",
            name="ck_coach_focus_areas_active_slot",
        ),
        Index(
            "uq_coach_focus_areas_active_slot", "active_slot", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    group_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    criteria_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CoachPracticePlan(Base):
    """A deterministic, time-boxed draft or active practice plan."""

    __tablename__ = "coach_practice_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','completed','superseded','expired','discarded')",
            name="ck_coach_practice_plans_status",
        ),
        CheckConstraint(
            "minutes BETWEEN 10 AND 120",
            name="ck_coach_practice_plans_minutes",
        ),
        Index(
            "uq_coach_practice_plans_one_active",
            "status",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    target_round_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("interview_rounds.id", ondelete="SET NULL"), nullable=True
    )
    items_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
