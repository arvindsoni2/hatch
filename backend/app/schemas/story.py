"""Pydantic schemas for the Interview Story Bank."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────── Request schemas ────────────────────────

class StoryCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    summary: Optional[str] = Field(None, max_length=200)
    situation: Optional[str] = None
    task: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    reflection: Optional[str] = None
    tags: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    metrics: Optional[dict[str, Any]] = None
    archetype_fit: Optional[list[str]] = None
    source_session_id: Optional[str] = None
    source_question_id: Optional[str] = None


class StoryUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    summary: Optional[str] = Field(None, max_length=200)
    situation: Optional[str] = None
    task: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    reflection: Optional[str] = None
    tags: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    metrics: Optional[dict[str, Any]] = None
    archetype_fit: Optional[list[str]] = None


class StoryRateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)


class StoryMatchRequest(BaseModel):
    question: str = Field(..., min_length=5)
    tags: Optional[list[str]] = None


# ──────────────────────── Response schemas ────────────────────────

class StoryRead(BaseModel):
    id: str
    title: str
    slug: str
    summary: Optional[str] = None
    situation: Optional[str] = None
    task: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    reflection: Optional[str] = None
    tags: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    metrics: Optional[dict[str, Any]] = None
    archetype_fit: Optional[list[str]] = None
    strength_score: float
    times_used: int
    times_edited: int
    version: int
    manual_rating: Optional[int] = None
    source_session_id: Optional[str] = None
    source_question_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoryListItem(BaseModel):
    id: str
    title: str
    slug: str
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    archetype_fit: Optional[list[str]] = None
    strength_score: float
    times_used: int
    version: int
    manual_rating: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoryMatchResult(BaseModel):
    story: StoryListItem
    confidence: float = Field(..., ge=0.0, le=1.0)
    match_stage: str  # "tag" | "embedding" | "none"
    match_reason: Optional[str] = None


class StoryMatchResponse(BaseModel):
    matches: list[StoryMatchResult]
    question: str


class PaginatedStories(BaseModel):
    items: list[StoryListItem]
    total: int
    skip: int
    limit: int
