"""Read-only job-posting context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.runtime.context import ContextItem, ContextRequirement

from .models import ContextSourceMetadata


JobSourceReader = Callable[[str, str], Awaitable[ContextSourceMetadata | None]]


class JobPostingContextProvider:
    """Wraps a product job source supplied by the owning runtime binding."""

    provider_id = "job.posting"
    capabilities = ("job.summary", "job.requirements", "job.description")

    def __init__(self, source_reader: JobSourceReader) -> None:
        self._source_reader = source_reader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        source = await self._source_reader(task_attempt_id, requirement.capability)
        if source is None:
            return None
        return ContextItem(
            capability=requirement.capability,
            provider_id=self.provider_id,
            source_ref=source.source_ref,
            descriptor=source.descriptor,
            summary=None,
            provenance=source.provenance,
            freshness=source.freshness,
            sensitivity=source.sensitivity,
            token_estimate=source.token_estimate,
            confidence=source.confidence,
            content_hash=source.content_hash,
        )
