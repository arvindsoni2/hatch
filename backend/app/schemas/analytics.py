"""Pydantic v2 schemas for analytics responses."""
from __future__ import annotations

from pydantic import BaseModel


class KanbanStats(BaseModel):
    """Summary statistics for the Kanban board header."""

    active_count: int
    applied_count: int
    response_rate: float  # 0.0 – 100.0
    overdue_count: int


class FunnelStage(BaseModel):
    """A single stage in the application conversion funnel."""

    status: str
    count: int
    conversion_rate: float | None  # % of previous stage


class FunnelResponse(BaseModel):
    """Application conversion funnel from discovery to acceptance."""

    stages: list[FunnelStage]
    total_tracked: int


class WeeklyTrend(BaseModel):
    """Aggregated application activity for a single calendar week."""

    week_start: str  # ISO date string (Monday)
    new_applications: int
    reached_interview: int


class TrendResponse(BaseModel):
    """Weekly application trend data over a date range."""

    weeks: list[WeeklyTrend]


class SourceBreakdown(BaseModel):
    """Performance metrics for a single job-board source."""

    source: str
    total: int
    applied: int
    interview_rate: float  # % that reached interview


class AnalyticsDashboard(BaseModel):
    """Full analytics dashboard payload."""

    stats: KanbanStats
    funnel: FunnelResponse
    trends: TrendResponse
    sources: list[SourceBreakdown]
    avg_days_to_interview: float | None
    avg_days_to_offer: float | None
