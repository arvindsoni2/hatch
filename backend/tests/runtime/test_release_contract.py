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
from app.runtime.workflow.kernel import WorkflowKernel
from app.runtime.workflow.repository import SQLiteWorkflowRepository
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
    assert await kernel.reconcile(expiry, batch_size=2) == 1
    async with factory.session_factory() as session:
        persisted = await session.get(TaskAttemptRecord, first.task_attempt_id)
    assert persisted is not None and persisted.status == TaskAttemptStatus.PENDING


async def test_delayed_retry_promotes_only_when_due_and_completes_aggregate_lifecycle(
    workflow_runtime,
) -> None:
    """Would fail if delayed retries, result provenance, or aggregate timestamps drifted."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, first = await start_and_claim(kernel, now=now)
    due_at = now + timedelta(seconds=5)
    retry = await kernel.fail_or_retry(
        first,
        RetryFailure("transient_failure", "synthetic.retry", 1, retry_after=timedelta(seconds=5)),
        now,
    )
    assert retry is not None
    prior, step, run, claim = await _records(factory, first.task_attempt_id)
    assert (prior.status, prior.finished_at, prior.current_claim_id) == (
        TaskAttemptStatus.FAILED,
        now,
        None,
    )
    assert (step.status, step.completed_at, run.status, run.completed_at, claim) == (
        WorkflowStepStatus.WAITING,
        None,
        WorkflowRunStatus.WAITING,
        None,
        None,
    )
    queued = await kernel.get_attempt(retry.id)
    assert queued is not None
    assert (queued.status, queued.waiting_reason, queued.started_at, queued.finished_at) == (
        TaskAttemptStatus.WAITING,
        WaitingReason.RETRY_TIME,
        None,
        None,
    )
    assert await kernel.claim_next("worker-b", due_at - timedelta(microseconds=1)) is None
    second = await kernel.claim_next("worker-b", due_at)
    assert second is not None and second.task_attempt_id == retry.id
    assert await kernel.finalize(second, {"result_ref": "synthetic-result"}, now=due_at)
    completed, step, run, current = await _records(factory, retry.id)
    assert (completed.status, completed.current_claim_id, current) == (
        TaskAttemptStatus.SUCCEEDED,
        None,
        None,
    )
    assert completed.result_ref_json == {"result_ref": "synthetic-result"}
    assert completed.finished_at is not None
    assert (step.status, step.completed_at, run.status, run.completed_at) == (
        WorkflowStepStatus.COMPLETED,
        completed.finished_at,
        WorkflowRunStatus.COMPLETED,
        completed.finished_at,
    )
    assert run.result_ref_json == {"result_ref": "synthetic-result"}
    assert run.failure_code is None and step.failure_code is None


async def test_retry_budget_and_explicit_terminal_failure_set_terminal_aggregate_fields(
    workflow_runtime,
) -> None:
    """Would fail if retry exhaustion appended a third attempt or terminalized aggregates incompletely."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, first = await start_and_claim(kernel, now=now, max_attempts=2)
    retry = await kernel.fail_or_retry(first, RetryFailure("transient_failure", "synthetic.retry", 1), now)
    assert retry is not None
    second = await kernel.claim_next("worker-b", now)
    assert second is not None and second.task_attempt_id == retry.id
    assert await kernel.fail_or_retry(
        second, RetryFailure("retry_exhausted", "synthetic.retry", 1), now
    ) is None
    terminal, step, run, current = await _records(factory, second.task_attempt_id)
    assert (terminal.status, terminal.failure_code, terminal.finished_at, current) == (
        TaskAttemptStatus.FAILED,
        "retry_exhausted",
        now,
        None,
    )
    assert (step.status, step.failure_code, step.completed_at) == (
        WorkflowStepStatus.FAILED,
        "retry_exhausted",
        now,
    )
    assert (run.status, run.failure_code, run.completed_at, run.result_ref_json) == (
        WorkflowRunStatus.FAILED,
        "retry_exhausted",
        now,
        None,
    )
    async with factory.session_factory() as session:
        attempts = list((await session.scalars(select(TaskAttemptRecord))).all())
    assert len(attempts) == 2

    _, explicit = await start_and_claim(kernel, now=now + timedelta(seconds=1))
    assert await kernel.fail_terminal(explicit, "explicit_failure", now + timedelta(seconds=1))
    failed, failed_step, failed_run, current = await _records(factory, explicit.task_attempt_id)
    assert (failed.status, failed.failure_code, failed.finished_at, current) == (
        TaskAttemptStatus.FAILED,
        "explicit_failure",
        now + timedelta(seconds=1),
        None,
    )
    assert (failed_step.status, failed_run.status) == (
        WorkflowStepStatus.FAILED,
        WorkflowRunStatus.FAILED,
    )


async def test_expired_execution_and_outcome_unknown_claims_recover_without_aggregate_drift(
    workflow_runtime,
) -> None:
    """Would fail if expired execution or reconciliation ownership left stale current claims."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, execution_claim = await start_and_claim(kernel, now=now)
    assert await kernel.reconcile(execution_claim.lease_expires_at) == 1
    recovered, step, run, current = await _records(factory, execution_claim.task_attempt_id)
    assert (recovered.status, recovered.current_claim_id, step.status, run.status, current) == (
        TaskAttemptStatus.PENDING,
        None,
        WorkflowStepStatus.PENDING,
        WorkflowRunStatus.PENDING,
        None,
    )
    assert step.completed_at is None and run.completed_at is None

    _, external_claim = await start_and_claim(kernel, now=now + timedelta(seconds=1))
    assert await kernel.mark_outcome_unknown(
        external_claim,
        now + timedelta(seconds=1),
        capability_id="synthetic.check",
        capability_version=1,
        idempotency_class="check_before_retry",
        reconciliation_reference="synthetic.ref",
    )
    recon_claim = await kernel.claim_outcome_unknown(
        external_claim.task_attempt_id, "reconciler", now + timedelta(seconds=1)
    )
    assert recon_claim is not None
    assert await kernel.reconcile(recon_claim.lease_expires_at) == 1
    unknown, step, run, current = await _records(factory, external_claim.task_attempt_id)
    assert (unknown.status, unknown.current_claim_id, step.status, run.status, current) == (
        TaskAttemptStatus.OUTCOME_UNKNOWN,
        None,
        WorkflowStepStatus.WAITING,
        WorkflowRunStatus.WAITING,
        None,
    )
    assert step.completed_at is None and run.completed_at is None


class _SyncFailureRepository(SQLiteWorkflowRepository):
    """Test-only seam that simulates a crash after child mutation before commit."""

    async def _sync_lifecycle(self, uow: object, workflow_step_id: str, now: datetime) -> None:
        raise RuntimeError("synthetic aggregate sync failure")


async def test_aggregate_sync_failure_rolls_back_attempt_claim_step_and_run(
    workflow_runtime,
) -> None:
    """Would fail if aggregate synchronization could commit a partial retry transition."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    failing_kernel = WorkflowKernel(
        factory,
        repository=_SyncFailureRepository(factory),
        clock=kernel._clock,
    )
    with pytest.raises(RuntimeError, match="synthetic aggregate sync failure"):
        await failing_kernel.fail_or_retry(
            claim, RetryFailure("transient_failure", "synthetic.retry", 1), now
        )
    attempt, step, run, current = await _records(factory, claim.task_attempt_id)
    assert (attempt.status, attempt.current_claim_id, step.status, run.status) == (
        TaskAttemptStatus.RUNNING,
        claim.id,
        WorkflowStepStatus.RUNNING,
        WorkflowRunStatus.RUNNING,
    )
    assert current is not None
    assert (current.status, current.fencing_token, current.lease_expires_at) == (
        "active",
        claim.fencing_token,
        claim.lease_expires_at,
    )


@pytest.mark.parametrize("backoff_seconds", [True, 0, -1, 3601])
async def test_recovery_rejects_invalid_bounded_backoff_seconds(
    workflow_runtime, backoff_seconds: object
) -> None:
    """Would fail if recovery scheduling accepted unbounded or boolean delay input."""
    kernel, _ = workflow_runtime
    with pytest.raises(ValueError, match="recovery_backoff_seconds"):
        await kernel.reconcile(
            datetime(2030, 1, 1), recovery_backoff_seconds=backoff_seconds  # type: ignore[arg-type]
        )


async def test_poisoned_expired_claim_is_deferred_without_starving_later_recovery(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Would fail if one bad expired record repeatedly monopolized bounded recovery pages."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, poison = await start_and_claim(kernel, now=now)
    _, later = await start_and_claim(kernel, now=now)
    original = kernel._repository._reconcile_one_expired_claim
    calls: list[str] = []

    async def poison_one(claim_id: str, operation_now: datetime) -> bool:
        calls.append(claim_id)
        if claim_id == poison.id:
            raise RuntimeError("untrusted exception detail must not persist")
        return await original(claim_id, operation_now)

    monkeypatch.setattr(kernel._repository, "_reconcile_one_expired_claim", poison_one)
    expiry = poison.lease_expires_at
    assert later.lease_expires_at == expiry
    assert await kernel.reconcile(expiry, batch_size=2, recovery_backoff_seconds=10) == 1
    async with factory.session_factory() as session:
        deferred_claim = await session.get(ExecutionClaimRecord, poison.id)
        recovered_attempt = await session.get(TaskAttemptRecord, later.task_attempt_id)
    assert deferred_claim is not None
    assert deferred_claim.status == "active"
    assert deferred_claim.lease_expires_at == expiry
    assert deferred_claim.recovery_failure_count == 1
    assert deferred_claim.recovery_not_before == expiry + timedelta(seconds=10)
    assert deferred_claim.last_recovery_error_code == "recovery_failed"
    assert recovered_attempt is not None and recovered_attempt.status == TaskAttemptStatus.PENDING
    assert await kernel._repository.finalize(poison, {"result_ref": "stale"}, expiry) is False
    assert await kernel.reconcile(expiry, batch_size=2, recovery_backoff_seconds=10) == 0
    assert calls.count(poison.id) == 1
    assert await kernel.reconcile(
        expiry + timedelta(seconds=10), batch_size=2, recovery_backoff_seconds=10
    ) == 0
    assert calls.count(poison.id) == 2
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "recovery_failed" in messages
    assert poison.id in messages
    assert "untrusted exception detail" not in messages
