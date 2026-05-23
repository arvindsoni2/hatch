"""SQLAlchemy model for LLM API cost tracking."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class CostTracking(Base):
    """Immutable record of each LLM API call — model, token counts, estimated cost."""

    __tablename__ = "cost_tracking"
    __table_args__ = (
        Index("idx_cost_agent_date", "agent_name", "created_at"),
        Index("idx_cost_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_events.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
