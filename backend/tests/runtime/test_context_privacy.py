"""Context-package privacy and atomic safe-failure contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlalchemy import select

from app.runtime.context import (
    ContextItem,
    ContextPackage,
    ContextRegistry,
    ContextRequirement,
)
from app.runtime.context.resolver import ContextResolutionError, ContextResolver
from app.runtime.evaluation import ContextPackageRecord
from app.runtime.workflow import TaskAttemptRecord
from workflow_test_support import start_and_claim


class _UnsafeJobProvider:
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
            summary="CANARY_CONTEXT_RAW_CONTENT",
            provenance={"source_version": "synthetic-v1"},
            freshness=datetime(2030, 1, 1, tzinfo=UTC),
            sensitivity="confidential",
            token_estimate=7,
            confidence=1.0,
            content_hash="c" * 64,
        )


@pytest.mark.asyncio
async def test_raw_content_canary_fails_without_package_persistence(
    workflow_runtime,
) -> None:
    """A raw-content-looking field must not create a package or bind the attempt."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    registry = ContextRegistry()
    registry.register(_UnsafeJobProvider())
    resolver = ContextResolver(uow_factory, registry)

    with pytest.raises(ContextResolutionError, match="context_package_metadata_unsafe"):
        await resolver.resolve(
            claim.task_attempt_id,
            (ContextRequirement(capability="job.description"),),
            budget=32,
        )

    async with uow_factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
        records = list(
            (
                await uow.session.scalars(
                    select(ContextPackageRecord).where(
                        ContextPackageRecord.task_attempt_id == claim.task_attempt_id
                    )
                )
            ).all()
        )
    assert attempt is not None and attempt.context_package_id is None
    assert records == []


@pytest.mark.asyncio
async def test_store_rejects_raw_content_without_partial_persistence(
    workflow_runtime,
) -> None:
    """The UoW seam must enforce privacy even when resolver validation is bypassed."""
    kernel, uow_factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    unsafe_item = ContextItem(
        capability="job.description",
        provider_id="synthetic.job",
        source_ref=f"synthetic:{claim.task_attempt_id}",
        descriptor="synthetic-job-description",
        summary="CANARY_CONTEXT_RAW_CONTENT",
        provenance={"source_version": "synthetic-v1"},
        freshness=datetime(2030, 1, 1, tzinfo=UTC),
        sensitivity="confidential",
        token_estimate=7,
        confidence=1.0,
        content_hash="e" * 64,
    )
    package = ContextPackage(
        id="unsafe-package",
        task_attempt_id=claim.task_attempt_id,
        items=(unsafe_item,),
        total_token_estimate=7,
        content_hash="f" * 64,
    )

    async with uow_factory.transaction() as uow:
        with pytest.raises(ValueError, match="context_package_metadata_unsafe"):
            await uow.context_packages.persist_and_bind(package)
        await uow.commit()

    async with uow_factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
        records = list(
            (
                await uow.session.scalars(
                    select(ContextPackageRecord).where(
                        ContextPackageRecord.task_attempt_id == claim.task_attempt_id
                    )
                )
            ).all()
        )
    assert attempt is not None and attempt.context_package_id is None
    assert records == []
