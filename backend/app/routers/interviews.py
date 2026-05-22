"""FastAPI router for /api/interviews and /api/interviews/follow-ups endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.interview_repository import InterviewRepository
from ..schemas.interview import (
    FollowUpCreate,
    FollowUpRead,
    FollowUpUpdate,
    InterviewRoundCreate,
    InterviewRoundRead,
    InterviewRoundUpdate,
)

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


def get_interview_repo(db: AsyncSession = Depends(get_db)) -> InterviewRepository:
    """Dependency: returns InterviewRepository with injected session."""
    return InterviewRepository(db)


@router.post("/", response_model=InterviewRoundRead, status_code=201)
async def create_interview(
    data: InterviewRoundCreate,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> InterviewRoundRead:
    """Create a new interview round for an application.

    Args:
        data: InterviewRoundCreate payload.

    Returns:
        Created InterviewRoundRead.
    """
    return await repo.create(data)


@router.get("/upcoming", response_model=list[InterviewRoundRead])
async def get_upcoming_interviews(
    days: int = Query(7, ge=1, le=90),
    repo: InterviewRepository = Depends(get_interview_repo),
) -> list[InterviewRoundRead]:
    """Return all scheduled interviews within the next N days.

    Args:
        days: Look-ahead window in days (1–90).

    Returns:
        List of InterviewRoundRead ordered by scheduled_at ascending.
    """
    return await repo.get_upcoming(days)


@router.patch("/{interview_id}", response_model=InterviewRoundRead)
async def update_interview(
    interview_id: str,
    data: InterviewRoundUpdate,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> InterviewRoundRead:
    """Partially update an interview round.

    Args:
        interview_id: UUID of the interview round.
        data: InterviewRoundUpdate with fields to change.

    Returns:
        Updated InterviewRoundRead.

    Raises:
        HTTPException 404: If not found.
    """
    updated = await repo.update(interview_id, data)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Interview '{interview_id}' not found."
        )
    return updated


@router.patch("/{interview_id}/complete", response_model=InterviewRoundRead)
async def complete_interview(
    interview_id: str,
    data: InterviewRoundUpdate,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> InterviewRoundRead:
    """Mark an interview round as completed.

    Overrides the status field to 'completed' regardless of input.

    Args:
        interview_id: UUID of the interview round.
        data: InterviewRoundUpdate (feedback, notes, etc.).

    Returns:
        Updated InterviewRoundRead with status='completed'.

    Raises:
        HTTPException 404: If not found.
    """
    data.status = "completed"
    updated = await repo.update(interview_id, data)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Interview '{interview_id}' not found."
        )
    return updated


@router.delete("/{interview_id}", status_code=200)
async def delete_interview(
    interview_id: str,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> dict[str, str]:
    """Hard-delete an interview round.

    Args:
        interview_id: UUID of the interview round.

    Returns:
        Confirmation dict with status and id.

    Raises:
        HTTPException 404: If not found.
    """
    deleted = await repo.delete(interview_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Interview '{interview_id}' not found."
        )
    return {"status": "deleted", "id": interview_id}


@router.post("/follow-ups", response_model=FollowUpRead, status_code=201)
async def create_follow_up(
    data: FollowUpCreate,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> FollowUpRead:
    """Create a new follow-up task for an application.

    Args:
        data: FollowUpCreate payload.

    Returns:
        Created FollowUpRead.
    """
    return await repo.create_follow_up(data)


@router.patch("/follow-ups/{follow_up_id}/complete", response_model=FollowUpRead)
async def complete_follow_up(
    follow_up_id: str,
    repo: InterviewRepository = Depends(get_interview_repo),
) -> FollowUpRead:
    """Mark a follow-up task as completed, setting completed_at to now.

    Args:
        follow_up_id: UUID of the follow-up task.

    Returns:
        Updated FollowUpRead with completed=True and completed_at set.

    Raises:
        HTTPException 404: If not found.
    """
    updated = await repo.update_follow_up(
        follow_up_id,
        FollowUpUpdate(completed=True, completed_at=datetime.utcnow()),
    )
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Follow-up '{follow_up_id}' not found."
        )
    return updated


@router.get("/follow-ups/overdue", response_model=list[FollowUpRead])
async def get_overdue_follow_ups(
    repo: InterviewRepository = Depends(get_interview_repo),
) -> list[FollowUpRead]:
    """Return all overdue, incomplete follow-up tasks.

    Returns:
        List of FollowUpRead ordered by due_date ascending.
    """
    return await repo.get_overdue_follow_ups()
