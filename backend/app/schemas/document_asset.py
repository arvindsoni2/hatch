"""Pydantic schemas for derived document export assets."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GeneratedDocumentAssetRead(BaseModel):
    id: str
    application_id: str
    package_id: str
    source_document_id: str
    kind: str
    format: str
    generation_status: str
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
