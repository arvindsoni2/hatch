"""FastAPI router for /api/applications endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.application_repository import ApplicationRepository
from ..repositories.interview_repository import InterviewRepository
from ..schemas.application import (
    ApplicationCreate,
    ApplicationKanbanResponse,
    ApplicationListItem,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    KanbanStats,
)
from ..schemas.job import PaginatedResponse
from ..services.application_service import ApplicationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["applications"])


def get_app_service(db: AsyncSession = Depends(get_db)) -> ApplicationService:
    """Dependency: returns ApplicationService with injected session."""
    app_repo = ApplicationRepository(db)
    interview_repo = InterviewRepository(db)
    return ApplicationService(app_repo, interview_repo)


@router.get("/", response_model=PaginatedResponse[ApplicationListItem])
async def list_applications(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: ApplicationService = Depends(get_app_service),
) -> PaginatedResponse[ApplicationListItem]:
    """List all active applications with optional filters.

    Args:
        status: Filter by status string.
        priority: Filter by priority string.
        search: Search title, company, agency, and notes.
        skip: Pagination offset.
        limit: Maximum results to return.

    Returns:
        Paginated list of ApplicationListItem.
    """
    items, total = await service._repo.list_all(status, priority, search, skip, limit)
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/kanban", response_model=ApplicationKanbanResponse)
async def get_kanban(
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationKanbanResponse:
    """Return all active applications grouped by status for the Kanban board.

    Returns:
        ApplicationKanbanResponse with columns dict and summary stats.
    """
    grouped = await service._repo.get_kanban()
    stats = await service._repo.get_kanban_stats()
    return ApplicationKanbanResponse(columns=grouped, stats=stats)


@router.get("/next-actions")
async def get_all_next_actions(
    service: ApplicationService = Depends(get_app_service),
) -> list[dict]:
    """Return prioritised action items across all active applications.

    Returns:
        List of action dicts with application_id, action, reason, and urgency.
    """
    overdue = await service._repo.get_overdue_follow_ups()
    all_actions: list[dict] = []
    for fu in overdue:
        all_actions.append(
            {
                "application_id": fu.application_id,
                "action": f"Complete overdue follow-up: {fu.type}",
                "reason": "Overdue",
                "urgency": "high",
            }
        )
    return all_actions


@router.get("/export")
async def export_applications(
    format: str = Query("csv", pattern="^(csv|json)$"),
    service: ApplicationService = Depends(get_app_service),
) -> Response:
    """Export all active applications as CSV or JSON.

    Args:
        format: Output format — 'csv' or 'json'.

    Returns:
        Response with file content and appropriate content-type header.
    """
    from ..repositories.analytics_repository import AnalyticsRepository
    from ..services.analytics_service import AnalyticsService

    items, _ = await service._repo.list_all(skip=0, limit=10000)
    full_apps: list[ApplicationRead] = []
    for item in items:
        app = await service._repo.get_by_id(item.id)
        if app:
            full_apps.append(app)

    analytics_svc = AnalyticsService(AnalyticsRepository(service._repo._session))
    if format == "csv":
        content = analytics_svc.export_csv(full_apps)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=applications.csv"},
        )
    else:
        import json

        data = analytics_svc.export_json(full_apps)
        return Response(
            content=json.dumps(data, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=applications.json"
            },
        )


@router.post("/from-job/{job_id}", response_model=ApplicationRead, status_code=201)
async def track_from_job(
    job_id: str,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Create a 'discovered' application linked to an existing job posting.

    Args:
        job_id: UUID of the job posting to track.

    Returns:
        New ApplicationRead with status 'discovered'.

    Raises:
        HTTPException 400: If already tracking this job.
    """
    return await service.track_from_job(job_id)


@router.post("/", response_model=ApplicationRead, status_code=201)
async def create_application(
    data: ApplicationCreate,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Create a new application manually (without a linked job posting).

    Args:
        data: ApplicationCreate payload.

    Returns:
        New ApplicationRead.
    """
    return await service.create_application(data)


@router.get("/follow-up-reminders")
async def get_follow_up_reminders(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return applications that are due or overdue for a follow-up.

    Uses profile.yaml follow_up_days config (default [5, 10, 15]) to determine
    when follow-ups should be sent after the applied_date.
    """
    from ..models.application import Application
    from ..models.job import JobPosting
    from ..agents.tools.profile_loader import load_profile

    profile = load_profile()
    follow_up_days: list[int] = profile.preferences.follow_up_days

    result = await db.execute(
        select(Application).where(
            Application.status == "applied",
            Application.applied_date.isnot(None),
            Application.is_active == True,
        )
    )
    apps = result.scalars().all()

    now = datetime.utcnow()
    reminders: list[dict[str, Any]] = []

    for app in apps:
        if app.applied_date is None:
            continue

        days_since = (now - app.applied_date).days

        job_title: str | None = None
        company: str | None = None
        if app.job_id:
            job_r = await db.execute(select(JobPosting).where(JobPosting.id == app.job_id))
            job = job_r.scalar_one_or_none()
            if job:
                job_title = job.title
                company = job.company

        for i, threshold in enumerate(sorted(follow_up_days)):
            if days_since >= threshold:
                if i == len(follow_up_days) - 1 or days_since < sorted(follow_up_days)[i + 1]:
                    due_date = app.applied_date + timedelta(days=threshold)
                    reminders.append({
                        "application_id": app.id,
                        "job_title": job_title,
                        "company": company,
                        "applied_date": app.applied_date.isoformat(),
                        "days_since_applied": days_since,
                        "follow_up_number": i + 1,
                        "due_date": due_date.isoformat(),
                        "overdue": days_since > threshold,
                    })
                    break

    reminders.sort(key=lambda r: r["days_since_applied"], reverse=True)
    return reminders


@router.get("/{app_id}", response_model=ApplicationRead)
async def get_application(
    app_id: str,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Get a single application with all nested data (interviews, follow-ups, activity).

    Args:
        app_id: UUID of the application.

    Returns:
        Full ApplicationRead.

    Raises:
        HTTPException 404: If not found or inactive.
    """
    app = await service._repo.get_by_id(app_id, load_relations=True)
    if app is None:
        raise HTTPException(
            status_code=404, detail=f"Application '{app_id}' not found."
        )
    return app


@router.patch("/{app_id}", response_model=ApplicationRead)
async def update_application(
    app_id: str,
    data: ApplicationUpdate,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Partially update application fields (no state machine enforcement).

    Args:
        app_id: UUID of the application.
        data: ApplicationUpdate with fields to change.

    Returns:
        Updated ApplicationRead.

    Raises:
        HTTPException 404: If not found.
    """
    updated = await service._repo.update(app_id, data)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Application '{app_id}' not found."
        )
    return updated


@router.patch("/{app_id}/status", response_model=ApplicationRead)
async def update_application_status(
    app_id: str,
    data: ApplicationStatusUpdate,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Move application to a new status with state machine enforcement.

    Args:
        app_id: UUID of the application.
        data: ApplicationStatusUpdate with new status and optional note.

    Returns:
        Updated ApplicationRead.

    Raises:
        HTTPException 404: If not found.
        HTTPException 422: If the transition is not permitted.
    """
    return await service.update_status(app_id, data)


@router.post("/{app_id}/notes", response_model=ApplicationRead)
async def add_note(
    app_id: str,
    body: dict,
    service: ApplicationService = Depends(get_app_service),
) -> ApplicationRead:
    """Append a timestamped note to the application.

    Args:
        app_id: UUID of the application.
        body: JSON body containing a 'note' key with the note text.

    Returns:
        Updated ApplicationRead.

    Raises:
        HTTPException 422: If 'note' field is missing or empty.
    """
    note_text = body.get("note", "")
    if not note_text:
        raise HTTPException(status_code=422, detail="'note' field is required.")
    return await service.add_note(app_id, note_text)


@router.delete("/{app_id}", status_code=200)
async def delete_application(
    app_id: str,
    service: ApplicationService = Depends(get_app_service),
) -> dict[str, str]:
    """Soft-delete an application (sets is_active=False).

    Args:
        app_id: UUID of the application.

    Returns:
        Confirmation dict with status and id.

    Raises:
        HTTPException 404: If not found.
    """
    deleted = await service._repo.soft_delete(app_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Application '{app_id}' not found."
        )
    return {"status": "deleted", "id": app_id}
