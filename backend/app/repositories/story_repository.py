"""Database access layer for the Interview Story Bank."""
from __future__ import annotations

import re
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.story import Story, StoryUsage
from ..schemas.story import (
    PaginatedStories,
    StoryCreate,
    StoryListItem,
    StoryRead,
    StoryUpdate,
)

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:200]


class StoryRepository:
    """All database operations for stories and story usages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ──────────────────────── Stories ────────────────────────

    async def create(self, data: StoryCreate) -> StoryRead:
        base_slug = _slugify(data.title)
        slug = await self._unique_slug(base_slug)

        story = Story(
            title=data.title,
            slug=slug,
            summary=data.summary,
            situation=data.situation,
            task=data.task,
            action=data.action,
            result=data.result,
            reflection=data.reflection,
            tags=data.tags,
            skills=data.skills,
            metrics=data.metrics,
            archetype_fit=data.archetype_fit,
            source_session_id=data.source_session_id,
            source_question_id=data.source_question_id,
        )
        self._session.add(story)
        await self._session.flush()
        await self._session.refresh(story)
        return StoryRead.model_validate(story)

    async def get_by_id(self, story_id: str) -> StoryRead | None:
        result = await self._session.execute(
            select(Story).where(Story.id == story_id, Story.is_active.is_(True))
        )
        row = result.scalar_one_or_none()
        return StoryRead.model_validate(row) if row else None

    async def get_orm(self, story_id: str) -> Story | None:
        """Return raw ORM object (needed for embedding update)."""
        result = await self._session.execute(
            select(Story).where(Story.id == story_id, Story.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_active(
        self,
        skip: int = 0,
        limit: int = 50,
        archetype: str | None = None,
        tag: str | None = None,
        skill: str | None = None,
        min_strength: float | None = None,
    ) -> PaginatedStories:
        query = select(Story).where(Story.is_active.is_(True))

        # SQLite JSON_CONTAINS isn't available; filter in Python for tag/skill/archetype
        # We pull all active stories then filter — acceptable for <200 stories (personal tool)
        result = await self._session.execute(query.order_by(Story.strength_score.desc()))
        rows = list(result.scalars().all())

        if archetype:
            rows = [r for r in rows if r.archetype_fit and archetype in r.archetype_fit]
        if tag:
            rows = [r for r in rows if r.tags and tag in r.tags]
        if skill:
            rows = [r for r in rows if r.skills and skill in r.skills]
        if min_strength is not None:
            rows = [r for r in rows if r.strength_score >= min_strength]

        total = len(rows)
        page = rows[skip : skip + limit]
        return PaginatedStories(
            items=[StoryListItem.model_validate(r) for r in page],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def list_all_active_orm(self) -> list[Story]:
        """Return all active Story ORM objects — used by the matcher."""
        result = await self._session.execute(
            select(Story).where(Story.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def update(self, story_id: str, data: StoryUpdate) -> StoryRead | None:
        row = await self.get_orm(story_id)
        if not row:
            return None

        changes = data.model_dump(exclude_none=True)
        for field, value in changes.items():
            setattr(row, field, value)
        row.times_edited += 1
        row.version += 1
        row.updated_at = datetime.utcnow()

        await self._session.flush()
        await self._session.refresh(row)
        return StoryRead.model_validate(row)

    async def set_rating(self, story_id: str, rating: int) -> StoryRead | None:
        await self._session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(manual_rating=rating, updated_at=datetime.utcnow())
        )
        return await self.get_by_id(story_id)

    async def set_strength_score(self, story_id: str, score: float) -> None:
        await self._session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(strength_score=round(score, 2), updated_at=datetime.utcnow())
        )

    async def set_embedding(self, story_id: str, embedding: list[float]) -> None:
        await self._session.execute(
            update(Story).where(Story.id == story_id).values(embedding=embedding)
        )

    async def soft_delete(self, story_id: str) -> bool:
        result = await self._session.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        return result.rowcount > 0

    async def increment_times_used(self, story_id: str) -> None:
        row = await self.get_orm(story_id)
        if row:
            row.times_used += 1
            row.updated_at = datetime.utcnow()
            await self._session.flush()

    # ──────────────────────── Story Usages ────────────────────────

    async def record_usage(
        self,
        story_id: str,
        session_id: str | None = None,
        question_id: str | None = None,
        confidence: float | None = None,
        match_stage: str | None = None,
    ) -> None:
        usage = StoryUsage(
            story_id=story_id,
            session_id=session_id,
            question_id=question_id,
            match_confidence=confidence,
            match_stage=match_stage,
        )
        self._session.add(usage)
        await self._session.flush()
        await self.increment_times_used(story_id)

    async def get_usages_for_story(self, story_id: str) -> list[StoryUsage]:
        result = await self._session.execute(
            select(StoryUsage)
            .where(StoryUsage.story_id == story_id)
            .order_by(StoryUsage.used_at.desc())
        )
        return list(result.scalars().all())

    # ──────────────────────── Helpers ────────────────────────

    async def _unique_slug(self, base: str) -> str:
        candidate = base
        suffix = 1
        while True:
            exists = await self._session.execute(
                select(Story.id).where(Story.slug == candidate)
            )
            if not exists.scalar_one_or_none():
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1
