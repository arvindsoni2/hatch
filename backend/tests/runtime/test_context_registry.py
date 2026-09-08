"""Context capability registration contracts."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime
from uuid import UUID

from app.runtime.context import ContextRegistry
from app.runtime.context.models import INITIAL_CONTEXT_CAPABILITIES
from app.runtime_bindings.context import register_initial_context_providers
from app.runtime_bindings.context.models import (
    CoachContextSource,
    ContextSourceMetadata,
)


class _JobDescriptionProvider:
    provider_id = "synthetic.job"
    capabilities = ("job.description",)


class _DuplicateJobDescriptionProvider:
    provider_id = "synthetic.duplicate-job"
    capabilities = ("job.description", "job.description")


class _UnknownProvider:
    provider_id = "synthetic.unknown"
    capabilities = ("job.unregistered",)


def test_registry_rejects_duplicate_capability_registration() -> None:
    """A second owner would make declared resolution non-deterministic."""
    registry = ContextRegistry()
    registry.register(_JobDescriptionProvider())

    with pytest.raises(ValueError, match="context_capability_duplicate"):
        registry.register(_JobDescriptionProvider())


def test_registry_rejects_duplicate_capability_in_one_provider() -> None:
    """A malformed provider declaration cannot make ownership ambiguous."""
    with pytest.raises(ValueError, match="context_capability_duplicate"):
        ContextRegistry().register(_DuplicateJobDescriptionProvider())


def test_registry_rejects_unknown_capability_registration() -> None:
    """The registry cannot advertise capabilities outside the declared vocabulary."""
    with pytest.raises(ValueError, match="context_capability_unknown"):
        ContextRegistry().register(_UnknownProvider())


def test_product_bindings_register_exact_initial_capability_vocabulary() -> None:
    """Generic resolution obtains all product capabilities only through bindings."""

    async def reader(attempt_id: str, capability: str) -> ContextSourceMetadata:
        return ContextSourceMetadata(
            source_ref="synthetic:source",
            descriptor="synthetic-source",
            provenance={"source_version": "synthetic-v1"},
            freshness=datetime(2030, 1, 1, tzinfo=UTC),
            sensitivity="confidential",
            token_estimate=1,
            confidence=1.0,
            content_hash="a" * 64,
        )

    async def coach_reader(attempt_id: str, capability: str) -> CoachContextSource:
        return CoachContextSource(
            **(await reader(attempt_id, capability)).model_dump(),
            task_attempt_id=attempt_id,
            attempt_session_id=UUID("00000000-0000-0000-0000-000000000001"),
            session_id=UUID("00000000-0000-0000-0000-000000000001"),
            question_id=None,
            question_session_id=None,
            ownership_verified=True,
            source_version="synthetic-v1",
            required_source_version="synthetic-v1",
            transcript_version="synthetic-v1",
            required_transcript_version="synthetic-v1",
        )

    registry = ContextRegistry()
    register_initial_context_providers(
        registry,
        job_reader=reader,
        application_reader=reader,
        coach_reader=coach_reader,
    )

    assert {
        capability
        for capability in INITIAL_CONTEXT_CAPABILITIES
        if registry.provider_for(capability) is not None
    } == INITIAL_CONTEXT_CAPABILITIES


def test_product_binding_registration_requires_typed_readers() -> None:
    """The composition root must not silently advertise inert capabilities."""
    with pytest.raises(TypeError):
        register_initial_context_providers(ContextRegistry())
