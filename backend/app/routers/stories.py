"""FastAPI router for the Interview Story Bank."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.story import (
    PaginatedStories,
    StoryCreate,
    StoryListItem,
    StoryMatchRequest,
    StoryMatchResponse,
    StoryRateRequest,
    StoryRead,
    StoryUpdate,
)
from ..services.story_service import StoryService

logger = logging.getLogger(__name__)

# Note: "suggest" and "match" are registered before "/{story_id}" to prevent
# FastAPI from treating those path segments as IDs.
router = APIRouter(prefix="/api/stories", tags=["stories"])


def get_svc() -> StoryService:
    return StoryService()


# ──────────────────────── Collection endpoints ────────────────────────

@router.get("", response_model=PaginatedStories)
async def list_stories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    archetype: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    min_strength: Optional[float] = Query(None, ge=0, le=10),
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> PaginatedStories:
    """List active stories with optional filters, ordered by strength_score desc."""
    return await svc.list_stories(
        db, skip=skip, limit=limit,
        archetype=archetype, tag=tag, skill=skill, min_strength=min_strength,
    )


@router.post("", response_model=StoryRead, status_code=201)
async def create_story(
    data: StoryCreate,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> StoryRead:
    """Create a new story manually."""
    return await svc.create(data, db)


@router.get("/suggest", response_model=list[StoryListItem])
async def suggest_stories(
    archetype: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    top_n: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> list[StoryListItem]:
    """Return top-N stories for an archetype/tags, ordered by strength_score."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    return await svc.suggest(db, archetype=archetype, tags=tag_list, top_n=top_n)


@router.post("/match", response_model=StoryMatchResponse)
async def match_stories(
    request: StoryMatchRequest,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> StoryMatchResponse:
    """Return the top-3 stories that best match a given question."""
    return await svc.match(request, db)


# ──────────────────────── Single story endpoints ────────────────────────

@router.get("/{story_id}", response_model=StoryRead)
async def get_story(
    story_id: str,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> StoryRead:
    story = await svc.get(story_id, db)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.put("/{story_id}", response_model=StoryRead)
async def update_story(
    story_id: str,
    data: StoryUpdate,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> StoryRead:
    """Update a story (increments version and times_edited)."""
    story = await svc.update(story_id, data, db)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.delete("/{story_id}", status_code=204, response_class=Response)
async def delete_story(
    story_id: str,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> Response:
    """Soft-delete a story (sets is_active=False)."""
    deleted = await svc.soft_delete(story_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Story not found")
    return Response(status_code=204)


@router.post("/{story_id}/rate", response_model=StoryRead)
async def rate_story(
    story_id: str,
    request: StoryRateRequest,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> StoryRead:
    """Set a 1-5 manual rating and recompute strength_score."""
    story = await svc.set_rating(story_id, request.rating, db)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/record-use", status_code=204, response_class=Response)
async def record_story_use(
    story_id: str,
    db: AsyncSession = Depends(get_db),
    svc: StoryService = Depends(get_svc),
) -> Response:
    """Increment times_used and recompute strength_score."""
    ok = await svc.record_use(story_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Story not found")
    return Response(status_code=204)
