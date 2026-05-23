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


@router.get("/ats-correlation")
async def get_ats_correlation(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return ATS score vs response rate correlation data.

    Buckets applications by ATS score range and calculates response rate per bucket.
    Useful for validating whether higher ATS scores lead to more responses.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from ..models.application import Application  # noqa: PLC0415
    from ..models.document import GeneratedDocument  # noqa: PLC0415

    # Get applications with ATS-scored CVs
    result = await db.execute(
        select(
            Application.id,
            Application.response_received,
        ).where(Application.is_active.is_(True))
    )
    apps = {row.id: row.response_received for row in result.all()}

    if not apps:
        return {"buckets": [], "message": "No applications yet"}

    # Get ATS scores for CV documents
    docs_result = await db.execute(
        select(
            GeneratedDocument.application_id,
            GeneratedDocument.ats_score,
        ).where(
            GeneratedDocument.document_type == "cv",
            GeneratedDocument.ats_score.isnot(None),
            GeneratedDocument.application_id.in_(list(apps.keys())),
        )
    )

    # Take the latest CV ATS score per application
    ats_by_app: dict[str, int] = {}
    for row in docs_result.all():
        if row.application_id not in ats_by_app:
            ats_by_app[row.application_id] = row.ats_score

    if len(ats_by_app) < 5:
        return {"buckets": [], "message": f"Not enough data ({len(ats_by_app)} scored CVs). Need at least 5."}

    # Bucket into 0-59, 60-74, 75-84, 85-100
    buckets: dict[str, dict] = {
        "0–59": {"total": 0, "responses": 0, "label": "Low (<60)"},
        "60–74": {"total": 0, "responses": 0, "label": "Fair (60–74)"},
        "75–84": {"total": 0, "responses": 0, "label": "Good (75–84)"},
        "85–100": {"total": 0, "responses": 0, "label": "Excellent (85+)"},
    }

    for app_id, ats_score in ats_by_app.items():
        response = apps.get(app_id, False)
        if ats_score < 60:
            key = "0–59"
        elif ats_score < 75:
            key = "60–74"
        elif ats_score < 85:
            key = "75–84"
        else:
            key = "85–100"
        buckets[key]["total"] += 1
        if response:
            buckets[key]["responses"] += 1

    output = []
    for key, b in buckets.items():
        if b["total"] > 0:
            output.append({
                "range": key,
                "label": b["label"],
                "total": b["total"],
                "responses": b["responses"],
                "response_rate_pct": round(b["responses"] / b["total"] * 100, 1),
            })

    return {"buckets": output, "total_scored": len(ats_by_app)}


@router.get("/skill-frequency")
async def get_skill_frequency(
    limit: int = Query(20, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return most-demanded skills from job postings that were shortlisted.

    Reads keywords from job_scores ATS analysis to find the most common
    skill gaps across jobs that passed the scoring threshold.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from ..models.job_score import JobScore  # noqa: PLC0415
    import json  # noqa: PLC0415

    result = await db.execute(
        select(JobScore.reasoning, JobScore.overall_score)
        .where(JobScore.overall_score.isnot(None))
        .order_by(JobScore.overall_score.desc())
        .limit(200)
    )
    rows = result.all()

    # Also pull from agent_events payload for keyword data
    from ..models.agent_event import AgentEvent  # noqa: PLC0415
    events_result = await db.execute(
        select(AgentEvent.payload)
        .where(AgentEvent.event_type == "job_scored")
        .limit(200)
    )

    skill_counts: dict[str, int] = {}
    for row in events_result.scalars().all():
        if not row:
            continue
        try:
            payload = json.loads(row) if isinstance(row, str) else row
            keywords = payload.get("keyword_matches", []) + payload.get("keyword_misses", [])
            for kw in keywords:
                kw = kw.lower().strip()
                if kw:
                    skill_counts[kw] = skill_counts.get(kw, 0) + 1
        except Exception:
            continue

    if not skill_counts:
        return {"skills": [], "message": "No keyword data yet — run the scorer agent first"}

    sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "skills": [{"skill": k, "count": v} for k, v in sorted_skills],
        "total_jobs_analyzed": len(rows),
    }
