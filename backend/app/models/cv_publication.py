"""Product-owned CV publication journal. Content lives only in the DOCX artifact."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CVPublication(Base):
    __tablename__ = "cv_publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_workflow_runs.id"), index=True
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), index=True
    )
    owner_fence: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="reserved")
    staged_path: Mapped[str] = mapped_column(String(512))
    final_path: Mapped[str] = mapped_column(String(512), unique=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(64))
    byte_count: Mapped[int | None] = mapped_column(Integer)
    section_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    projection_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("generated_documents.id"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
