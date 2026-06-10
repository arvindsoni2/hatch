"""FastAPI router for job posting endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel
import json as _json

from sqlalchemy import func, select

from ..database import get_db
from ..models.agent_event import AgentEvent
from ..models.cost_tracking import CostTracking
from ..repositories.job_repository import JobRepository
from ..schemas.job import (
    JobPostingRead,
    JobPostingUpdate,
    PaginatedResponse,
    ScrapeResult,
    StatsResponse,
)
from ..services.archive_service import archive_old_jobs, unarchive_job
from ..services.job_service import JobService


class DecisionStep(BaseModel):
    step: int
    agent: str
    event_type: str
    status: str
    timestamp: datetime
    summary: str
    reasoning: str | None = None
    score: float | None = None
    skill_match: float | None = None
    experience_match: float | None = None
    rate_match: float | None = None
    location_match: float | None = None
    model_used: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_estimate: float | None = None
    duration_ms: int | None = None
    ats_score: float | None = None


class DecisionTrail(BaseModel):
    job_id: str
    job_title: str | None
    steps: list[DecisionStep]
    total_cost_usd: float

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
health_router = APIRouter(tags=["health"])


def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    """Dependency factory: create a JobService with a fresh DB session."""
    repo = JobRepository(db)
    return JobService(repo)


# ──────────────────────── Health Check ────────────────────────

@health_router.get("/api/health")
async def health_check() -> dict[str, object]:
    """Simple health check endpoint used by Docker healthcheck.

    Returns JSON with status, timestamp, and optional ram_gb hint for onboarding.
    """
    result: dict[str, object] = {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
    try:
        with open("/proc/meminfo") as _f:
            for _line in _f:
                if _line.startswith("MemTotal:"):
                    result["ram_gb"] = round(int(_line.split()[1]) / 1_048_576)
                    break
    except Exception:
        pass
    return result


# ──────────────────────── Job Endpoints ────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    service: JobService = Depends(get_job_service),
) -> StatsResponse:
    """Return aggregate statistics: totals, by-source breakdown, new today/week.

    Returns:
        StatsResponse with dashboard metrics.
    """
    repo = service._repo
    return await repo.get_stats()


@router.get("/filter-counts", response_model=dict[str, dict[str, int]])
async def get_filter_counts(
    service: JobService = Depends(get_job_service),
) -> dict[str, Any]:
    """Return job counts grouped by filter values for the frontend filter UI.

    Returns:
        Dict with keys 'employment_type', 'working_pattern', 'ir35_status',
        each containing a dict of value → count (e.g. {'contract': 342, ...}).
    """
    return await service._repo.get_filter_counts()


@router.get("", response_model=PaginatedResponse[JobPostingRead])
@router.get("/", response_model=PaginatedResponse[JobPostingRead], include_in_schema=False)
async def list_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    ir35_status: Optional[str] = Query(default=None, description="inside | outside | unknown"),
    source: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    min_rate: Optional[float] = Query(default=None, ge=0),
    max_rate: Optional[float] = Query(default=None, ge=0),
    employment_type: Optional[str] = Query(default=None, description="contract | permanent | fixed_term | part_time | freelance | unknown"),
    working_pattern: Optional[str] = Query(default=None, description="remote | hybrid | onsite | unknown"),
    posted_after: Optional[datetime] = Query(default=None, description="ISO datetime — return only jobs posted after this time"),
    min_match_score: Optional[float] = Query(default=None, ge=0, le=100, description="Minimum AI match score"),
    hide_ghosts: bool = Query(default=True, description="Exclude likely_ghost listings (default True)"),
    service: JobService = Depends(get_job_service),
) -> PaginatedResponse[JobPostingRead]:
    """List active job postings with optional filtering and pagination.

    Args:
        skip: Number of records to skip.
        limit: Max records to return (1-200).
        ir35_status: Filter by IR35 status.
        source: Filter by scraper source.
        search: Full-text search across title, company, description.
        min_rate: Minimum daily rate filter.
        max_rate: Maximum daily rate filter.
        employment_type: Filter by employment type.
        working_pattern: Filter by working pattern.
        posted_after: Only include jobs posted after this datetime.
        min_match_score: Minimum AI match score filter (0-100).

    Returns:
        Paginated list of JobPostingRead objects with total count.
    """
    repo = service._repo
    items, total = await repo.list_with_filters(
        skip=skip,
        limit=limit,
        ir35_status=ir35_status,
        source=source,
        search=search,
        min_rate=min_rate,
        max_rate=max_rate,
        employment_type=employment_type,
        working_pattern=working_pattern,
        posted_after=posted_after,
        min_match_score=min_match_score,
        hide_ghosts=hide_ghosts,
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{job_id}", response_model=JobPostingRead)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobPostingRead:
    """Retrieve a single job posting by ID.

    Args:
        job_id: UUID string for the job posting.

    Returns:
        JobPostingRead if found.

    Raises:
        HTTPException 404: If job not found or soft-deleted.
    """
    job = await service._repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@router.post("/scrape", response_model=list[ScrapeResult])
async def trigger_all_scrapers(
    background_tasks: BackgroundTasks,
    source: Optional[str] = Query(default=None, description="Specific scraper to run"),
    service: JobService = Depends(get_job_service),
) -> list[ScrapeResult]:
    """Trigger scraper(s) to run immediately.

    If 'source' query param is provided, runs only that scraper.
    Otherwise runs all registered scrapers.

    Note: Scrapers run synchronously in this request for simplicity.
    For long-running production use, consider offloading to a background task.

    Args:
        source: Optional scraper name to run a single scraper.

    Returns:
        List of ScrapeResult, one per scraper that ran.
    """
    if source:
        result = await service.run_scraper(source)
        return [result]
    return await service.run_all_scrapers()


@router.post("/scrape/{source}", response_model=ScrapeResult)
async def trigger_single_scraper(
    source: str,
    service: JobService = Depends(get_job_service),
) -> ScrapeResult:
    """Trigger a specific scraper by name.

    Args:
        source: Scraper source name (e.g. 'reed', 'contractoruk').

    Returns:
        ScrapeResult from the run.

    Raises:
        HTTPException 400: If the source name is not recognised.
    """
    try:
        return await service.run_scraper(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{job_id}", response_model=JobPostingRead)
async def update_job(
    job_id: str,
    data: JobPostingUpdate,
    service: JobService = Depends(get_job_service),
) -> JobPostingRead:
    """Partially update a job posting.

    Args:
        job_id: UUID of the job to update.
        data: Fields to update (all optional).

    Returns:
        Updated JobPostingRead.

    Raises:
        HTTPException 404: If job not found.
    """
    updated = await service._repo.update(job_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return updated


@router.delete("/{job_id}", status_code=200)
async def delete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> dict[str, str]:
    """Soft-delete a job posting (sets is_active=False).

    Args:
        job_id: UUID of the job to delete.

    Raises:
        HTTPException 404: If job not found.
    """
    deleted = await service._repo.soft_delete(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"status": "deleted", "id": job_id}


# ──────────────────────── Rescore Unscored ───────────────────────────────────

@router.post("/rescore-unscored", response_model=dict[str, int])
async def rescore_unscored(
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Re-emit job_discovered events for any active jobs that have no match score.

    Legacy jobs stored before the scoring pipeline was set up never received a
    job_discovered event, so the scorer never processed them. This endpoint
    re-queues them so the next scorer run will pick them up.
    Returns {queued: N}.
    """
    from ..agents.tools.event_bus import EventBus  # noqa: PLC0415
    bus = EventBus.instance()
    repo = JobRepository(db)
    unscored = await repo.get_unclassified(limit=200)
    queued = 0
    for job in unscored:
        await bus.emit(
            "job_discovered",
            {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "rate_text": job.rate_text,
                "source": getattr(job, "source", "unknown"),
            },
            db,
        )
        queued += 1
    return {"queued": queued}


# ──────────────────────── Archive Endpoints ────────────────────────

@router.post("/archive/run", response_model=dict[str, int])
async def run_archive(
    days: Optional[int] = Query(default=None, ge=1, description="Override archive_after_days from profile"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Archive active jobs older than the configured threshold.

    Uses profile.preferences.archive_after_days unless overridden with ?days=N.
    Returns {archived: N}.
    """
    if days is None:
        try:
            from ..agents.tools.profile_loader import load_profile
            days = load_profile().preferences.archive_after_days
        except Exception:
            days = 30

    count = await archive_old_jobs(db, days)
    return {"archived": count}


@router.post("/{job_id}/unarchive", response_model=dict[str, str])
async def unarchive(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Restore an archived job (sets is_active=True).

    Raises:
        HTTPException 404: If job not found.
    """
    found = await unarchive_job(db, job_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")


# ──────────────────────── Decision Trail ─────────────────────────────────────

@router.get("/{job_id}/decisions", response_model=DecisionTrail)
async def get_job_decisions(
    job_id: str,
    service: JobService = Depends(get_job_service),
    db: AsyncSession = Depends(get_db),
) -> DecisionTrail:
    """Return the full agent decision trail for a specific job."""
    job = await service._repo.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # Fetch all events for this job (payload is TEXT, use json_extract for SQLite)
    events_result = await db.execute(
        select(AgentEvent)
        .where(func.json_extract(AgentEvent.payload, '$.job_id') == job_id)
        .order_by(AgentEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    # Fetch cost tracking records for this job
    cost_result = await db.execute(
        select(CostTracking).where(CostTracking.job_id == job_id)
    )
    cost_rows = cost_result.scalars().all()
    total_cost = sum(r.cost_estimate or 0.0 for r in cost_rows)

    steps: list[DecisionStep] = []
    step_num = 1

    # Add discovered step
    steps.append(DecisionStep(
        step=step_num,
        agent="scout",
        event_type="discovered",
        status="completed",
        timestamp=job.created_at,
        summary=f"Discovered from {getattr(job, 'source', 'unknown')}",
    ))
    step_num += 1

    # Build steps from events
    for event in events:
        payload: dict = _json.loads(event.payload) if event.payload else {}
        etype = event.event_type

        if etype == "job_scored":
            score_val = payload.get("score", 0)
            steps.append(DecisionStep(
                step=step_num,
                agent="scorer",
                event_type=etype,
                status=event.status,
                timestamp=event.created_at,
                summary=f"Scored {round(score_val * 100)}% overall",
                reasoning=payload.get("reasoning"),
                score=score_val,
                skill_match=payload.get("skill_match"),
                experience_match=payload.get("experience_match"),
                rate_match=payload.get("rate_match"),
                location_match=payload.get("location_match"),
                model_used=payload.get("model_used"),
                tokens_in=payload.get("tokens_in"),
                tokens_out=payload.get("tokens_out"),
                cost_estimate=payload.get("cost_estimate"),
                duration_ms=payload.get("duration_ms"),
            ))
        elif etype == "job_shortlisted":
            score_val = payload.get("score", 0)
            threshold = payload.get("threshold", 0.75)
            steps.append(DecisionStep(
                step=step_num,
                agent="scorer",
                event_type=etype,
                status=event.status,
                timestamp=event.created_at,
                summary=f"Auto-shortlisted: {round(score_val * 100)}% ≥ {round(threshold * 100)}% threshold",
            ))
        elif etype == "cv_tailored":
            steps.append(DecisionStep(
                step=step_num,
                agent="tailor",
                event_type=etype,
                status=event.status,
                timestamp=event.created_at,
                summary=f"CV + cover letter generated — ATS score: {payload.get('ats_score', '?')}%",
                ats_score=payload.get("ats_score"),
                model_used=payload.get("model_used"),
                tokens_in=payload.get("tokens_in"),
                tokens_out=payload.get("tokens_out"),
                cost_estimate=payload.get("cost_estimate"),
                duration_ms=payload.get("duration_ms"),
            ))
        elif etype in ("application_approved", "application_rejected"):
            steps.append(DecisionStep(
                step=step_num,
                agent="human",
                event_type=etype,
                status=event.status,
                timestamp=event.created_at,
                summary="Approved by user" if etype == "application_approved" else "Rejected by user",
            ))
        else:
            continue
        step_num += 1

    return DecisionTrail(
        job_id=job_id,
        job_title=getattr(job, "title", None),
        steps=steps,
        total_cost_usd=round(total_cost, 6),
    )


# ──────────────────────── Hatch v4: Two-step assisted apply ────────────────────────


@router.post("/{job_id}/approve")
async def approve_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve a job for application: tailor docs + assemble package → ready_to_apply.

    This endpoint prepares application materials for human review.
    It does NOT submit anything or fill forms autonomously.
    Status transitions: * → preparing → ready_to_apply.

    Args:
        job_id: UUID of the job posting to approve.

    Returns:
        ApplicationPackage JSON: job_id, job_url, cv_path, cover_letter_path,
        prefill_map, screening_answers, paste_map.

    Raises:
        HTTPException 404: Job not found.
    """
    from sqlalchemy import select, update
    from datetime import datetime

    from ..models.job import JobPosting
    from ..models.application import Application
    from ..services.assisted_apply import AssistedApplyService

    # 1. Verify job exists
    job_result = await db.execute(
        select(JobPosting).where(JobPosting.id == job_id, JobPosting.is_active.is_(True))
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # 2. Find or create the linked Application
    app_result = await db.execute(
        select(Application).where(
            Application.job_id == job_id,
            Application.is_active.is_(True),
        )
    )
    app_obj = app_result.scalar_one_or_none()
    if app_obj is None:
        app_obj = Application(
            job_id=job_id,
            status="approved",
            priority="normal",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(app_obj)
        await db.commit()
        await db.refresh(app_obj)
    else:
        await db.execute(
            update(Application)
            .where(Application.id == app_obj.id)
            .values(status="approved", updated_at=datetime.utcnow())
        )
        await db.commit()

    # 3. Prepare the application package
    service = AssistedApplyService()
    package = await service.prepare_application(job_id=job_id, db=db)

    # 4. Guarantee final status is ready_to_apply (idempotent if prepare_application
    # already set it; a safety net when prepare_application is mocked in tests)
    await db.execute(
        update(Application)
        .where(Application.job_id == job_id)
        .values(status="ready_to_apply", updated_at=datetime.utcnow())
    )
    await db.commit()

    return {
        "job_id": package.job_id,
        "job_url": package.job_url,
        "cv_path": package.cv_path,
        "cover_letter_path": package.cover_letter_path,
        "cv_document_id": package.cv_document_id,
        "cl_document_id": package.cl_document_id,
        "prefill_map": package.prefill_map,
        "screening_answers": package.screening_answers,
        "paste_map": package.paste_map,
    }
