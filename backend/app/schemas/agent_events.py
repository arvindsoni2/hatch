"""Pydantic schemas for agent events."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Event payloads ──────────────────────────────────────────────────────────

class JobDiscoveredPayload(BaseModel):
    job_id: str
    title: str
    company: str | None = None
    rate_text: str | None = None
    source: str


class JobScoredPayload(BaseModel):
    job_id: str
    score: float
    skill_match: float | None = None
    experience_match: float | None = None
    rate_match: float | None = None
    location_match: float | None = None
    reasoning: str | None = None


class JobShortlistedPayload(BaseModel):
    job_id: str
    score: float


class CvTailoredPayload(BaseModel):
    job_id: str
    application_id: str
    cv_path: str | None = None
    cl_path: str | None = None
    ats_score: float | None = None


class ApplicationReadyPayload(BaseModel):
    application_id: str
    job_id: str
    cv_path: str | None = None
    cl_path: str | None = None


class ApplicationApprovedPayload(BaseModel):
    application_id: str


class InterviewScheduledPayload(BaseModel):
    application_id: str
    interview_date: datetime | None = None
    round_type: str | None = None


class PrepReadyPayload(BaseModel):
    application_id: str
    session_id: str
    questions_count: int = 0


class ScoutErrorPayload(BaseModel):
    source: str
    error: str
    retry_count: int = 0


class AgentHeartbeatPayload(BaseModel):
    agent_name: str
    status: str
    timestamp: datetime


# ── CRUD schemas ────────────────────────────────────────────────────────────

class AgentEventCreate(BaseModel):
    event_type: str
    source_agent: str
    payload: dict[str, Any]


class AgentEventRead(BaseModel):
    id: str
    event_type: str
    source_agent: str
    payload: str                  # raw JSON string as stored
    status: str
    created_at: datetime
    processed_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class AgentEventList(BaseModel):
    items: list[AgentEventRead]
    total: int
