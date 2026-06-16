"""Immutable application-time scoring and job feature snapshot."""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class ApplicationScoreSnapshot(Base):
    __tablename__ = "application_score_snapshots"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_application_score_snapshots_application_id"),
        Index("idx_application_score_snapshots_job_id", "job_id"),
        Index("idx_application_score_snapshots_created_at", "created_at"),
        Index("idx_application_score_snapshots_source", "source"),
        Index("idx_application_score_snapshots_role_family", "role_family"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("job_postings.id"), nullable=True)
    base_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    skill_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role_family: Mapped[str | None] = mapped_column(String(256), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    working_pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ir35_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    freshness_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_variant: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cl_variant: Mapped[str | None] = mapped_column(String(8), nullable=True)
    scoring_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scorer_version: Mapped[str] = mapped_column(String(32), nullable=False, default="snapshot-v1")
    snapshot_quality: Mapped[str] = mapped_column(String(16), nullable=False, default="exact")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
