"""FastAPI router for /api/analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.analytics_repository import AnalyticsRepository
from ..schemas.analytics import AnalyticsDashboard, FunnelResponse, SourceBreakdown, TrendResponse
from ..services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    """Dependency: returns AnalyticsService with injected session."""
    return AnalyticsService(AnalyticsRepository(db))


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_dashboard(
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsDashboard:
    """Return the full analytics dashboard payload.

    Includes Kanban stats, conversion funnel, weekly trends, source breakdown,
    and average days-to-interview.

    Returns:
        AnalyticsDashboard.
    """
    return await service.get_dashboard()


@router.get("/funnel", response_model=FunnelResponse)
async def get_funnel(
    service: AnalyticsService = Depends(get_analytics_service),
) -> FunnelResponse:
    """Return application conversion funnel data.

    Returns:
        FunnelResponse with per-stage counts and conversion rates.
    """
    return await service._repo.get_funnel()


@router.get("/trends", response_model=TrendResponse)
async def get_trends(
    weeks: int = Query(12, ge=1, le=52),
    service: AnalyticsService = Depends(get_analytics_service),
) -> TrendResponse:
    """Return weekly application trend data.

    Args:
        weeks: Number of weeks to look back (1–52).

    Returns:
        TrendResponse with weekly new applications and interviews reached.
    """
    return await service._repo.get_weekly_trends(weeks)


@router.get("/sources", response_model=list[SourceBreakdown])
async def get_sources(
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[SourceBreakdown]:
    """Return per-source application performance breakdown.

    Returns:
        List of SourceBreakdown sorted by total applications descending.
    """
    return await service._repo.get_source_breakdown()


@router.get("/ab-testing")
async def get_ab_testing(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return A/B testing analytics for CV and cover letter variants.

    Returns response rates grouped by cv_variant and cl_variant.
    Only meaningful with 20+ applications.

    Returns:
        Dict with cv_variant and cl_variant response rates.
    """
    from sqlalchemy import func, select  # noqa: PLC0415
    from ..models.application import Application  # noqa: PLC0415

    result = await db.execute(
        select(
            Application.cv_variant,
            Application.cl_variant,
            func.count(Application.id).label("total"),
            func.sum(
                Application.response_received.cast(
                    __import__("sqlalchemy", fromlist=["Integer"]).Integer
                )
            ).label("responses"),
        )
        .where(Application.is_active.is_(True))
        .group_by(Application.cv_variant, Application.cl_variant)
    )

    rows = result.all()
    total_apps = sum(r.total for r in rows)

    if total_apps < 20:
        return {
            "message": f"Not enough data ({total_apps} applications). Need at least 20 for meaningful A/B analysis.",
            "total_applications": total_apps,
            "by_cv_variant": {},
            "by_cl_variant": {},
        }

    by_cv: dict[str, dict] = {}
    by_cl: dict[str, dict] = {}

    for row in rows:
        responses = row.responses or 0
        rate = round(responses / row.total * 100, 1) if row.total > 0 else 0.0

        cv_key = row.cv_variant or "unset"
        if cv_key not in by_cv:
            by_cv[cv_key] = {"total": 0, "responses": 0}
        by_cv[cv_key]["total"] += row.total
        by_cv[cv_key]["responses"] += responses

        cl_key = row.cl_variant or "unset"
        if cl_key not in by_cl:
            by_cl[cl_key] = {"total": 0, "responses": 0}
        by_cl[cl_key]["total"] += row.total
        by_cl[cl_key]["responses"] += responses

    # Add response rate to each bucket
    for bucket in by_cv.values():
        bucket["response_rate_pct"] = round(bucket["responses"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0
    for bucket in by_cl.values():
        bucket["response_rate_pct"] = round(bucket["responses"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0

    return {
        "total_applications": total_apps,
        "by_cv_variant": by_cv,
        "by_cl_variant": by_cl,
    }
