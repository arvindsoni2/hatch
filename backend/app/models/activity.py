"""ActivityLog ORM model for audit trail of application changes."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ActivityLog(Base):
    """Immutable audit log entry for changes to an application."""

    __tablename__ = "activity_log"
    __table_args__ = (Index("idx_activity_log_app_id", "application_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
