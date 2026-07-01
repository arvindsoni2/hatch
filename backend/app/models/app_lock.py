"""Single-workspace app-lock configuration and server-side sessions."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class AppLockConfig(Base):
    __tablename__ = "app_lock_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_failed_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AppLockSession(Base):
    __tablename__ = "app_lock_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
