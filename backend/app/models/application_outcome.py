"""Normalised factual application outcome events."""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class ApplicationOutcome(Base):
    __tablename__ = "application_outcomes"
    __table_args__ = (
        UniqueConstraint("application_id", "outcome_type", name="uq_application_outcomes_app_type"),
        Index("idx_application_outcomes_application_id", "application_id"),
        Index("idx_application_outcomes_type", "outcome_type"),
        Index("idx_application_outcomes_occurred_at", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
