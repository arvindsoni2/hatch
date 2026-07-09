"""Question Bank ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class QuestionBankItem(Base):
    """Reusable interview answer, STAR story, proof point, or research note."""

    __tablename__ = "question_bank_items"
    __table_args__ = (
        Index("idx_question_bank_type", "type"),
        Index("idx_question_bank_confidence", "confidence"),
        Index("idx_question_bank_updated_at", "updated_at"),
        Index("idx_question_bank_archived_at", "archived_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    answer_draft: Mapped[str] = mapped_column(Text, nullable=False)
    situation: Mapped[str | None] = mapped_column(Text, nullable=True)
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    linked_applications: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    source_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_question_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
