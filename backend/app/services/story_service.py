"""CRUD orchestration for the Interview Story Bank."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.story_repository import StoryRepository
from ..schemas.story import (
    PaginatedStories,
    StoryCreate,
    StoryListItem,
    StoryMatchRequest,
    StoryMatchResponse,
    StoryMatchResult,
    StoryRead,
    StoryUpdate,
)
from .story_matcher import StoryMatcher
from .story_scorer import compute_strength_score

logger = logging.getLogger(__name__)

_matcher = StoryMatcher()


class StoryService:
    """Orchestrates story CRUD and match operations."""

    async def create(self, data: StoryCreate, db: AsyncSession) -> StoryRead:
        repo = StoryRepository(db)
        story = await repo.create(data)
        return story

    async def get(self, story_id: str, db: AsyncSession) -> StoryRead | None:
        return await StoryRepository(db).get_by_id(story_id)

    async def list_stories(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50,
        archetype: str | None = None,
        tag: str | None = None,
        skill: str | None = None,
        min_strength: float | None = None,
    ) -> PaginatedStories:
        return await StoryRepository(db).list_active(
            skip=skip,
            limit=limit,
            archetype=archetype,
            tag=tag,
            skill=skill,
            min_strength=min_strength,
        )

    async def suggest(
        self,
        db: AsyncSession,
        archetype: str | None = None,
        tags: list[str] | None = None,
        top_n: int = 5,
    ) -> list[StoryListItem]:
        """Return top-N stories for an archetype, ordered by strength_score."""
        repo = StoryRepository(db)
        result = await repo.list_active(archetype=archetype, limit=100)
        stories = result.items

        if tags:
            # Re-rank by tag overlap then strength
            from .story_matcher import _jaccard
            scored = sorted(
                stories,
                key=lambda s: (
                    _jaccard(tags, s.tags or []),
                    s.strength_score,
                ),
                reverse=True,
            )
            return scored[:top_n]

        return stories[:top_n]

    async def update(self, story_id: str, data: StoryUpdate, db: AsyncSession) -> StoryRead | None:
        repo = StoryRepository(db)
        story = await repo.update(story_id, data)
        if story:
            await self._refresh_strength_score(story_id, db, repo)
        return await repo.get_by_id(story_id)

    async def set_rating(self, story_id: str, rating: int, db: AsyncSession) -> StoryRead | None:
        repo = StoryRepository(db)
        result = await repo.set_rating(story_id, rating)
        if result:
            await self._refresh_strength_score(story_id, db, repo)
        return await repo.get_by_id(story_id)

    async def soft_delete(self, story_id: str, db: AsyncSession) -> bool:
        return await StoryRepository(db).soft_delete(story_id)

    async def record_use(self, story_id: str, db: AsyncSession) -> bool:
        repo = StoryRepository(db)
        story = await repo.get_orm(story_id)
        if not story:
            return False
        await repo.record_usage(story_id)
        await self._refresh_strength_score(story_id, db, repo)
        return True

    async def match(self, request: StoryMatchRequest, db: AsyncSession) -> StoryMatchResponse:
        repo = StoryRepository(db)
        all_stories = await repo.list_all_active_orm()

        results = _matcher.find_matches(
            question=request.question,
            question_tags=request.tags,
            stories=all_stories,
        )

        match_items: list[StoryMatchResult] = []
        for r in results:
            match_items.append(
                StoryMatchResult(
                    story=StoryListItem.model_validate(r.story),
                    confidence=r.confidence,
                    match_stage=r.stage,
                    match_reason=r.reason,
                )
            )

        return StoryMatchResponse(matches=match_items, question=request.question)

    async def _refresh_strength_score(
        self, story_id: str, db: AsyncSession, repo: StoryRepository
    ) -> None:
        story = await repo.get_orm(story_id)
        if not story:
            return

        usages = await repo.get_usages_for_story(story_id)
        last_used_at = usages[0].used_at if usages else None

        new_score = compute_strength_score(story, last_used_at=last_used_at)
        await repo.set_strength_score(story_id, new_score)
