"""Content providers that resolve readiness references at execution time."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.runtime.context import ContextItem, ContextRequirement


ReadinessContextReader = Callable[[str, str], Awaitable[ContextItem | None]]


class ReadinessContextProvider:
    provider_id = "coach.readiness"
    capabilities = ("coach.readiness.evidence",)

    def __init__(self, reader: ReadinessContextReader) -> None:
        self._reader = reader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        return await self._reader(task_attempt_id, requirement.capability)
