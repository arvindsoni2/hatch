"""Product context bindings preserve typed source metadata and Coach safety."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.runtime.context import ContextRequirement
from app.runtime_bindings.context.application import ApplicationContextProvider
from app.runtime_bindings.context.coach import CoachContextProvider
from app.runtime_bindings.context.job import JobPostingContextProvider
from app.runtime_bindings.context.models import (
    CoachContextSource,
    ContextSourceMetadata,
)


def _metadata() -> ContextSourceMetadata:
    return ContextSourceMetadata(
        source_ref="job:source-1",
        descriptor="job-description",
        provenance={"source_version": "source-v1"},
        freshness=datetime(2030, 1, 1, tzinfo=UTC),
        sensitivity="restricted",
        token_estimate=17,
        confidence=0.8,
        content_hash="a" * 64,
    )


def test_coach_source_contract_rejects_non_safe_ids() -> None:
    """Reader results use typed safe IDs before a provider can consume them."""
    with pytest.raises(ValidationError):
        CoachContextSource(
            **_metadata().model_dump(),
            task_attempt_id="attempt-1",
            attempt_session_id="not-a-safe-id",
            session_id="not-a-safe-id",
            question_id=None,
            question_session_id=None,
            ownership_verified=True,
            source_version="source-v1",
            required_source_version="source-v1",
            transcript_version=None,
            required_transcript_version=None,
        )


@pytest.mark.asyncio
async def test_job_and_application_bindings_preserve_reader_metadata() -> None:
    """Typed readers, not ad-hoc mappings, determine durable item metadata."""

    async def reader(attempt_id: str, capability: str) -> ContextSourceMetadata:
        return _metadata()

    requirement = ContextRequirement(capability="job.description")
    job_item = await JobPostingContextProvider(reader).resolve("attempt-1", requirement)
    application_item = await ApplicationContextProvider(reader).resolve(
        "attempt-1", ContextRequirement(capability="application.current_cv")
    )

    assert job_item is not None and application_item is not None
    for item in (job_item, application_item):
        assert item.provenance == {"source_version": "source-v1"}
        assert item.freshness == datetime(2030, 1, 1, tzinfo=UTC)
        assert item.sensitivity == "restricted"
        assert item.token_estimate == 17
        assert item.confidence == 0.8
        assert item.content_hash == "a" * 64


@pytest.mark.asyncio
async def test_coach_binding_rejects_cross_session_question() -> None:
    """Coach question context cannot cross the owned session boundary."""
    source = CoachContextSource(
        **_metadata().model_dump(),
        task_attempt_id="attempt-1",
        attempt_session_id=UUID("00000000-0000-0000-0000-000000000003"),
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        question_id=UUID("00000000-0000-0000-0000-000000000002"),
        question_session_id=UUID("00000000-0000-0000-0000-000000000001"),
        ownership_verified=True,
        source_version="source-v1",
        required_source_version="source-v1",
        transcript_version="transcript-v1",
        required_transcript_version="transcript-v1",
    )

    async def reader(attempt_id: str, capability: str) -> CoachContextSource:
        return source

    with pytest.raises(ValueError, match="coach_context_ownership_invalid"):
        await CoachContextProvider(reader).resolve(
            "attempt-1", ContextRequirement(capability="coach.question_context")
        )


@pytest.mark.asyncio
async def test_coach_binding_rejects_stale_transcript_version() -> None:
    """Coach transcript context requires the reader's validated current version."""
    source = CoachContextSource(
        **_metadata().model_dump(),
        task_attempt_id="attempt-1",
        attempt_session_id=UUID("00000000-0000-0000-0000-000000000001"),
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        question_id=None,
        question_session_id=None,
        ownership_verified=True,
        source_version="source-v1",
        required_source_version="source-v1",
        transcript_version="transcript-v1",
        required_transcript_version="transcript-v2",
    )

    async def reader(attempt_id: str, capability: str) -> CoachContextSource:
        return source

    with pytest.raises(ValueError, match="coach_context_version_invalid"):
        await CoachContextProvider(reader).resolve(
            "attempt-1", ContextRequirement(capability="coach.transcript")
        )


@pytest.mark.asyncio
async def test_coach_binding_returns_authorized_current_owned_metadata() -> None:
    """A valid safe-ID association and current versions produce metadata only."""
    source = CoachContextSource(
        **_metadata().model_dump(),
        task_attempt_id="attempt-1",
        attempt_session_id=UUID("00000000-0000-0000-0000-000000000001"),
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        question_id=UUID("00000000-0000-0000-0000-000000000002"),
        question_session_id=UUID("00000000-0000-0000-0000-000000000001"),
        ownership_verified=True,
        source_version="source-v1",
        required_source_version="source-v1",
        transcript_version="transcript-v1",
        required_transcript_version="transcript-v1",
    )

    async def reader(attempt_id: str, capability: str) -> CoachContextSource:
        return source

    item = await CoachContextProvider(reader).resolve(
        "attempt-1", ContextRequirement(capability="coach.question_context")
    )

    assert item is not None
    assert item.summary is None
    assert item.source_ref == source.source_ref
    assert item.content_hash == source.content_hash
