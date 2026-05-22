"""Repository for analytics queries."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application, FollowUp, InterviewRound
from ..models.job import JobPosting
from ..schemas.analytics import (
    AnalyticsDashboard,
    FunnelResponse,
    FunnelStage,
    KanbanStats,
    SourceBreakdown,
    TrendResponse,
    WeeklyTrend,
)

FUNNEL_ORDER = ["discovered", "shortlisted", "applied", "interview", "offered", "accepted"]


class AnalyticsRepository:
    """Read-only analytics queries over application and job data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_funnel(self) -> FunnelResponse:
        """Compute conversion funnel across the standard status stages.

        Returns:
            FunnelResponse with per-stage counts and conversion rates.
        """
        result = await self._session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.is_active == True)
            .group_by(Application.status)
        )
        counts: dict[str, int] = dict(result.all())
        total = sum(counts.values())

        stages: list[FunnelStage] = []
        prev_count: int | None = None
        for status in FUNNEL_ORDER:
            count = counts.get(status, 0)
            rate: float | None = None
            if prev_count is not None and prev_count > 0:
                rate = round((count / prev_count) * 100, 1)
            stages.append(FunnelStage(status=status, count=count, conversion_rate=rate))
            prev_count = count

        return FunnelResponse(stages=stages, total_tracked=total)

    async def get_weekly_trends(self, weeks: int = 12) -> TrendResponse:
        """Compute weekly new-applications and interview-reached counts.

        Args:
            weeks: Number of calendar weeks to look back.

        Returns:
            TrendResponse with a WeeklyTrend entry per week.
        """
        cutoff = datetime.utcnow() - timedelta(weeks=weeks)

        # New applications per ISO week
        app_result = await self._session.execute(
            select(
                func.strftime("%Y-%W", Application.created_at).label("week"),
                func.count(Application.id).label("cnt"),
            )
            .where(Application.created_at >= cutoff)
            .group_by(func.strftime("%Y-%W", Application.created_at))
            .order_by(func.strftime("%Y-%W", Application.created_at))
        )
        app_by_week: dict[str, int] = {row.week: row.cnt for row in app_result}

        # Applications that reached interview, grouped by the week they were applied
        interview_result = await self._session.execute(
            select(
                func.strftime("%Y-%W", Application.applied_date).label("week"),
                func.count(Application.id).label("cnt"),
            )
            .where(
                Application.applied_date >= cutoff,
                Application.status.in_(["interview", "offered", "accepted"]),
            )
            .group_by(func.strftime("%Y-%W", Application.applied_date))
        )
        interview_by_week: dict[str, int] = {row.week: row.cnt for row in interview_result}

        all_weeks = sorted(
            set(list(app_by_week.keys()) + list(interview_by_week.keys()))
        )
        trend_weeks: list[WeeklyTrend] = []
        for week_key in all_weeks:
            # Convert "YYYY-WW" to the ISO date of the Monday of that week
            try:
                year, wk = week_key.split("-")
                monday = datetime.strptime(f"{year}-W{int(wk)}-1", "%Y-W%W-%w")
                week_start = monday.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                week_start = week_key
            trend_weeks.append(
                WeeklyTrend(
                    week_start=week_start,
                    new_applications=app_by_week.get(week_key, 0),
                    reached_interview=interview_by_week.get(week_key, 0),
                )
            )

        return TrendResponse(weeks=trend_weeks)

    async def get_source_breakdown(self) -> list[SourceBreakdown]:
        """Compute per-source total, applied, and interview rate metrics.

        Returns:
            List of SourceBreakdown sorted by total descending.
        """
        # Total applications per source (joined to job_postings)
        result = await self._session.execute(
            select(JobPosting.source, func.count(Application.id).label("total"))
            .join(Application, Application.job_id == JobPosting.id)
            .where(Application.is_active == True)
            .group_by(JobPosting.source)
        )
        source_total: dict[str, int] = {row.source: row.total for row in result}

        # Applied (non-discovered) applications per source
        applied_result = await self._session.execute(
            select(JobPosting.source, func.count(Application.id).label("cnt"))
            .join(Application, Application.job_id == JobPosting.id)
            .where(Application.is_active == True, Application.status != "discovered")
            .group_by(JobPosting.source)
        )
        source_applied: dict[str, int] = {row.source: row.cnt for row in applied_result}

        # Interview-reached applications per source
        interview_result = await self._session.execute(
            select(JobPosting.source, func.count(Application.id).label("cnt"))
            .join(Application, Application.job_id == JobPosting.id)
            .where(
                Application.is_active == True,
                Application.status.in_(["interview", "offered", "accepted"]),
            )
            .group_by(JobPosting.source)
        )
        source_interview: dict[str, int] = {row.source: row.cnt for row in interview_result}

        breakdowns: list[SourceBreakdown] = []
        for source, total in source_total.items():
            applied = source_applied.get(source, 0)
            interview = source_interview.get(source, 0)
            interview_rate = round((interview / max(applied, 1)) * 100, 1)
            breakdowns.append(
                SourceBreakdown(
                    source=source,
                    total=total,
                    applied=applied,
                    interview_rate=interview_rate,
                )
            )

        return sorted(breakdowns, key=lambda x: x.total, reverse=True)

    async def get_avg_days_to_interview(self) -> float | None:
        """Compute average days between applied_date and first interview.

        Returns:
            Average days as a float, or None if no data available.
        """
        result = await self._session.execute(
            select(Application.applied_date, InterviewRound.scheduled_at)
            .join(InterviewRound, Application.id == InterviewRound.application_id)
            .where(
                Application.applied_date.is_not(None),
                InterviewRound.scheduled_at.is_not(None),
                InterviewRound.round_number == 1,
            )
        )
        rows = result.all()
        if not rows:
            return None
        diffs = [
            (r.scheduled_at - r.applied_date).days
            for r in rows
            if r.scheduled_at and r.applied_date and r.scheduled_at > r.applied_date
        ]
        return round(sum(diffs) / len(diffs), 1) if diffs else None

    async def get_kanban_stats(self) -> KanbanStats:
        """Compute summary statistics for the Kanban board header.

        Returns:
            KanbanStats with active, applied, response rate, and overdue counts.
        """
        result = await self._session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.is_active == True)
            .group_by(Application.status)
        )
        counts: dict[str, int] = dict(result.all())

        active_statuses = {"discovered", "shortlisted", "applied", "interview", "offered"}
        active_count = sum(counts.get(s, 0) for s in active_statuses)
        applied_count = (
            counts.get("applied", 0)
            + counts.get("interview", 0)
            + counts.get("offered", 0)
        )
        total_applied = (
            applied_count
            + counts.get("accepted", 0)
            + counts.get("rejected", 0)
            + counts.get("declined", 0)
        )
        interview_plus = (
            counts.get("interview", 0)
            + counts.get("offered", 0)
            + counts.get("accepted", 0)
        )
        response_rate = (interview_plus / max(total_applied, 1)) * 100.0

        overdue_result = await self._session.execute(
            select(func.count(FollowUp.id)).where(
                FollowUp.completed == False,
                FollowUp.due_date < datetime.utcnow(),
            )
        )
        overdue_count = overdue_result.scalar_one() or 0

        return KanbanStats(
            active_count=active_count,
            applied_count=applied_count,
            response_rate=round(response_rate, 1),
            overdue_count=overdue_count,
        )
