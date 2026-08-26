"""Product-independent OUTCOME_UNKNOWN reconciliation contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import Base, create_sqlite_engine
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.kernel import WorkflowKernel
from app.runtime.workflow.reconciliation import (
    ReconciliationDecision,
    ReconciliationRegistry,
    WorkflowReconciler,
)
from app.runtime.workflow.retry import RetryFailure
from app.runtime.workflow.models import TaskAttemptStatus
from workflow_test_support import start_and_claim


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


async def mark_unknown(kernel, claim, now: datetime) -> bool:
    return await kernel.mark_outcome_unknown(
        claim,
        now,
        capability_id="artifact.publish",
        capability_version=1,
        idempotency_class="check_before_retry",
        reconciliation_reference="synthetic.publish.1",
    )


async def test_unknown_outcome_requires_registered_handler_and_is_not_replayed(workflow_runtime) -> None:
    """Would fail if OUTCOME_UNKNOWN fell through to an automatic retry."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now) is True

    reconciler = WorkflowReconciler(kernel, ReconciliationRegistry(), worker_id="reconciler-a")
    with pytest.raises(LookupError, match="handler"):
        await reconciler.reconcile_outcome_unknown(claim.task_attempt_id, now)
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    restarted = ReconciliationRegistry()

    async def confirmed_after_restart(**_: object) -> ReconciliationDecision:
        return ReconciliationDecision.CONFIRMED

    restarted.register("artifact.publish", 1, confirmed_after_restart)
    assert (
        await WorkflowReconciler(
            kernel, restarted, worker_id="reconciler-b"
        ).reconcile_outcome_unknown(claim.task_attempt_id, now)
        is ReconciliationDecision.CONFIRMED
    )
    assert await kernel.claim_next("worker-b", now) is None


async def test_confirmed_reconciliation_finishes_unknown_attempt_without_replay(workflow_runtime) -> None:
    """Would fail if a confirmed external effect was retried instead of finalized."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now)
    registry = ReconciliationRegistry()

    async def confirmed(**_: object) -> ReconciliationDecision:
        return ReconciliationDecision.CONFIRMED

    registry.register("artifact.publish", 1, confirmed)
    result = await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(claim.task_attempt_id, now)
    assert result is ReconciliationDecision.CONFIRMED
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.SUCCEEDED
    assert persisted.result_ref_json == {"result_ref": "reconciled-confirmed"}
    assert await kernel.claim_next("worker-b", now) is None


async def test_not_found_retries_only_after_check_before_retry_handler(workflow_runtime) -> None:
    """Would fail if not-found replay occurred without a capability reconciliation decision."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now)
    registry = ReconciliationRegistry()

    async def not_found(**_: object) -> ReconciliationDecision:
        return ReconciliationDecision.NOT_FOUND

    registry.register("artifact.publish", 1, not_found)
    retry = await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(
        claim.task_attempt_id,
        now,
        retry_failure=RetryFailure("outcome_not_found", "artifact.publish.check", 1),
    )
    assert retry is ReconciliationDecision.NOT_FOUND
    original = await kernel.get_attempt(claim.task_attempt_id)
    assert original is not None
    assert original.status == TaskAttemptStatus.FAILED
    next_claim = await kernel.claim_next("worker-b", now)
    assert next_claim is not None
    assert next_claim.task_attempt_id != claim.task_attempt_id


async def test_reconciliation_handler_failure_restores_unknown_for_restart(workflow_runtime) -> None:
    """Would fail if a process-local handler failure stranded or replayed durable state."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now)
    registry = ReconciliationRegistry()

    async def fails(**_: object) -> ReconciliationDecision:
        raise RuntimeError("synthetic handler failure")

    registry.register("artifact.publish", 1, fails)
    with pytest.raises(RuntimeError, match="synthetic handler failure"):
        await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(claim.task_attempt_id, now)
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.OUTCOME_UNKNOWN


async def test_non_retryable_side_effect_is_terminal_and_never_replayed(
    workflow_runtime,
) -> None:
    """Would fail if non-idempotent effects were sent through normal retry scheduling."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    reconciler = WorkflowReconciler(
        kernel, ReconciliationRegistry(), worker_id="reconciler-a"
    )

    assert await reconciler.fail_non_retryable_side_effect(claim, now) is True
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.FAILED
    assert persisted.failure_code == "non_retryable_side_effect"
    assert await kernel.claim_next("worker-b", now) is None


async def test_only_one_reconciler_can_own_unknown_attempt(workflow_runtime) -> None:
    """Would fail if concurrent reconcilers could both run external confirmation."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now)
    started = asyncio.Event()
    release = asyncio.Event()
    registry = ReconciliationRegistry()

    async def blocked(**_: object) -> ReconciliationDecision:
        started.set()
        await release.wait()
        return ReconciliationDecision.CONFIRMED

    registry.register("artifact.publish", 1, blocked)
    first = WorkflowReconciler(kernel, registry, worker_id="reconciler-a")
    second = WorkflowReconciler(kernel, registry, worker_id="reconciler-b")
    first_task = asyncio.create_task(first.reconcile_outcome_unknown(claim.task_attempt_id, now))
    await asyncio.wait_for(started.wait(), timeout=1)
    assert await second.reconcile_outcome_unknown(claim.task_attempt_id, now) is None
    release.set()
    assert await first_task is ReconciliationDecision.CONFIRMED


async def test_reconciliation_claim_survives_crash_and_expiry_as_outcome_unknown(
    tmp_path,
) -> None:
    """Would fail if a new process revived ambiguous work as normal execution."""
    now = datetime(2030, 1, 1)
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'reconciliation-restart.db'}"
    first_engine = create_sqlite_engine(database_url)
    async with first_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    first_factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(first_engine, expire_on_commit=False)
    )
    first_kernel = WorkflowKernel(
        first_factory, lease_duration=timedelta(seconds=30), clock=_FixedClock(now)
    )
    try:
        _, claim = await start_and_claim(first_kernel, now=now)
        assert await mark_unknown(first_kernel, claim, now)
        abandoned = await first_kernel.claim_outcome_unknown(
            claim.task_attempt_id, "reconciler-a", now
        )
        assert abandoned is not None
    finally:
        await first_engine.dispose()

    second_engine = create_sqlite_engine(database_url)
    second_factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(second_engine, expire_on_commit=False)
    )
    restarted_kernel = WorkflowKernel(
        second_factory, lease_duration=timedelta(seconds=30), clock=_FixedClock(now)
    )
    try:
        assert await restarted_kernel.claim_next("normal-worker", now) is None
        assert await restarted_kernel.reconcile(abandoned.lease_expires_at) == 1
        persisted = await restarted_kernel.get_attempt(claim.task_attempt_id)
        assert persisted is not None
        assert persisted.status == TaskAttemptStatus.OUTCOME_UNKNOWN
        assert persisted.current_claim_id is None
        second = await restarted_kernel.claim_outcome_unknown(
            claim.task_attempt_id, "reconciler-b", abandoned.lease_expires_at
        )
        assert second is not None
        assert second.fencing_token > abandoned.fencing_token
    finally:
        await second_engine.dispose()


async def test_reconciler_dispatches_only_the_capability_durably_bound_to_attempt(
    tmp_path,
) -> None:
    """Would fail if a caller could select capability B for attempt A after restart."""
    now = datetime(2030, 1, 1)
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'capability-restart.db'}"
    first_engine = create_sqlite_engine(database_url)
    async with first_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    first_factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(first_engine, expire_on_commit=False)
    )
    first_kernel = WorkflowKernel(
        first_factory, lease_duration=timedelta(seconds=30), clock=_FixedClock(now)
    )
    try:
        _, claim = await start_and_claim(first_kernel, now=now)
        assert await first_kernel.mark_outcome_unknown(
            claim,
            now,
            capability_id="artifact.publish",
            capability_version=1,
            idempotency_class="check_before_retry",
            reconciliation_reference="synthetic.publish.1",
        )
    finally:
        await first_engine.dispose()

    second_engine = create_sqlite_engine(database_url)
    second_factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(second_engine, expire_on_commit=False)
    )
    restarted_kernel = WorkflowKernel(
        second_factory, lease_duration=timedelta(seconds=30), clock=_FixedClock(now)
    )
    registry = ReconciliationRegistry()
    called: list[str] = []

    async def handler_a(**_: object) -> ReconciliationDecision:
        called.append("a")
        return ReconciliationDecision.CONFIRMED

    async def handler_b(**_: object) -> ReconciliationDecision:
        called.append("b")
        return ReconciliationDecision.CONFIRMED

    registry.register("artifact.publish", 1, handler_a)
    registry.register("artifact.delete", 1, handler_b)
    try:
        reconciler = WorkflowReconciler(
            restarted_kernel, registry, worker_id="reconciler-b"
        )
        assert (
            await reconciler.reconcile_outcome_unknown(claim.task_attempt_id, now)
            is ReconciliationDecision.CONFIRMED
        )
        assert called == ["a"]
    finally:
        await second_engine.dispose()


async def test_stale_not_found_reconciliation_reports_ownership_loss(workflow_runtime) -> None:
    """Would fail if a stale reconciler reported NOT_FOUND after losing its fence."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await mark_unknown(kernel, claim, now)
    started = asyncio.Event()
    release = asyncio.Event()
    registry = ReconciliationRegistry()

    async def blocked_not_found(**_: object) -> ReconciliationDecision:
        started.set()
        await release.wait()
        return ReconciliationDecision.NOT_FOUND

    registry.register("artifact.publish", 1, blocked_not_found)
    reconciler = WorkflowReconciler(kernel, registry, worker_id="reconciler-a")
    task = asyncio.create_task(
        reconciler.reconcile_outcome_unknown(
            claim.task_attempt_id,
            now,
            retry_failure=RetryFailure("outcome_not_found", "artifact.publish.check", 1),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    first = await kernel.get_attempt(claim.task_attempt_id)
    assert first is not None and first.current_claim_id is not None
    assert await kernel.reconcile(now + timedelta(seconds=31)) == 1
    replacement = await kernel.claim_outcome_unknown(
        claim.task_attempt_id, "reconciler-b", now + timedelta(seconds=31)
    )
    assert replacement is not None
    release.set()
    assert await task is None
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert persisted.current_claim_id == replacement.id
