"""SQLAlchemy ORM model for per-agent runtime state."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class AgentState(Base):
    """One row per agent — tracks current lifecycle status and config."""

    __tablename__ = "agent_state"

    agent_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="idle")      # idle | running | waiting_approval | error
    current_task: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: what the agent is doing
    config: Mapped[str | None] = mapped_column(Text, nullable=True)        # JSON: agent-specific config
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
