"""Company watchlist ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class CompanyWatchlistItem(Base):
    """A user-approved company/careers source Hatch may scan."""

    __tablename__ = "company_watchlist_items"
    __table_args__ = (
        Index("idx_company_watchlist_status_frequency", "status", "scan_frequency"),
        Index("idx_company_watchlist_last_scanned", "last_scanned_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    company_website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    careers_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    scan_frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    role_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    location_preferences: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    remote_preference: Mapped[str] = mapped_column(String(16), nullable=False, default="any")
    min_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_successful_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    scan_runs: Mapped[list["WatchlistScanRun"]] = relationship(
        "WatchlistScanRun",
        back_populates="watchlist_item",
        cascade="all, delete-orphan",
    )


class WatchlistScanRun(Base):
    """Audit record for one company watchlist scan."""

    __tablename__ = "watchlist_scan_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    watchlist_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("company_watchlist_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="builtin_basic")
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    watchlist_item: Mapped[CompanyWatchlistItem] = relationship(
        "CompanyWatchlistItem",
        back_populates="scan_runs",
    )


class DiscoveredRoleFingerprint(Base):
    """Normalized identity for roles found through watchlist scans."""

    __tablename__ = "discovered_role_fingerprints"
    __table_args__ = (
        Index("idx_role_fingerprint_source_url", "source_url"),
        Index("idx_role_fingerprint_external", "normalized_company", "external_job_id"),
        Index("idx_role_fingerprint_title_location", "normalized_company", "normalized_title", "normalized_location"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    normalized_company: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
