"""Immutable per-attempt context package contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.runtime.context import ContextItem, ContextRegistry, ContextRequirement
from app.runtime.context.resolver import ContextResolver
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
