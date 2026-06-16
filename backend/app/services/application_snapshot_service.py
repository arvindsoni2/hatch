"""Application-time snapshot creation and historical backfill."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.application_score_snapshot import ApplicationScoreSnapshot
from ..models.job import JobPosting
from ..models.job_score import JobScore
from .outcome_feature_service import freshness, normalise_role_family


async def create_snapshot(db: AsyncSession, application_id: str, *, quality: str = "exact") -> tuple[ApplicationScoreSnapshot, bool]:
    existing = await db.scalar(select(ApplicationScoreSnapshot).where(ApplicationScoreSnapshot.application_id == application_id))
    if existing:
        return existing, False
    row = (await db.execute(
        select(Application, JobPosting, JobScore)
        .outerjoin(JobPosting, Application.job_id == JobPosting.id)
        .outerjoin(JobScore, Application.job_id == JobScore.job_id)
        .where(Application.id == application_id)
    )).one_or_none()
    if row is None:
        raise ValueError(f"Application {application_id} not found")
    app, job, score = row
    age_days, bucket = freshness(job.posted_at, job.scraped_at) if job else (None, "unknown")
    snapshot = ApplicationScoreSnapshot(
        application_id=app.id, job_id=app.job_id,
        base_fit_score=score.overall_score if score else (job.match_score if job else None),
        skill_match=score.skill_match if score else None,
        experience_match=score.experience_match if score else None,
        rate_match=score.rate_match if score else None,
        location_match=score.location_match if score else None,
        source=job.source if job else "unknown",
        role_family=normalise_role_family(job.title if job else None),
        seniority=(job.seniority or "unknown") if job else "unknown",
        working_pattern=(job.working_pattern or "unknown") if job else "unknown",
        employment_type=(job.employment_type or "unknown") if job else "unknown",
        ir35_status=(job.ir35_status or "unknown") if job else "unknown",
        freshness_bucket=bucket, job_age_days=age_days,
        cv_variant=app.cv_variant, cl_variant=app.cl_variant,
        scoring_method=score.scoring_method if score else None,
        snapshot_quality="partial" if not job or not score else quality,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot, True


async def backfill_existing_applications(db: AsyncSession, limit: int | None = None) -> dict[str, int]:
    query = select(Application.id).where(Application.applied_date.is_not(None)).order_by(Application.applied_date)
    if limit is not None:
        query = query.limit(limit)
    ids = list((await db.scalars(query)).all())
    result = {"scanned": len(ids), "snapshots_created": 0, "outcomes_created": 0, "partial_snapshots": 0, "skipped": 0}
    from .outcome_event_service import backfill_application_outcomes
    for app_id in ids:
        snapshot, created = await create_snapshot(db, app_id, quality="backfilled")
        result["snapshots_created"] += int(created)
        result["partial_snapshots"] += int(created and snapshot.snapshot_quality == "partial")
        result["outcomes_created"] += await backfill_application_outcomes(db, app_id)
        result["skipped"] += int(not created)
    return result
