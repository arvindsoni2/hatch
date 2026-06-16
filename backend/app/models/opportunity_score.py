"""Cached deterministic outcome-aware ranking scores."""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_opportunity_scores_job_id"),
        Index("idx_opportunity_scores_score", "opportunity_score"),
        Index("idx_opportunity_scores_calculated_at", "calculated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_postings.id"), nullable=False)
    base_fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    outcome_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_sample_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    signal_contributions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
