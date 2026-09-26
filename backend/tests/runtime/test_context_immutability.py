"""Immutable per-attempt context package contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.runtime.context import ContextItem, ContextRegistry, ContextRequirement
from app.runtime.context.resolver import ContextResolver
from app.runtime.evaluation import ContextPackageRecord
from workflow_test_support import start_and_claim


class _JobProvider:
    provider_id = "synthetic.job"
    capabilities = ("job.description",)

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem:
        return ContextItem(
            capability="job.description",
            provider_id=self.provider_id,
            source_ref=f"synthetic:{task_attempt_id}",
            descriptor="synthetic-job-description",
            summary=None,
            provenance={"source_version": "synthetic-v1"},
            freshness=datetime(2030, 1, 1, tzinfo=UTC),
            sensitivity="confidential",
            token_estimate=7,
            confidence=1.0,
            content_hash="b" * 64,
        )


@pytest.mark.asyncio
async def test_retry_resolves_new_package_without_mutating_prior(
    workflow_runtime,
) -> None:
    """Retries must get a fresh immutable package, never overwrite their predecessor."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    registry = ContextRegistry()
    registry.register(_JobProvider())
    resolver = ContextResolver(uow_factory, registry)
    requirements = (ContextRequirement(capability="job.description"),)

    first = await resolver.resolve(claim.task_attempt_id, requirements, budget=32)
    async with uow_factory.transaction() as uow:
        retry = await uow.workflows.schedule_retry(
            claim.task_attempt_id,
            retry_reason="transient",
            retry_policy_id="synthetic",
            retry_policy_version=1,
        )
        await uow.commit()
    second = await resolver.resolve(retry.id, requirements, budget=32)

    assert first.id != second.id
    assert first.content_hash != second.content_hash
    assert await resolver.load(first.id) == first
    with pytest.raises(ValidationError):
        first.items[0].descriptor = "changed"
    with pytest.raises(TypeError, match="immutable"):
        first.items[0].provenance["source_version"] = "changed"


def test_context_item_rejects_nested_mutable_provenance() -> None:
    """A package hash cannot be invalidated by mutable nested provenance."""
    with pytest.raises(ValidationError):
        ContextItem(
            capability="job.description",
            provider_id="synthetic.job",
            source_ref="synthetic:attempt",
            descriptor="synthetic-job-description",
            summary=None,
            provenance={"source_version": {"mutable": "value"}},
            freshness=datetime(2030, 1, 1, tzinfo=UTC),
            sensitivity="confidential",
            token_estimate=7,
            confidence=1.0,
            content_hash="d" * 64,
        )


@pytest.mark.asyncio
async def test_load_rejects_corrupted_package_hash(workflow_runtime) -> None:
    """Stored package integrity is checked instead of trusting the row hash."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    registry = ContextRegistry()
    registry.register(_JobProvider())
    resolver = ContextResolver(uow_factory, registry)
    package = await resolver.resolve(
        claim.task_attempt_id,
        (ContextRequirement(capability="job.description"),),
        budget=32,
    )

    async with uow_factory.transaction() as uow:
        record = await uow.session.get(ContextPackageRecord, package.id)
        assert record is not None
        record.content_hash = "0" * 64
        await uow.commit()

    with pytest.raises(ValueError, match="context_package_corrupt"):
        await resolver.load(package.id)
