"""AnalyticsService — computes dashboard metrics and exports."""
from __future__ import annotations

import csv
import io
import logging

from ..repositories.analytics_repository import AnalyticsRepository
from ..schemas.analytics import AnalyticsDashboard, KanbanStats
from ..schemas.application import ApplicationRead

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Computes analytics dashboards and exports application data."""

    def __init__(self, analytics_repo: AnalyticsRepository) -> None:
        self._repo = analytics_repo

    async def get_dashboard(self) -> AnalyticsDashboard:
        """Assemble the full analytics dashboard from multiple repo queries.

        Returns:
            AnalyticsDashboard with stats, funnel, trends, sources, and averages.
        """
        funnel = await self._repo.get_funnel()
        trends = await self._repo.get_weekly_trends()
        sources = await self._repo.get_source_breakdown()
        avg_days = await self._repo.get_avg_days_to_interview()

        # Derive KanbanStats from the funnel data to avoid a separate round-trip
        stage_counts: dict[str, int] = {s.status: s.count for s in funnel.stages}
        active_count = sum(
            stage_counts.get(s, 0)
            for s in {"discovered", "shortlisted", "applied", "interview", "offered"}
        )
        applied_count = sum(
            stage_counts.get(s, 0) for s in {"applied", "interview", "offered", "accepted"}
        )
        interview_plus = sum(
            stage_counts.get(s, 0) for s in {"interview", "offered", "accepted"}
        )
        response_rate = round((interview_plus / max(applied_count, 1)) * 100, 1)
        kanban_stats = KanbanStats(
            active_count=active_count,
            applied_count=applied_count,
            response_rate=response_rate,
            overdue_count=0,  # Requires application repo; set to 0 here
        )

        return AnalyticsDashboard(
            stats=kanban_stats,
            funnel=funnel,
            trends=trends,
            sources=sources,
            avg_days_to_interview=avg_days,
            avg_days_to_offer=None,
        )

    def export_csv(self, applications: list[ApplicationRead]) -> str:
        """Export a list of applications as a CSV-formatted string.

        Args:
            applications: List of ApplicationRead instances to export.

        Returns:
            CSV-formatted string with a header row and one row per application.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Status",
            "Priority",
            "Job ID",
            "Applied Date",
            "Agency",
            "Recruiter",
            "Salary Offered",
            "CV Version",
            "Cover Letter Version",
            "Rejection Reason",
            "Created At",
        ])
        for app in applications:
            writer.writerow([
                app.id,
                app.status,
                app.priority,
                app.job_id or "",
                app.applied_date.isoformat() if app.applied_date else "",
                app.agency_name or "",
                app.recruiter_name or "",
                app.salary_offered or "",
                app.cv_version or "",
                app.cover_letter_version or "",
                app.rejection_reason or "",
                app.created_at.isoformat(),
            ])
        return output.getvalue()

    def export_json(self, applications: list[ApplicationRead]) -> list[dict]:
        """Export a list of applications as a list of serialisable dicts.

        Args:
            applications: List of ApplicationRead instances to export.

        Returns:
            List of dicts suitable for JSON serialisation.
        """
        return [app.model_dump(mode="json") for app in applications]
