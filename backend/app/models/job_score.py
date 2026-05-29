"""SQLAlchemy ORM model for LLM-generated job fit scores."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class JobScore(Base):
    """Stores Claude-generated fit scores for a job posting."""

    __tablename__ = "job_scores"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_job_scores_job_id"),
        Index("idx_scores_overall", "overall_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_postings.id"), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)   # 0.0 – 1.0
    skill_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)    # LLM explanation
    scoring_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "local" | "llm"
    keyword_matches: Mapped[list | None] = mapped_column(JSON, nullable=True)
    keyword_misses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
