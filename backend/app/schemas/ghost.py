"""Pydantic schemas for ghost job detection scoring."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class GhostScore(BaseModel):
    """Result of a ghost analysis for a single job."""

    job_id: str
    score: int  # 0-100
    verdict: str  # 'likely_real' | 'uncertain' | 'suspicious' | 'likely_ghost'
    signals: list[tuple[str, Any]]  # [(signal_name, detail_value)]
    analysed_at: datetime


class GhostSignalDetail(BaseModel):
    """Expanded detail for a single ghost signal."""

    signal: str
    weight: int
    description: str
    triggered: bool
    detail: Optional[str] = None  # e.g. 'Posted 67 days ago', 'Reposted 4 times'


class GhostJobRead(BaseModel):
    """Lightweight job record for ghost flagged listing."""

    id: str
    title: str
    company: Optional[str] = None
    source: Optional[str] = None
    ghost_score: Optional[int] = None
    ghost_verdict: Optional[str] = None
    ghost_signals: Optional[list] = None
    posted_at: Optional[datetime] = None
    url: str


class GhostStats(BaseModel):
    """Aggregate ghost detection statistics."""

    likely_real: int = 0
    uncertain: int = 0
    suspicious: int = 0
    likely_ghost: int = 0
    total_analysed: int = 0
    total_pending: int = 0  # jobs not yet analysed


class GhostOverrideRequest(BaseModel):
    """Request body for manual verdict override."""

    override_verdict: str
    # 'likely_real' | 'uncertain' | 'suspicious' | 'likely_ghost'
