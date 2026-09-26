"""Read-only master-resume context binding."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from app.runtime.context import ContextItem, ContextRequirement
from app.services.resume_store import get_resume_text


class ResumeContextProvider:
    """Hashes the existing resume source and persists only an opaque reference."""

    provider_id = "resume.store"
    capabilities = ("candidate.resume_text",)

    def __init__(self, loader: Callable[[], str] = get_resume_text) -> None:
        self._loader = loader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        try:
            resume = self._loader()
        except Exception:
            return None
        if not isinstance(resume, str) or not resume.strip():
            return None
        content_hash = sha256(resume.encode("utf-8")).hexdigest()
        return ContextItem(
            capability=requirement.capability,
            provider_id=self.provider_id,
            source_ref="candidate:resume",
            descriptor="candidate-resume-text",
            summary=None,
            provenance={"source_version": content_hash},
            freshness=None,
            sensitivity="restricted",
            token_estimate=4096,
            confidence=1.0,
            content_hash=content_hash,
        )
