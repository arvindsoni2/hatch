"""Declared, deterministic context resolution contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.runtime.context import ContextItem, ContextRegistry, ContextRequirement
from app.runtime.context.resolver import ContextResolutionError, ContextResolver
from app.runtime.evaluation import ContextPackageRecord
from app.runtime.workflow import TaskAttemptRecord
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


@pytest.mark.asyncio
async def test_resolver_rejects_budget_above_package_limit(workflow_runtime) -> None:
    """Budget validation remains within the durable package model bound."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    registry = ContextRegistry()
    registry.register(_RecordingProvider("job.description"))
    resolver = ContextResolver(uow_factory, registry)

    with pytest.raises(ContextResolutionError, match="context_budget_invalid"):
        await resolver.resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description"),),
            budget=32769,
        )


@pytest.mark.asyncio
async def test_resolver_fails_required_missing_and_records_optional_source_missing(
    workflow_runtime,
) -> None:
    """Missing required context fails while a declared unavailable source is durable."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    resolver = ContextResolver(uow_factory, ContextRegistry())
    with pytest.raises(ContextResolutionError, match="context_required_missing"):
        await resolver.resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description"),),
            budget=32,
        )

    class MissingProvider(_RecordingProvider):
        async def resolve(self, task_attempt_id: str, requirement: ContextRequirement):
            return None

    registry = ContextRegistry()
    registry.register(MissingProvider("job.description"))
    package = await ContextResolver(uow_factory, registry).resolve(
        claim.task_attempt_id,
        (ContextRequirement(capability="job.description", required=False),),
        budget=32,
    )
    assert package.omissions[0].reason == "context_source_missing"


@pytest.mark.asyncio
async def test_resolver_enforces_per_requirement_and_cumulative_budgets(
    workflow_runtime,
) -> None:
    """Each declared item and the package total respect the caller budget."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    registry = ContextRegistry()
    registry.register(_RecordingProvider("job.description"))
    registry.register(_RecordingProvider("job.requirements"))
    resolver = ContextResolver(uow_factory, registry)
    with pytest.raises(ContextResolutionError, match="context_budget_exceeded"):
        await resolver.resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description", max_tokens=6),),
            budget=32,
        )
    with pytest.raises(ContextResolutionError, match="context_budget_exceeded"):
        await resolver.resolve(
            claim.task_attempt_id,
            (
                ContextRequirement(capability="job.description"),
                ContextRequirement(capability="job.requirements"),
            ),
            budget=10,
        )


@pytest.mark.asyncio
async def test_resolver_maps_invalid_provider_and_duplicate_binding_to_stable_codes(
    workflow_runtime,
) -> None:
    """Provider faults and a second CAS bind never leak implementation exceptions."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))

    class InvalidProvider(_RecordingProvider):
        async def resolve(self, task_attempt_id: str, requirement: ContextRequirement):
            return object()

    invalid_registry = ContextRegistry()
    invalid_registry.register(InvalidProvider("job.description"))
    with pytest.raises(ContextResolutionError, match="context_provider_invalid"):
        await ContextResolver(uow_factory, invalid_registry).resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description"),),
            budget=32,
        )

    registry = ContextRegistry()
    registry.register(_RecordingProvider("job.description"))
    resolver = ContextResolver(uow_factory, registry)
    package = await resolver.resolve(
        claim.task_attempt_id,
        (ContextRequirement(capability="job.description"),),
        budget=32,
    )
    async with uow_factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
    assert attempt is not None and attempt.context_package_id == package.id
    with pytest.raises(ContextResolutionError, match="context_package_already_bound"):
        await resolver.resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description"),),
            budget=32,
        )
    async with uow_factory.transaction() as uow:
        records = list(
            (
                await uow.session.scalars(
                    select(ContextPackageRecord).where(
                        ContextPackageRecord.task_attempt_id == claim.task_attempt_id
                    )
                )
            ).all()
        )
    assert [record.id for record in records] == [package.id]
