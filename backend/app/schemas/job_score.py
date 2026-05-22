"""Pydantic schemas for job scores."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobScoreRead(BaseModel):
    id: str
    job_id: str
    overall_score: float
    skill_match: float | None = None
    experience_match: float | None = None
    rate_match: float | None = None
    location_match: float | None = None
    reasoning: str | None = None
    scored_at: datetime

    model_config = {"from_attributes": True}
