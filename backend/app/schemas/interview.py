"""Pydantic v2 schemas for InterviewRound and FollowUp CRUD."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

VALID_INTERVIEW_TYPES = {
    "phone_screen",
    "technical",
    "behavioural",
    "panel",
    "presentation",
    "culture_fit",
    "final",
    "assessment",
}
VALID_INTERVIEW_STATUSES = {"scheduled", "completed", "cancelled", "rescheduled"}
VALID_FOLLOW_UP_TYPES = {"check_in", "thank_you", "negotiation", "general"}


class InterviewRoundCreate(BaseModel):
    """Schema for creating a new interview round."""

    application_id: str
    round_number: int = 1
    type: str = "phone_screen"
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location: str | None = None
    interviewer_name: str | None = None
    prep_notes: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_INTERVIEW_TYPES:
            raise ValueError(f"type must be one of {VALID_INTERVIEW_TYPES}")
        return v


class InterviewRoundUpdate(BaseModel):
    """Schema for partially updating an interview round."""

    round_number: int | None = None
    type: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location: str | None = None
    interviewer_name: str | None = None
    feedback: str | None = None
    prep_notes: str | None = None
    questions_asked: list[str] | None = None
    status: str | None = None


class InterviewRoundRead(BaseModel):
    """Full interview round response schema."""

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


class FollowUpCreate(BaseModel):
    """Schema for creating a new follow-up task."""

    application_id: str
    due_date: datetime
    type: str = "general"
    note: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_FOLLOW_UP_TYPES:
            raise ValueError(f"type must be one of {VALID_FOLLOW_UP_TYPES}")
        return v


class FollowUpUpdate(BaseModel):
    """Schema for partially updating a follow-up task."""

    due_date: datetime | None = None
    type: str | None = None
    note: str | None = None
    completed: bool | None = None
    completed_at: datetime | None = None


class FollowUpRead(BaseModel):
    """Full follow-up response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    due_date: datetime
    type: str
    note: str | None
    completed: bool
    completed_at: datetime | None
    created_at: datetime
