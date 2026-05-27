"""Pydantic v2 request/response schemas for job postings and scrape results."""
from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

import json

from pydantic import BaseModel, ConfigDict, field_validator

T = TypeVar("T")


class JobPostingCreate(BaseModel):
    """Schema for creating a new job posting (used by scrapers)."""

    title: str
    company: str | None = None
    location: str | None = None
    rate_text: str | None = None
    rate_min: float | None = None
    rate_max: float | None = None
    currency: str = "GBP"
    ir35_status: str | None = None
    legal_fields: dict[str, str] = {}
    contract_length: str | None = None
    description: str | None = None
    url: str
    source: str
    posted_at: datetime | None = None
    skills: list[str] | None = None
    employment_type: str = "unknown"
    working_pattern: str = "unknown"
    rate_type: str = "unknown"
    seniority: str | None = None
    match_score: float | None = None
    match_reasons: list[str] | None = None
    red_flags: list[str] | None = None

    @field_validator("ir35_status")
    @classmethod
    def validate_ir35(cls, v: str | None) -> str | None:
        """Ensure ir35_status is one of the allowed values."""
        if v is not None and v not in ("inside", "outside", "unknown"):
            return "unknown"
        return v


class JobPostingRead(BaseModel):
    """Full job posting schema returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str | None = None
    location: str | None = None
    rate_text: str | None = None
    rate_min: float | None = None
    rate_max: float | None = None
    currency: str = "GBP"
    ir35_status: str | None = None
    legal_fields: dict[str, str] | None = None
    contract_length: str | None = None
    description: str | None = None
    url: str
    source: str
    posted_at: datetime | None = None
    scraped_at: datetime
    skills: list[str] | None = None
    employment_type: str = "unknown"
    working_pattern: str = "unknown"
    rate_type: str = "unknown"
    seniority: str | None = None
    match_score: float | None = None
    match_reasons: list[str] | None = None
    red_flags: list[str] | None = None
    is_active: bool
    sync_status: str
    created_at: datetime
    updated_at: datetime
    # Ghost detection fields
    ghost_score: int | None = None
    ghost_verdict: str | None = None
    ghost_signals: list[list] | None = None
    ghost_analysed_at: datetime | None = None
    # Per-dimension scores (joined from job_scores table)
    skill_match: float | None = None
    experience_match: float | None = None
    rate_match: float | None = None
    location_match: float | None = None

    @field_validator("ghost_signals", mode="before")
    @classmethod
    def parse_ghost_signals(cls, v: object) -> list | None:
        """Parse ghost_signals from JSON string if stored as text in SQLite."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v  # type: ignore[return-value]


class JobPostingUpdate(BaseModel):
    """Schema for partial updates to a job posting."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    rate_text: str | None = None
    rate_min: float | None = None
    rate_max: float | None = None
    currency: str | None = None
    ir35_status: str | None = None
    contract_length: str | None = None
    description: str | None = None
    url: str | None = None
    source: str | None = None
    posted_at: datetime | None = None
    skills: list[str] | None = None
    is_active: bool | None = None
    sync_status: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    skip: int
    limit: int


class ScrapeResult(BaseModel):
    """Result from a single scraper run."""

    source: str
    jobs_found: int
    jobs_new: int
    errors: int
    duration_seconds: float


class StatsResponse(BaseModel):
    """Aggregated statistics for the jobs dashboard."""

    total_jobs: int
    by_source: dict[str, int]
    by_ir35: dict[str, int]
    new_today: int
    new_this_week: int
