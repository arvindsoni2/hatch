"""SQLAlchemy ORM model for recruiter contacts found via job listings."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class RecruiterContact(Base):
    """Stores recruiter/hiring manager contact details inferred from job listings."""

    __tablename__ = "recruiter_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_postings.id"), nullable=True
    )
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recruiter_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recruiter_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email_guess: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    outreach_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft|sent|opened|replied|not_sent
    outreach_status: Mapped[str] = mapped_column(String(32), default="not_sent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
