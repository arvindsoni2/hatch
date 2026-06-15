"""FastAPI router for agent management and approval flow endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.agent_state import AgentState
from ..models.application import Application
from ..models.document import GeneratedDocument
from ..models.job import JobPosting
from ..models.job_score import JobScore
from ..schemas.agent_state import AgentStateRead, AgentStatusSummary, AllAgentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _safe_json(value: str | None) -> Any:
    """Parse a JSON string field safely, returning None on failure."""
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


# ── Dependency: resolve orchestrator from app state ───────────────────────────

def _get_orchestrator(request: Request) -> Any:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Agent orchestrator not initialised")
    return orch


# ── Agent status ──────────────────────────────────────────────────────────────

@router.get("/status", response_model=AllAgentStatus)
async def all_agent_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AllAgentStatus:
    """Return status of every agent + basic system health."""
    result = await db.execute(select(AgentState))
    rows = result.scalars().all()
    summaries = [
        AgentStatusSummary(
            agent_name=r.agent_name,
            status=r.status,
            last_run_at=r.last_run_at,
        )
        for r in rows
    ]
    orch = getattr(request.app.state, "orchestrator", None)
    uptime = orch.uptime_seconds() if orch else 0.0
    return AllAgentStatus(agents=summaries, database="connected", uptime_seconds=uptime)


@router.get("/{name}/status", response_model=AgentStateRead)
async def agent_status(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> AgentStateRead:
    """Return detailed status for a single agent."""
    result = await db.execute(
        select(AgentState).where(AgentState.agent_name == name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    # Deserialise JSON fields for the response
    current_task = json.loads(row.current_task) if row.current_task else None
    config = json.loads(row.config) if row.config else None
    return AgentStateRead(
        agent_name=row.agent_name,
        last_run_at=row.last_run_at,
        status=row.status,
        current_task=current_task,
        config=config,
        updated_at=row.updated_at,
    )


# ── Manual controls ───────────────────────────────────────────────────────────

async def _run_trigger_in_background(orch: Any, name: str) -> None:
    try:
        result = await orch.trigger(name)
        logger.info("Background trigger for %s completed: %s", name, result)
    except Exception as exc:
        logger.warning("Background trigger for %s failed: %s", name, exc)


@router.post("/{name}/trigger")
async def trigger_agent(
    name: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Manually trigger an agent run (fire-and-forget)."""
    orch = _get_orchestrator(request)
    background_tasks.add_task(_run_trigger_in_background, orch, name)
    return {"agent": name, "status": "started"}


@router.post("/{name}/pause")
async def pause_agent(
    name: str,
    request: Request,
) -> dict[str, str]:
    """Pause a running agent."""
    orch = _get_orchestrator(request)
    orch.pause(name)
    return {"agent": name, "status": "paused"}


@router.post("/{name}/resume")
async def resume_agent(
    name: str,
    request: Request,
) -> dict[str, str]:
    """Resume a paused agent."""
    orch = _get_orchestrator(request)
    orch.resume(name)
    return {"agent": name, "status": "resumed"}


# ── Approval flow ─────────────────────────────────────────────────────────────

@router.get("/approvals/pending")
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return applications awaiting human approval, filtered to max_job_age_days."""
    try:
        from ..agents.tools.profile_loader import load_profile  # noqa: PLC0415
        max_age = load_profile().preferences.max_job_age_days
    except Exception:
        max_age = 60
    cutoff = datetime.utcnow() - timedelta(days=max_age)

    result = await db.execute(
        select(Application)
        .join(JobPosting, Application.job_id == JobPosting.id)
        .where(Application.agent_created)
        .where(Application.approval_status == "pending")
        .where(or_(JobPosting.posted_at.is_(None), JobPosting.posted_at >= cutoff))
        .order_by(Application.created_at.desc())
    )
    apps = result.scalars().all()

    output = []
    for app in apps:
        job = None
        if app.job_id:
            job_r = await db.execute(select(JobPosting).where(JobPosting.id == app.job_id))
            job = job_r.scalar_one_or_none()

        score = None
        if app.job_id:
            score_r = await db.execute(select(JobScore).where(JobScore.job_id == app.job_id))
            score = score_r.scalar_one_or_none()

        output.append({
            "application_id": app.id,
            "job_id": app.job_id,
            "job_title": job.title if job else None,
            "company": job.company if job else None,
            "rate_text": job.rate_text if job else None,
            "job_url": job.url if job else None,
            "overall_score": score.overall_score if score else None,
            "skill_match": score.skill_match if score else None,
            "experience_match": score.experience_match if score else None,
            "rate_match": score.rate_match if score else None,
            "location_match": score.location_match if score else None,
            "status": app.status,
            "approval_status": app.approval_status,
            "created_at": app.created_at.isoformat() if app.created_at else None,
        })
    return output


@router.get("/approvals/{application_id}")
async def get_approval_detail(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full detail for a single pending approval — job, score, documents."""
    app_r = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = app_r.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    job = None
    if app.job_id:
        job_r = await db.execute(select(JobPosting).where(JobPosting.id == app.job_id))
        job = job_r.scalar_one_or_none()

    score = None
    if app.job_id:
        score_r = await db.execute(select(JobScore).where(JobScore.job_id == app.job_id))
        score = score_r.scalar_one_or_none()

    # Fetch generated documents (CV + CL)
    docs_r = await db.execute(
        select(GeneratedDocument).where(GeneratedDocument.application_id == application_id)
    )
    docs = docs_r.scalars().all()

    return {
        "application": {
            "id": app.id,
            "status": app.status,
            "approval_status": app.approval_status,
            "agent_created": app.agent_created,
            "created_at": app.created_at.isoformat() if app.created_at else None,
        },
        "job": {
            "id": job.id if job else None,
            "title": job.title if job else None,
            "company": job.company if job else None,
            "location": job.location if job else None,
            "rate_text": job.rate_text if job else None,
            "ir35_status": job.ir35_status if job else None,
            "description": (job.description or "")[:1000] if job else None,
        },
        "score": {
            "overall_score": score.overall_score if score else None,
            "skill_match": score.skill_match if score else None,
            "experience_match": score.experience_match if score else None,
            "rate_match": score.rate_match if score else None,
            "location_match": score.location_match if score else None,
            "reasoning": score.reasoning if score else None,
            "scoring_method": score.scoring_method if score else None,
            "keyword_matches": score.keyword_matches if score else [],
            "keyword_misses": score.keyword_misses if score else [],
        } if score else None,
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "version": d.version,
                "file_path": d.file_path,
                "ats_score": d.ats_score,
                "ats_details": _safe_json(d.ats_details),
                "jd_analysis": _safe_json(d.jd_analysis_snapshot),
                "content_text": getattr(d, "content_text", None),
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
        "notes": app.notes,
    }


@router.post("/approvals/{application_id}/approve")
async def approve_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Approve an application — sets status to applied."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.approval_status != "pending":
        raise HTTPException(status_code=409, detail=f"Application is already '{app.approval_status}'")

    # Retry up to 5 times on SQLite busy/locked errors — the scheduler may hold
    # a write lock briefly while running background scrapers.
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    for attempt in range(5):
        try:
            await db.execute(
                update(Application)
                .where(Application.id == application_id)
                .values(
                    approval_status="approved",
                    status="applied",
                    applied_date=datetime.utcnow(),
                )
            )
            await db.commit()
            return {"application_id": application_id, "status": "approved"}
        except OperationalError as exc:
            if "database is locked" in str(exc) and attempt < 4:
                await db.rollback()
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise


@router.post("/approvals/{application_id}/reject")
async def reject_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Reject an application with an optional reason."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    for attempt in range(5):
        try:
            await db.execute(
                update(Application)
                .where(Application.id == application_id)
                .values(approval_status="rejected", status="not_applying")
            )
            await db.commit()
            return {"application_id": application_id, "status": "rejected"}
        except OperationalError as exc:
            if "database is locked" in str(exc) and attempt < 4:
                await db.rollback()
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise


@router.patch("/approvals/{application_id}/notes")
async def update_application_notes(
    application_id: str,
    body: dict[str, str],
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Save reviewer notes on an application before approving."""
    notes = body.get("notes", "")
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Application not found")
    await db.execute(
        update(Application)
        .where(Application.id == application_id)
        .values(notes=notes)
    )
    await db.commit()
    return {"application_id": application_id, "notes": notes}


# ── Dashboard stats ───────────────────────────────────────────────────────────

@router.get("/dashboard/pipeline")
async def pipeline_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return clearly named all-time agent output counts for the dashboard."""
    from sqlalchemy import func
    from ..models.agent_event import AgentEvent
    from ..models.coach_session import InterviewSession
    from ..models.document import GeneratedDocument

    async def count_events(etype: str) -> int:
        r = await db.execute(
            select(func.count()).select_from(AgentEvent).where(AgentEvent.event_type == etype)
        )
        return r.scalar_one() or 0

    from ..models.job import JobPosting as JP
    total_jobs = (await db.execute(select(func.count()).select_from(JP))).scalar_one() or 0
    scored = (await db.execute(select(func.count()).select_from(JobScore))).scalar_one() or 0
    cv_apps = select(GeneratedDocument.application_id).where(
        GeneratedDocument.document_type == "cv"
    )
    cl_apps = select(GeneratedDocument.application_id).where(
        GeneratedDocument.document_type == "cover_letter"
    )
    tailored = (await db.execute(
        select(func.count()).select_from(Application)
        .where(Application.id.in_(cv_apps))
        .where(Application.id.in_(cl_apps))
    )).scalar_one() or 0
    approved = (await db.execute(
        select(func.count()).select_from(Application)
        .where(Application.agent_created)
        .where(Application.approval_status == "approved")
    )).scalar_one() or 0
    coach_sessions = (await db.execute(
        select(func.count()).select_from(InterviewSession)
        .where(InterviewSession.status.in_(("active", "completed")))
    )).scalar_one() or 0

    return {
        "discovered": total_jobs,
        "scored": scored,
        "shortlisted": await count_events("job_shortlisted"),
        "tailored": tailored,
        "approved": approved,
        "coach_sessions": coach_sessions,
    }


@router.get("/rate-limit-status")
async def rate_limit_status() -> dict:
    """Return current LLM rate limiter state for the dashboard."""
    from ..agents.tools.rate_limiter import get_limiter  # noqa: PLC0415
    return get_limiter().status().as_dict()
