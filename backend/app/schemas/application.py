"""Pydantic v2 schemas for Application tracking."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

# Re-export KanbanStats from analytics so all modules share a single definition
from .analytics import KanbanStats as KanbanStats  # noqa: F401

VALID_STATUSES = {
    "discovered",
    "shortlisted",
    "applied",
    "interview",
    "offered",
    "accepted",
    "rejected",
    "withdrawn",
    "declined",
    "preparing",
    "ready_to_apply",
    # Hatch v4 two-step states
    "ready",      # tailoring done, awaiting human review
    "approved",   # human approved; package being prepared
    "parked",     # scored below threshold
}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}


class ApplicationCreate(BaseModel):
    """Schema for creating a new application record."""

    job_id: str | None = None
    status: str = "discovered"
    priority: str = "normal"
    notes: str | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_phone: str | None = None
    agency_name: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v


class ApplicationUpdate(BaseModel):
    """Schema for partially updating an application record."""

    status: str | None = None
    priority: str | None = None
    applied_date: datetime | None = None
    cv_version: str | None = None
    cover_letter_version: str | None = None
    notes: str | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_phone: str | None = None
    agency_name: str | None = None
    salary_offered: float | None = None
    rejection_reason: str | None = None


class ApplicationStatusUpdate(BaseModel):
    """Schema for status transitions with optional note."""

    status: str
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v


class InterviewRoundRead(BaseModel):
    """Full interview round schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    round_number: int
    type: str
    scheduled_at: datetime | None
    duration_minutes: int | None
    location: str | None
    interviewer_name: str | None
    feedback: str | None
    prep_notes: str | None
    questions_asked: list[str] | None
    status: str
    created_at: datetime
    updated_at: datetime


class FollowUpRead(BaseModel):
    """Full follow-up schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    due_date: datetime
    type: str
    note: str | None
    completed: bool
    completed_at: datetime | None
    created_at: datetime


class ActivityLogRead(BaseModel):
    """Schema for activity log entries."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: str
    action: str
    old_value: str | None
    new_value: str | None
    detail: str | None
    created_at: datetime


class JobSummary(BaseModel):
    """Lightweight job info embedded in ApplicationRead."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str | None
    location: str | None
    rate_text: str | None
    rate_min: float | None
    rate_max: float | None
    ir35_status: str | None
    source: str
    url: str


class ApplicationListItem(BaseModel):
    """Lightweight schema for Kanban cards — no nested lists."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str | None
    status: str
    priority: str
    applied_date: datetime | None
    recruiter_name: str | None
    agency_name: str | None
    salary_offered: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Joined from job_postings when available:
    job_title: str | None = None
    job_company: str | None = None
    job_location: str | None = None
    job_rate_text: str | None = None
    job_rate_min: float | None = None
    job_source: str | None = None
    job_url: str | None = None
    # Agentic fields
    agent_score: float | None = None      # overall_score from job_scores (0.0–1.0)
    agent_created: bool = False
    approval_status: str | None = None


class ApplicationRead(BaseModel):
    """Full application schema including nested data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str | None
    status: str
    priority: str
    applied_date: datetime | None
    cv_version: str | None
    cover_letter_version: str | None
    notes: str | None
    recruiter_name: str | None
    recruiter_email: str | None
    recruiter_phone: str | None
    agency_name: str | None
    salary_offered: float | None
    rejection_reason: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    interviews: list[InterviewRoundRead] = []
    follow_ups: list[FollowUpRead] = []
    activity: list[ActivityLogRead] = []
    # Agentic pipeline fields
    agent_created: bool = False
    approval_status: str | None = None
    # Embedded job info (populated when job_id is set)
    job: JobSummary | None = None


class ApplicationKanbanResponse(BaseModel):
    """Kanban board response grouped by status."""

    columns: dict[str, list[ApplicationListItem]]
    stats: KanbanStats
