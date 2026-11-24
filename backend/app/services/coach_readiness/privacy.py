"""The readiness source-change listener and the "What Hatch remembers" page.

Spec §5.3, §7.8, §11, §12. Every inventory/delete call opens its own session
from the repository factory and commits it, matching the production router.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.coach_readiness import (
    CoachCompetencyOverride,
    CoachDerivedSource,
    CoachDerivedText,
    CoachFocusArea,
    CoachInterviewBrief,
    CoachInterviewDebrief,
    CoachPatternDismissal,
    CoachPracticePlan,
)
from ...repositories.coach_readiness_repository import CoachReadinessRepository
from ...repositories.interview_repository import InterviewRepository
from ...schemas.interview import InterviewRoundUpdate
from ...services.source_events import SourceChange

MemoryKind = Literal[
    "dismissed_patterns",
    "focus_areas_and_plans",
    "briefs",
    "debriefs",
    "explain_tips",
    "competency_overrides",
    "job_competencies",
]
MEMORY_KINDS: tuple[MemoryKind, ...] = (
    "dismissed_patterns",
    "focus_areas_and_plans",
    "briefs",
    "debriefs",
    "explain_tips",
    "competency_overrides",
    "job_competencies",
)


@dataclass(frozen=True)
class MemoryKindSummary:
    kind: MemoryKind
    count: int
    last_updated: datetime | None


@dataclass(frozen=True)
class MemoryInventory:
    kinds: tuple[MemoryKindSummary, ...]


@dataclass(frozen=True)
class MemoryDeletionResult:
    removed: dict[MemoryKind, int]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _max_of(values: Sequence[datetime | None]) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


class ReadinessPrivacy:
    def __init__(self, repository: CoachReadinessRepository) -> None:
        self.repository = repository

    async def on_source_change(
        self, session: AsyncSession, change: SourceChange
    ) -> None:
        await self.repository.delete_derived_for_source(
            session, change.kind, change.source_id
        )

    async def inventory(self) -> MemoryInventory:
        async with self.repository.session_factory() as session:
            return await self._inventory(session)

    async def delete_kind(
        self, kind: MemoryKind, *, clear_round_questions: bool = False
    ) -> int:
        async with self.repository.session_factory() as session:
            if kind == "focus_areas_and_plans":
                removed = await self._delete_rows(session, CoachFocusArea)
                removed += await self._delete_rows(session, CoachPracticePlan)
            elif kind == "dismissed_patterns":
                removed = await self._delete_rows(session, CoachPatternDismissal)
            elif kind == "debriefs":
                removed = await self._delete_debriefs(
                    session, clear_round_questions=clear_round_questions
                )
            elif kind == "competency_overrides":
                removed = await self._delete_rows(session, CoachCompetencyOverride)
            elif kind == "briefs":
                removed = await self._delete_derived(session, "brief")
            elif kind == "explain_tips":
                removed = await self._delete_derived(session, "explain")
            elif kind == "job_competencies":
                removed = await self._delete_derived(session, "competency")
            else:
                raise ValueError(f"unknown memory kind: {kind}")
            await session.commit()
            return removed

    async def delete_all(self) -> MemoryDeletionResult:
        async with self.repository.session_factory() as session:
            inventory = await self._inventory(session)
            removed = {item.kind: item.count for item in inventory.kinds}
            # Sources first: the FK cascade is enabled in production SQLite, but
            # deleting explicitly keeps this correct under any connection.
            await self._delete_rows(session, CoachDerivedSource)
            await self._delete_rows(session, CoachDerivedText)
            await self._delete_rows(session, CoachInterviewBrief)
            await self._delete_rows(session, CoachInterviewDebrief)
            await self._delete_rows(session, CoachFocusArea)
            await self._delete_rows(session, CoachPracticePlan)
            await self._delete_rows(session, CoachPatternDismissal)
            await self._delete_rows(session, CoachCompetencyOverride)
            await session.commit()
            return MemoryDeletionResult(removed=removed)

    async def _inventory(self, session: AsyncSession) -> MemoryInventory:
        kinds: list[MemoryKindSummary] = []
        for kind in MEMORY_KINDS:
            count, last = await self._count_and_last(session, kind)
            kinds.append(
                MemoryKindSummary(
                    kind=kind,
                    count=count,
                    last_updated=_utc(last) if count else None,
                )
            )
        return MemoryInventory(kinds=tuple(kinds))

    async def _count_and_last(
        self, session: AsyncSession, kind: MemoryKind
    ) -> tuple[int, datetime | None]:
        if kind == "dismissed_patterns":
            return await self._count_last(
                session, CoachPatternDismissal, CoachPatternDismissal.dismissed_at
            )
        if kind == "debriefs":
            return await self._count_last(
                session, CoachInterviewDebrief, CoachInterviewDebrief.updated_at
            )
        if kind == "competency_overrides":
            return await self._count_last(
                session, CoachCompetencyOverride, CoachCompetencyOverride.updated_at
            )
        if kind == "focus_areas_and_plans":
            focus = await self._count_last(
                session, CoachFocusArea, CoachFocusArea.updated_at
            )
            plans = await self._count_last(
                session, CoachPracticePlan, CoachPracticePlan.updated_at
            )
            return focus[0] + plans[0], _max_of((focus[1], plans[1]))
        derived_kind = {
            "briefs": "brief",
            "explain_tips": "explain",
            "job_competencies": "competency",
        }[kind]
        count, last = (
            await session.execute(
                select(
                    func.count(CoachDerivedText.id),
                    func.max(CoachDerivedText.created_at),
                ).where(CoachDerivedText.kind == derived_kind)
            )
        ).one()
        return int(count or 0), last

    async def _count_last(self, session: AsyncSession, model, column) -> tuple[int, datetime | None]:
        count, last = (
            await session.execute(select(func.count(), func.max(column)))
        ).one()
        return int(count or 0), last

    async def _delete_rows(self, session: AsyncSession, model) -> int:
        result = await session.execute(delete(model))
        return int(result.rowcount or 0)

    async def _delete_derived(self, session: AsyncSession, kind: str) -> int:
        result = await session.execute(
            delete(CoachDerivedText).where(CoachDerivedText.kind == kind)
        )
        return int(result.rowcount or 0)

    async def _delete_debriefs(
        self, session: AsyncSession, *, clear_round_questions: bool
    ) -> int:
        round_ids = (
            await session.execute(
                select(CoachInterviewDebrief.interview_round_id)
            )
        ).scalars().all()
        result = await session.execute(delete(CoachInterviewDebrief))
        removed = int(result.rowcount or 0)
        if clear_round_questions:
            repository = InterviewRepository(session)
            for round_id in round_ids:
                await repository.update(
                    round_id, InterviewRoundUpdate(questions_asked=[])
                )
        return removed
