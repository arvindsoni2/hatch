"""SQLAlchemy ORM model for generated CV and cover letter documents."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class GeneratedDocument(Base):
    """Tracks every AI-generated CV or cover letter version for an application."""

    __tablename__ = "generated_documents"
    __table_args__ = (
        UniqueConstraint("application_id", "document_type", "version", name="uq_doc_app_type_version"),
        Index("idx_generated_docs_application_id", "application_id"),
        Index("idx_generated_docs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'cv' | 'cover_letter'
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cached analysis snapshots (JSON-serialised)
    jd_analysis_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    tailoring_params: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ATS scoring
    ats_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ats_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    # Variant & workflow state
    variant_label: Mapped[str | None] = mapped_column(String(4), nullable=True)  # 'A' | 'B'
    status: Mapped[str] = mapped_column(String(32), default="generated")  # generated|reviewed|approved|sent

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
