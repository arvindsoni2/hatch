"""The readiness source-change listener (spec §5.3, §7.8)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ...repositories.coach_readiness_repository import CoachReadinessRepository
from ...services.source_events import SourceChange


class ReadinessPrivacy:
    def __init__(self, repository: CoachReadinessRepository) -> None:
        self.repository = repository

    async def on_source_change(
        self, session: AsyncSession, change: SourceChange
    ) -> None:
        await self.repository.delete_derived_for_source(
            session, change.kind, change.source_id
        )
