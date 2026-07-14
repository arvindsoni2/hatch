"""Authoritative singleton state for first-run onboarding."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class OnboardingState(Base):
    __tablename__ = "onboarding_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_onboarding_state_singleton"),
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'finalization_pending', 'complete')",
            name="ck_onboarding_state_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    last_completed_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finalization_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalized_profile_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

