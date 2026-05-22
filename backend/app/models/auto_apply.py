"""SQLAlchemy ORM model for auto-apply application attempts."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class ApplicationAttempt(Base):
    """Records a single auto-apply attempt for a job application.

    The lifecycle is: pending → preparing → ready_for_review → approved
    → submitting → submitted (or failed/cancelled/captcha_blocked/manual_required).
    """

    __tablename__ = "application_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), nullable=False)
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    apply_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # pending|preparing|ready_for_review|approved|submitting|submitted
    # failed|cancelled|captcha_blocked|manual_required
    status: Mapped[str] = mapped_column(String(32), default="pending")
    form_data: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON
    custom_questions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    cv_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cl_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshot_before: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshot_after: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
