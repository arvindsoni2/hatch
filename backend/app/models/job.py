"""SQLAlchemy ORM models for job postings and scrape logs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class JobPosting(Base):
    """Represents a single contract job posting scraped from a job board."""

    __tablename__ = "job_postings"
    __table_args__ = (
        Index("idx_job_postings_ghost_score", "ghost_score"),
        Index("idx_job_postings_ghost_verdict", "ghost_verdict"),
        Index("idx_job_postings_active_scraped", "is_active", "scraped_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str | None] = mapped_column(String(256), nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rate_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rate_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="GBP")
    ir35_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legal_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contract_length: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # v2 classification fields
    employment_type: Mapped[str] = mapped_column(String(32), default="unknown")
    working_pattern: Mapped[str] = mapped_column(String(32), default="unknown")
    rate_type: Mapped[str] = mapped_column(String(16), default="unknown")
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    red_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Ghost job detection fields (Tier 1)
    ghost_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ghost_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 'likely_real' | 'uncertain' | 'suspicious' | 'likely_ghost'
    ghost_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of triggered signal names + details
    ghost_analysed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Duplicate / repost tracking
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Enrichment flag — True when description was too short to score meaningfully
    needs_enrichment: Mapped[bool] = mapped_column(Boolean, default=False)

    # Agentic pipeline fields
    auto_scored: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_tailored: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class ScrapeLog(Base):
    """Records each scrape run for auditing and diagnostics."""

    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
