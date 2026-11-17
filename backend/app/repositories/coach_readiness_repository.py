"""Persistence helpers shared by the readiness privacy listener and later P9."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models.coach_readiness import CoachDerivedSource, CoachDerivedText


class CoachReadinessRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def delete_derived_for_source(
        self, session: AsyncSession, source_kind: str, source_id: str
    ) -> None:
        ids = select(CoachDerivedSource.derived_text_id).where(
            CoachDerivedSource.source_kind == source_kind,
            CoachDerivedSource.source_id == source_id,
        )
        await session.execute(delete(CoachDerivedText).where(CoachDerivedText.id.in_(ids)))
