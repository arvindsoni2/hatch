"""FastAPI router for job posting endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
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

    Returns:
        JSON with status 'ok' and current UTC timestamp.
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


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


@router.get("/", response_model=PaginatedResponse[JobPostingRead])
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
    return {"status": "unarchived", "id": job_id}
