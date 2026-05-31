"""Pydantic schemas for GeneratedDocument (CV / cover letter records)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GeneratedDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    document_type: str
    version: int
    file_path: str | None = None
    file_size_bytes: int | None = None
    ats_score: int | None = None
    ats_details: str | None = None    # JSON string stored in DB Text column
    variant_label: str | None = None
    status: str
    created_at: datetime


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_type: str
    version: int
    ats_score: int | None = None
    variant_label: str | None = None
    status: str
    created_at: datetime


class DocumentStatusUpdate(BaseModel):
    status: str
