"""Read-only application document-reference context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.runtime.context import ContextItem, ContextRequirement

from .models import ContextSourceMetadata


ApplicationSourceReader = Callable[[str, str], Awaitable[ContextSourceMetadata | None]]


class ApplicationContextProvider:
    """Wraps application-owned document metadata without storing document contents."""

    provider_id = "application.record"
    capabilities = ("application.current_cv", "application.current_cover_letter")

    def __init__(self, source_reader: ApplicationSourceReader) -> None:
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
