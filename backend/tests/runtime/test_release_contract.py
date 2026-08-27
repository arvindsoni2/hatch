"""Release-level workflow ownership and lifecycle contracts (synthetic SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.runtime.workflow.models import (
    ExecutionClaimRecord,
    TaskAttemptRecord,
    TaskAttemptStatus,
    WaitingReason,
    WorkflowRunRecord,
    WorkflowRunStatus,
    WorkflowStepRecord,
    WorkflowStepStatus,
)
from app.runtime.workflow.retry import RetryFailure
from workflow_test_support import start_and_claim


async def _records(factory, attempt_id: str):
    async with factory.session_factory() as session:
        attempt = await session.get(TaskAttemptRecord, attempt_id)
        assert attempt is not None
        step = await session.get(WorkflowStepRecord, attempt.workflow_step_id)
        assert step is not None
        run = await session.get(WorkflowRunRecord, step.workflow_run_id)
        assert run is not None
        claim = await session.get(ExecutionClaimRecord, attempt.current_claim_id) if attempt.current_claim_id else None
    return attempt, step, run, claim


@pytest.mark.parametrize("operation", ["renew", "finalize", "wait", "unknown", "terminal", "retry"])
@pytest.mark.parametrize("offset", [timedelta(), timedelta(microseconds=1)], ids=["at-expiry", "after-expiry"])
async def test_expired_execution_owner_cannot_mutate_at_exact_lease_boundary(
    workflow_runtime, operation: str, offset: timedelta
) -> None:
    """Would fail if an owner could mutate after its durable lease boundary."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    at_expiry = claim.lease_expires_at + offset

    if operation == "renew":
        changed = await kernel.renew_claim(claim, at_expiry)
    elif operation == "finalize":
        changed = await kernel._repository.finalize(claim, {"result_ref": "synthetic"}, at_expiry)
    elif operation == "wait":
        changed = await kernel.wait_for(claim, WaitingReason.APPROVAL, at_expiry)
    elif operation == "unknown":
        changed = await kernel.mark_outcome_unknown(
            claim, at_expiry, capability_id="synthetic.check", capability_version=1,
            idempotency_class="check_before_retry", reconciliation_reference="synthetic.ref",
        )
    elif operation == "terminal":
        changed = await kernel.fail_terminal(claim, "synthetic_failure", at_expiry)
    else:
        changed = await kernel.fail_or_retry(
            claim, RetryFailure("transient_failure", "synthetic.retry", 1), at_expiry
        )

    assert changed is False or changed is None
    attempt, step, run, current = await _records(factory, claim.task_attempt_id)
    assert attempt.status == TaskAttemptStatus.RUNNING
    assert attempt.current_claim_id == claim.id
    assert step.status == WorkflowStepStatus.RUNNING
    assert run.status == WorkflowRunStatus.RUNNING
    assert current is not None and current.lease_expires_at == claim.lease_expires_at


@pytest.mark.parametrize("decision", ["confirmed", "not_found", "return"])
@pytest.mark.parametrize("offset", [timedelta(), timedelta(microseconds=1)], ids=["at-expiry", "after-expiry"])
async def test_expired_reconciler_cannot_change_ambiguous_attempt(
    workflow_runtime, decision: str, offset: timedelta
) -> None:
    """Would fail if expiry fencing differed for reconciliation completion paths."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, execution_claim = await start_and_claim(kernel, now=now)
    assert await kernel.mark_outcome_unknown(
        execution_claim, now, capability_id="synthetic.check", capability_version=1,
        idempotency_class="check_before_retry", reconciliation_reference="synthetic.ref",
    )
    claim = await kernel.claim_outcome_unknown(execution_claim.task_attempt_id, "reconciler", now)
    assert claim is not None
    at_expiry = claim.lease_expires_at + offset

    if decision == "confirmed":
        changed = await kernel._repository.finalize(claim, {"result_ref": "synthetic"}, at_expiry)
    elif decision == "not_found":
        changed = await kernel.fail_terminal(claim, "outcome_not_found", at_expiry)
    else:
        changed = await kernel.return_outcome_unknown(claim, at_expiry)

    assert changed is False
    attempt, step, run, current = await _records(factory, claim.task_attempt_id)
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert attempt.current_claim_id == claim.id
    assert step.status == WorkflowStepStatus.WAITING
    assert run.status == WorkflowRunStatus.WAITING
    assert current is not None and current.id == claim.id


async def test_attempt_step_run_and_claim_lifecycle_are_atomic(workflow_runtime) -> None:
    """Would fail if R2 updated only attempts while aggregate state drifted."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, first = await start_and_claim(kernel, now=now)
    attempt, step, run, _ = await _records(factory, first.task_attempt_id)
    assert (attempt.status, step.status, run.status) == (
        TaskAttemptStatus.RUNNING, WorkflowStepStatus.RUNNING, WorkflowRunStatus.RUNNING
    )
    assert await kernel.wait_for(first, WaitingReason.APPROVAL, now)
    attempt, step, run, claim = await _records(factory, first.task_attempt_id)
    assert (attempt.status, step.status, run.status, claim) == (
        TaskAttemptStatus.WAITING, WorkflowStepStatus.WAITING, WorkflowRunStatus.WAITING, None
    )
    assert await kernel.resume_waiting(attempt.id, now)
    second = await kernel.claim_next("worker-b", now)
    assert second is not None
    retry = await kernel.fail_or_retry(second, RetryFailure("transient_failure", "synthetic.retry", 1), now)
    assert retry is not None
    prior, step, run, prior_claim = await _records(factory, second.task_attempt_id)
    assert prior.current_claim_id is None and prior_claim is None
    assert (prior.status, step.status, run.status) == (
        TaskAttemptStatus.FAILED, WorkflowStepStatus.PENDING, WorkflowRunStatus.PENDING
    )
    third = await kernel.claim_next("worker-c", now)
    assert third is not None and third.task_attempt_id == retry.id
    assert await kernel.finalize(third, {"result_ref": "synthetic-result"})
    attempt, step, run, claim = await _records(factory, third.task_attempt_id)
    assert attempt.current_claim_id is None and claim is None
    assert (attempt.status, step.status, run.status) == (
        TaskAttemptStatus.SUCCEEDED, WorkflowStepStatus.COMPLETED, WorkflowRunStatus.COMPLETED
    )
    assert step.completed_at is not None and run.completed_at is not None


@pytest.mark.parametrize("bad_reason", [True, " ", "x" * 129, "prompt: synthetic", "/tmp/cv.pdf"])
async def test_terminal_failure_code_is_bounded_and_rolls_back_owner(
    workflow_runtime, bad_reason: object
) -> None:
    """Would fail if terminal error storage admitted content or partially mutated state."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    with pytest.raises(ValueError, match="stable code"):
        await kernel.fail_terminal(claim, bad_reason, now)  # type: ignore[arg-type]
    attempt, step, run, current = await _records(factory, claim.task_attempt_id)
    assert attempt.status == TaskAttemptStatus.RUNNING
    assert attempt.current_claim_id == claim.id
    assert step.status == WorkflowStepStatus.RUNNING
    assert run.status == WorkflowRunStatus.RUNNING
    assert current is not None


@pytest.mark.parametrize("batch_size", [True, 0, -1, 101])
async def test_recovery_rejects_invalid_bounded_batch_size(workflow_runtime, batch_size: object) -> None:
    kernel, _ = workflow_runtime
    with pytest.raises(ValueError, match="batch_size"):
        await kernel.reconcile(datetime(2030, 1, 1), batch_size=batch_size)  # type: ignore[arg-type]


async def test_recovery_processes_only_the_requested_bounded_batch(workflow_runtime) -> None:
    """Would fail if recovery loaded and held the entire expired backlog in one UoW."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    claims = []
    for index in range(3):
        _, claim = await start_and_claim(kernel, now=now + timedelta(seconds=index))
        claims.append(claim)
    expiry = max(claim.lease_expires_at for claim in claims)
    assert await kernel.reconcile(expiry, batch_size=2) == 2
    async with factory.session_factory() as session:
        running = list((await session.scalars(select(TaskAttemptRecord).where(TaskAttemptRecord.status == TaskAttemptStatus.RUNNING))).all())
    assert len(running) == 1
    assert await kernel.reconcile(expiry, batch_size=2) == 1


async def test_recovery_keeps_prior_short_transactions_when_later_record_fails(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Would fail if one bad backlog record rolled back previously recovered work."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, first = await start_and_claim(kernel, now=now)
    _, second = await start_and_claim(kernel, now=now + timedelta(seconds=1))
    expiry = second.lease_expires_at
    original = kernel._repository._reconcile_one_expired_claim
    calls = 0

    async def fail_second(claim_id: str, operation_now: datetime) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic second record failure")
        return await original(claim_id, operation_now)

    monkeypatch.setattr(kernel._repository, "_reconcile_one_expired_claim", fail_second)
    with pytest.raises(RuntimeError, match="second record"):
        await kernel.reconcile(expiry, batch_size=2)
    async with factory.session_factory() as session:
        persisted = await session.get(TaskAttemptRecord, first.task_attempt_id)
    assert persisted is not None and persisted.status == TaskAttemptStatus.PENDING
