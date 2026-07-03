"""Smart Job Import request and response contracts."""
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class JobUrlImportPreviewRequest(BaseModel):
    url: HttpUrl


class JobUrlImportDraft(BaseModel):
    source_url: str
    normalized_url: str | None = None
    final_url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    rate_text: str | None = None
    description: str | None = None
    apply_url: str | None = None


class JobUrlImportPreviewResponse(JobUrlImportDraft):
    confidence: Literal["high", "medium", "low"]
    extraction_method: Literal["direct", "firecrawl", "manual_required"]
    warnings: list[str] = Field(default_factory=list)
    duplicate: bool = False
    existing_job_id: str | None = None
    existing_application_id: str | None = None


class JobUrlImportSaveRequest(BaseModel):
    draft: JobUrlImportDraft
    next_action: Literal["save_as_job_only", "save_to_applications", "save_and_tailor"]


class JobUrlImportSaveResponse(BaseModel):
    job_id: str
    application_id: str | None = None
    next_action: Literal["saved", "applications", "tailor", "existing"]
    stage: str | None = None
    warnings: list[str] = Field(default_factory=list)
