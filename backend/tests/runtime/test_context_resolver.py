"""Declared, deterministic context resolution contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.runtime.context import ContextItem, ContextRegistry, ContextRequirement
from app.runtime.context.resolver import ContextResolver
from workflow_test_support import start_and_claim


class _RecordingProvider:
    def __init__(self, capability: str) -> None:
        self.provider_id = f"synthetic.{capability}"
        self.capabilities = (capability,)
        self.calls = 0
        self._capability = capability

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem:
        self.calls += 1
        return ContextItem(
            capability=self._capability,
            provider_id=self.provider_id,
            source_ref=f"synthetic:{task_attempt_id}",
            descriptor=f"synthetic-{self._capability.replace('.', '-')}",
            summary=None,
            provenance={"source_version": "synthetic-v1"},
            freshness=datetime(2030, 1, 1, tzinfo=UTC),
            sensitivity="confidential",
            token_estimate=7,
            confidence=1.0,
            content_hash="a" * 64,
        )


@pytest.mark.asyncio
async def test_resolver_never_fetches_undeclared_context(workflow_runtime) -> None:
    """Adding a provider must not expand a task's context implicitly."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    providers = {
        "job.description": _RecordingProvider("job.description"),
        "candidate.resume_text": _RecordingProvider("candidate.resume_text"),
    }
    registry = ContextRegistry()
    for provider in providers.values():
        registry.register(provider)
    resolver = ContextResolver(uow_factory, registry)

    package = await resolver.resolve(
        claim.task_attempt_id,
        (ContextRequirement(capability="job.description"),),
        budget=32,
    )

    assert [item.capability for item in package.items] == ["job.description"]
    assert providers["job.description"].calls == 1
    assert providers["candidate.resume_text"].calls == 0


@pytest.mark.asyncio
async def test_resolver_records_optional_missing_context_reason(
    workflow_runtime,
) -> None:
    """Optional gaps remain visible without failing a declared task attempt."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    resolver = ContextResolver(uow_factory, ContextRegistry())

    package = await resolver.resolve(
        claim.task_attempt_id,
        (ContextRequirement(capability="job.description", required=False),),
        budget=32,
    )

    assert package.items == ()
    assert [
        (omission.capability, omission.reason) for omission in package.omissions
    ] == [("job.description", "context_provider_missing")]
    assert await resolver.load(package.id) == package
