"""Immutable, content-free source reader results for product context bindings."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ContextSourceMetadata(BaseModel):
    """Metadata produced by a product-owned, read-only source reader."""

    model_config = ConfigDict(frozen=True, strict=True)

    source_ref: str
    descriptor: str
    provenance: dict[str, str]
    freshness: AwareDatetime | None
    sensitivity: str
    token_estimate: int = Field(ge=0, le=32768)
    confidence: float | None = Field(default=None, ge=0, le=1)
    content_hash: str


class CoachContextSource(ContextSourceMetadata):
    """A V6 reader result already bound to an owned immutable Coach source."""

    task_attempt_id: str
    attempt_session_id: UUID
    session_id: UUID
    question_id: UUID | None
    question_session_id: UUID | None
    ownership_verified: bool
    source_version: str
    required_source_version: str
    transcript_version: str | None
    required_transcript_version: str | None
