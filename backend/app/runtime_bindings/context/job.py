"""Read-only job-posting context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from hashlib import sha256
import json

from app.runtime.context import ContextItem, ContextRequirement


JobSourceLoader = Callable[[str], Awaitable[Mapping[str, object] | None]]


class JobPostingContextProvider:
    """Wraps a product job source supplied by the owning runtime binding."""

    provider_id = "job.posting"
    capabilities = ("job.summary", "job.requirements", "job.description")

    def __init__(self, source_loader: JobSourceLoader | None = None) -> None:
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
            sensitivity="confidential",
            token_estimate=2048,
            confidence=1.0,
            content_hash=content_hash,
        )
