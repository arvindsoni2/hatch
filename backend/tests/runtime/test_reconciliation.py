"""Product-independent OUTCOME_UNKNOWN reconciliation contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.runtime.workflow.reconciliation import (
    ReconciliationDecision,
    ReconciliationRegistry,
    WorkflowReconciler,
)
from app.runtime.workflow.retry import RetryFailure
from app.runtime.workflow.models import TaskAttemptStatus
from workflow_test_support import start_and_claim


async def test_unknown_outcome_requires_registered_handler_and_is_not_replayed(workflow_runtime) -> None:
    """Would fail if OUTCOME_UNKNOWN fell through to an automatic retry."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await kernel.mark_outcome_unknown(claim, now) is True

    reconciler = WorkflowReconciler(kernel, ReconciliationRegistry(), worker_id="reconciler-a")
    with pytest.raises(LookupError, match="handler"):
        await reconciler.reconcile_outcome_unknown(claim.task_attempt_id, "artifact.publish", now)
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert await kernel.claim_next("worker-b", now) is None


async def test_confirmed_reconciliation_finishes_unknown_attempt_without_replay(workflow_runtime) -> None:
    """Would fail if a confirmed external effect was retried instead of finalized."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await kernel.mark_outcome_unknown(claim, now)
    registry = ReconciliationRegistry()

    async def confirmed(**_: object) -> ReconciliationDecision:
        return ReconciliationDecision.CONFIRMED

    registry.register("artifact.publish", confirmed)
    result = await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(claim.task_attempt_id, "artifact.publish", now)
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
    assert await kernel.mark_outcome_unknown(claim, now)
    registry = ReconciliationRegistry()

    async def not_found(**_: object) -> ReconciliationDecision:
        return ReconciliationDecision.NOT_FOUND

    registry.register("artifact.publish", not_found)
    retry = await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(
        claim.task_attempt_id,
        "artifact.publish",
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
    assert await kernel.mark_outcome_unknown(claim, now)
    registry = ReconciliationRegistry()

    async def fails(**_: object) -> ReconciliationDecision:
        raise RuntimeError("synthetic handler failure")

    registry.register("artifact.publish", fails)
    with pytest.raises(RuntimeError, match="synthetic handler failure"):
        await WorkflowReconciler(kernel, registry, worker_id="reconciler-a").reconcile_outcome_unknown(claim.task_attempt_id, "artifact.publish", now)
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
    assert await kernel.mark_outcome_unknown(claim, now)
    started = asyncio.Event()
    release = asyncio.Event()
    registry = ReconciliationRegistry()

    async def blocked(**_: object) -> ReconciliationDecision:
        started.set()
        await release.wait()
        return ReconciliationDecision.CONFIRMED

    registry.register("artifact.publish", blocked)
    first = WorkflowReconciler(kernel, registry, worker_id="reconciler-a")
    second = WorkflowReconciler(kernel, registry, worker_id="reconciler-b")
    first_task = asyncio.create_task(first.reconcile_outcome_unknown(claim.task_attempt_id, "artifact.publish", now))
    await started.wait()
    assert await second.reconcile_outcome_unknown(claim.task_attempt_id, "artifact.publish", now) is None
    release.set()
    assert await first_task is ReconciliationDecision.CONFIRMED
