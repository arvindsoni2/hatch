"""Outcome learning summary, cache, backfill, recompute, and reset API."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.tools.profile_loader import invalidate_cache, load_profile
from ..database import get_db
from ..models.job_score import JobScore
from ..models.opportunity_score import OpportunityScore
from ..schemas.outcome_learning import OpportunityScoreRead, OutcomeLearningSummary, ResetRequest
from ..services.application_snapshot_service import backfill_existing_applications
from ..services.outcome_learning_service import MODEL_VERSION, build_summary, recompute_active_jobs
from ..services.profile_service import load_profile_raw, save_profile_raw

router = APIRouter(prefix="/api/outcome-learning", tags=["outcome-learning"])


@router.get("/summary", response_model=OutcomeLearningSummary)
async def summary(db: AsyncSession = Depends(get_db)) -> dict:
    return await build_summary(db)


@router.get("/jobs/{job_id}", response_model=OpportunityScoreRead)
async def job_score(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    profile = load_profile()
    base = await db.scalar(select(JobScore.overall_score).where(JobScore.job_id == job_id))
    if base is None:
        raise HTTPException(status_code=404, detail="Job score not found")
    if not profile.outcome_learning.enabled:
        return {"state": "disabled", "job_id": job_id, "base_fit_score": base, "opportunity_score": base}
    cached = await db.scalar(select(OpportunityScore).where(OpportunityScore.job_id == job_id))
    if cached is None:
        return {"state": "not_computed", "job_id": job_id, "base_fit_score": base, "opportunity_score": base}
    return {"state": "computed", "job_id": job_id, "base_fit_score": cached.base_fit_score, "outcome_adjustment": cached.outcome_adjustment, "opportunity_score": cached.opportunity_score, "confidence": cached.confidence, "raw_sample_size": cached.raw_sample_size, "effective_sample_size": cached.effective_sample_size, "reasons": cached.reasons, "model_version": cached.model_version, "calculated_at": cached.calculated_at}


@router.post("/recompute")
async def recompute(limit: int | None = Query(default=None, ge=1, le=10000), db: AsyncSession = Depends(get_db)) -> dict:
    return await recompute_active_jobs(db, limit=limit)


@router.post("/backfill")
async def backfill(limit: int | None = Query(default=None, ge=1, le=10000), db: AsyncSession = Depends(get_db)) -> dict:
    result = await backfill_existing_applications(db, limit=limit)
    result["recompute"] = await recompute_active_jobs(db)
    return result


@router.post("/reset")
async def reset(request: ResetRequest, db: AsyncSession = Depends(get_db)) -> dict:
    if request.confirmation != "RESET":
        raise HTTPException(status_code=422, detail="Confirmation must be RESET")
    now = datetime.utcnow()
    data = load_profile_raw()
    data.setdefault("outcome_learning", {})["learning_since"] = now.isoformat()
    save_profile_raw(data)
    invalidate_cache()
    await db.execute(delete(OpportunityScore))
    await db.flush()
    return {"learning_since": now, "model_version": MODEL_VERSION}
