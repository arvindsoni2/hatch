"""Persisted explanation for one generated CV/cover-letter set."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TailoringReview(Base):
    __tablename__ = "tailoring_reviews"
    __table_args__ = (
        Index("idx_tailoring_reviews_application_created", "application_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    cv_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("generated_documents.id", ondelete="SET NULL"))
    cl_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("generated_documents.id", ondelete="SET NULL"))
    review_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
