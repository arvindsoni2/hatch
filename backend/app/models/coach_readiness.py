"""ORM models owned by the Coach readiness feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
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
