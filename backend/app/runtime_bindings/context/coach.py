"""Read-only, session-scoped Coach context binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.runtime.context import ContextItem, ContextRequirement

from .models import CoachContextSource


CoachSourceReader = Callable[[str, str], Awaitable[CoachContextSource | None]]


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

    def __init__(self, source_reader: CoachSourceReader) -> None:
        self._source_reader = source_reader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        source = await self._source_reader(task_attempt_id, requirement.capability)
        if source is None:
            return None
        if source.task_attempt_id != task_attempt_id or not source.ownership_verified:
            raise ValueError("coach_context_ownership_invalid")
        if source.session_id != source.attempt_session_id:
            raise ValueError("coach_context_ownership_invalid")
        if requirement.capability == "coach.question_context" and (
            source.question_id is None
            or source.question_session_id != source.session_id
        ):
            raise ValueError("coach_context_ownership_invalid")
        if source.source_version != source.required_source_version or (
            requirement.capability == "coach.transcript"
            and (
                source.transcript_version is None
                or source.transcript_version != source.required_transcript_version
            )
        ):
            raise ValueError("coach_context_version_invalid")
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
