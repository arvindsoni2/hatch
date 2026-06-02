"""Ghost job detection API endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.job_repository import JobRepository
from ..schemas.ghost import GhostOverrideRequest, GhostScore, GhostStats
from ..schemas.job import JobPostingRead
from ..services.async_job_service import AsyncJobService
from ..services.ghost_detector import GhostDetector

router = APIRouter(prefix="/api/ghost", tags=["ghost"])
logger = logging.getLogger(__name__)
detector = GhostDetector()


@router.get("/stats", response_model=GhostStats)
async def get_ghost_stats(db: AsyncSession = Depends(get_db)) -> GhostStats:
    """Return aggregate ghost verdict counts."""
    repo = JobRepository(db)
    return await repo.get_ghost_stats()


@router.get("/flagged", response_model=list[JobPostingRead])
async def get_flagged_jobs(
    min_score: int = 50,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[JobPostingRead]:
    """Return jobs flagged as suspicious or likely-ghost, sorted by score."""
    repo = JobRepository(db)
    return await repo.get_flagged_jobs(min_score=min_score, limit=limit)


@router.get("/job/{job_id}", response_model=GhostScore)
async def get_job_ghost_score(
    job_id: str, db: AsyncSession = Depends(get_db)
) -> GhostScore:
    """Return the stored ghost score for a single job, re-analysing on the fly if needed."""
    from sqlalchemy import select

    from ..models.job import JobPosting

    result = await db.execute(
        select(JobPosting).where(JobPosting.id == job_id, JobPosting.is_active == True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return await detector.analyse_job(job, db)


@router.post("/analyse/{job_id}", status_code=202)
async def analyse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kick off ghost detection. Poll /api/async-jobs/{async_job_id} for result."""
    async_job = await AsyncJobService.create(db, "ghost_analyse")
    await db.commit()

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        from sqlalchemy import select as sa_select  # noqa: PLC0415
        from ..models.job import JobPosting  # noqa: PLC0415

        try:
            async with AsyncSessionLocal() as own_db:
                result = await own_db.execute(
                    sa_select(JobPosting).where(
                        JobPosting.id == job_id,
                        JobPosting.is_active == True,  # noqa: E712
                    )
                )
                job = result.scalar_one_or_none()
                if job is None:
                    await AsyncJobService._finish(async_job.id, None, "Job not found")
                    return
                score = await detector.analyse_job(job, own_db)
                await AsyncJobService._finish(async_job.id, score.model_dump_json(), None)
        except Exception as exc:
            logger.error("ghost_analyse job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "ghost_analyse"}


@router.post("/analyse-all")
async def analyse_all(
    background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)
) -> dict[str, int]:
    """Queue a batch ghost analysis run for all unscored/stale jobs."""
    from sqlalchemy import select

    from ..models.job import JobPosting

    pending_result = await db.execute(
        select(JobPosting)
        .where(JobPosting.is_active == True, JobPosting.ghost_score.is_(None))
        .limit(1)
    )
    # Count approximate pending jobs
    repo = JobRepository(db)
    stats = await repo.get_ghost_stats()
    queued = stats.total_pending

    background_tasks.add_task(_run_batch_analysis)
    return {"queued": queued}


async def _run_batch_analysis() -> None:
    """Run ghost batch analysis in the background."""
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            scores = await detector.analyse_batch(db)
            logger.info("Background ghost analysis complete: %d jobs scored", len(scores))
        except Exception as exc:
            logger.error("Background ghost analysis failed: %s", exc)


@router.post("/override/{job_id}", response_model=JobPostingRead)
async def override_verdict(
    job_id: str,
    body: GhostOverrideRequest,
    db: AsyncSession = Depends(get_db),
) -> JobPostingRead:
    """Manually override the ghost verdict for a job posting."""
    allowed = {"likely_real", "uncertain", "suspicious", "likely_ghost"}
    if body.override_verdict not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"override_verdict must be one of {sorted(allowed)}",
        )

    from sqlalchemy import select, update

    from ..models.job import JobPosting

    await db.execute(
        update(JobPosting)
        .where(JobPosting.id == job_id)
        .values(ghost_verdict=body.override_verdict)
    )
    await db.commit()

    result = await db.execute(
        select(JobPosting).where(JobPosting.id == job_id, JobPosting.is_active == True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobPostingRead.model_validate(job)
