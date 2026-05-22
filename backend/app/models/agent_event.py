"""SQLAlchemy ORM model for agent events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class AgentEvent(Base):
    """Persisted record of every event emitted by an agent."""

    __tablename__ = "agent_events"
    __table_args__ = (
        Index("idx_events_status", "status", "event_type"),
        Index("idx_events_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_agent: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)           # JSON blob
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending | processing | completed | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
