"""SQLAlchemy ORM model for follow-up emails drafted by the AI email generator."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class FollowUpEmail(Base):
    """An AI-drafted email for a follow-up reminder.

    Three types are supported:
    - post_application: 5 business days after applying
    - post_interview_thankyou: within 24h of interview completion
    - warm_reengagement: 14+ days with no response
    - custom: manually triggered

    All emails require human review before sending — never auto-sent.
    """

    __tablename__ = "follow_up_emails"
    __table_args__ = (
        Index("idx_follow_up_emails_application_id", "application_id"),
        Index("idx_follow_up_emails_status", "status"),
        Index("idx_follow_up_emails_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    follow_up_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("follow_ups.id"), nullable=True
    )
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    email_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'post_application' | 'post_interview_thankyou' | 'warm_reengagement' | 'custom'

    recipient_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_plain: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # 'draft' | 'approved' | 'sent' | 'failed' | 'skipped'

    sent_via: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 'smtp' | 'mailto' | 'manual'

    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generation_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded prompt inputs used to generate this email
    user_edits: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded diff of what the user changed before sending

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Relationships (viewonly=True — FollowUpEmail never cascades writes to parents)
    follow_up: Mapped[FollowUp | None] = relationship(  # type: ignore[name-defined]
        "FollowUp",
        foreign_keys=[follow_up_id],
        viewonly=True,
    )
    application: Mapped[Application] = relationship(  # type: ignore[name-defined]
        "Application",
        foreign_keys=[application_id],
        viewonly=True,
    )
