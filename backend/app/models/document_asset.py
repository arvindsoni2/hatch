"""SQLAlchemy model for generated document export assets."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class GeneratedDocumentAsset(Base):
    """Tracks derived export assets for generated application documents."""

    __tablename__ = "generated_document_assets"
    __table_args__ = (
        Index("idx_generated_document_assets_application_id", "application_id"),
        Index("idx_generated_document_assets_source_document_id", "source_document_id"),
        Index("idx_generated_document_assets_status", "generation_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generated_documents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    path_or_blob_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    generation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
