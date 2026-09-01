"""Read-only application document-reference context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from hashlib import sha256
import json

from app.runtime.context import ContextItem, ContextRequirement


ApplicationSourceLoader = Callable[[str], Awaitable[Mapping[str, object] | None]]


class ApplicationContextProvider:
    """Wraps application-owned document metadata without storing document contents."""

    provider_id = "application.record"
    capabilities = ("application.current_cv", "application.current_cover_letter")

    def __init__(self, source_loader: ApplicationSourceLoader | None = None) -> None:
        self._source_loader = source_loader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        if self._source_loader is None:
            return None
        source = await self._source_loader(task_attempt_id)
        if source is None:
            return None
        content_hash = sha256(
            json.dumps(
                source, sort_keys=True, default=str, separators=(",", ":")
            ).encode()
        ).hexdigest()
        source_ref = source.get("source_ref")
        if not isinstance(source_ref, str):
            return None
        return ContextItem(
            capability=requirement.capability,
            provider_id=self.provider_id,
            source_ref=source_ref,
            descriptor=requirement.capability.replace(".", "-"),
            summary=None,
            provenance={"source_version": content_hash},
            freshness=None,
            sensitivity="restricted",
            token_estimate=2048,
            confidence=1.0,
            content_hash=content_hash,
        )
