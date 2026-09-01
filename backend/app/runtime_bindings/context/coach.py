"""Read-only, session-scoped Coach context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.runtime.context import ContextItem, ContextRequirement


CoachSourceReader = Callable[[str, str], Awaitable[ContextItem | None]]


class CoachContextProvider:
    """Delegates only to an ownership-checked, immutable Coach source reader.

    The caller must reuse the Coach V6 safe-ID, parent-ownership, source-version,
    and transcript-version seams before returning a metadata-only ``ContextItem``.
    This provider adds no Coach command, media, mutation, deletion, or export path.
    """

    provider_id = "coach.session"
    capabilities = (
        "coach.session_context",
        "coach.question_context",
        "coach.transcript",
    )

    def __init__(self, source_reader: CoachSourceReader | None = None) -> None:
        self._source_reader = source_reader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        if self._source_reader is None:
            return None
        return await self._source_reader(task_attempt_id, requirement.capability)
