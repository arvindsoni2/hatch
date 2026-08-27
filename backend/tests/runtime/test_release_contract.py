"""Release-level workflow ownership and lifecycle contracts (synthetic SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _claim_by_id(factory, claim_id: str) -> ExecutionClaimRecord:
    """Read the original ownership record, even after it stops being current."""
    async with factory.session_factory() as session:
        claim = await session.get(ExecutionClaimRecord, claim_id)
    assert claim is not None
    return claim


def _lifecycle_snapshot(attempt, step, run, claim):
    """Capture every lifecycle-bearing value for rollback/proof comparisons."""
    attempt_fields = (
        "id", "status", "waiting_reason", "not_before", "retry_reason",
        "retry_policy_id", "retry_policy_version", "claim_fencing_token",
        "current_claim_id", "result_ref_json", "failure_code", "started_at",
        "finished_at", "prior_attempt_id", "attempt_number",
    )
    step_fields = ("id", "status", "waiting_reason", "completed_at", "failure_code", "updated_at")
    run_fields = ("id", "status", "completed_at", "result_ref_json", "failure_code", "updated_at")
    claim_fields = (
        "id", "status", "released_at", "claimed_at", "claimed_by",
        "lease_expires_at", "fencing_token", "task_attempt_id", "purpose",
        "recovery_not_before", "recovery_failure_count", "last_recovery_error_code",
    )
    return {
        "attempt": {field: getattr(attempt, field) for field in attempt_fields},
        "step": {field: getattr(step, field) for field in step_fields},
        "run": {field: getattr(run, field) for field in run_fields},
        "claim": None if claim is None else {field: getattr(claim, field) for field in claim_fields},
    }


async def _scoped_counts(factory, step_id: str):
    async with factory.session_factory() as session:
        attempts = list((await session.scalars(
            select(TaskAttemptRecord).where(TaskAttemptRecord.workflow_step_id == step_id)
        )).all())
        attempt_ids = [item.id for item in attempts]
        claims = []
        if attempt_ids:
            claims = list((await session.scalars(
                select(ExecutionClaimRecord).where(ExecutionClaimRecord.task_attempt_id.in_(attempt_ids))
            )).all())
    return len(attempts), len(claims)


async def _assert_original_claim_lifecycle(
    factory,
    original: ExecutionClaimRecord,
    *,
    status: str,
    released_at: datetime,
) -> None:
    """Assert terminal ownership facts independently of the current attempt link."""
    persisted = await _claim_by_id(factory, original.id)
    assert (persisted.status, persisted.released_at) == (status, released_at)
    assert persisted.lease_expires_at == original.lease_expires_at
    assert persisted.fencing_token == original.fencing_token


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
    await _assert_original_claim_lifecycle(
        factory, first, status="released", released_at=now
    )
    attempt, step, run, claim = await _records(factory, first.task_attempt_id)
    assert (attempt.status, step.status, run.status, claim) == (
        TaskAttemptStatus.WAITING, WorkflowStepStatus.WAITING, WorkflowRunStatus.WAITING, None
    )
    assert await kernel.resume_waiting(attempt.id, now)
    second = await kernel.claim_next("worker-b", now)
    assert second is not None
    retry = await kernel.fail_or_retry(second, RetryFailure("transient_failure", "synthetic.retry", 1), now)
    assert retry is not None
    await _assert_original_claim_lifecycle(
        factory, second, status="released", released_at=now
    )
    prior, step, run, prior_claim = await _records(factory, second.task_attempt_id)
    assert prior.current_claim_id is None and prior_claim is None
    assert (prior.status, step.status, run.status) == (
        TaskAttemptStatus.FAILED, WorkflowStepStatus.PENDING, WorkflowRunStatus.PENDING
    )
    third = await kernel.claim_next("worker-c", now)
    assert third is not None and third.task_attempt_id == retry.id
    assert await kernel.finalize(third, {"result_ref": "synthetic-result"}, now=now)
    await _assert_original_claim_lifecycle(
        factory, third, status="released", released_at=now
    )
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
    await _assert_original_claim_lifecycle(
        factory, first, status="released", released_at=now
    )
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
    await _assert_original_claim_lifecycle(
        factory, second, status="released", released_at=due_at
    )
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
    await _assert_original_claim_lifecycle(
        factory, first, status="released", released_at=now
    )
    await _assert_original_claim_lifecycle(
        factory, second, status="released", released_at=now
    )
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
    await _assert_original_claim_lifecycle(
        factory,
        explicit,
        status="released",
        released_at=now + timedelta(seconds=1),
    )
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
    await _assert_original_claim_lifecycle(
        factory,
        execution_claim,
        status="expired",
        released_at=execution_claim.lease_expires_at,
    )
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
    await _assert_original_claim_lifecycle(
        factory,
        external_claim,
        status="released",
        released_at=now + timedelta(seconds=1),
    )
    recon_claim = await kernel.claim_outcome_unknown(
        external_claim.task_attempt_id, "reconciler", now + timedelta(seconds=1)
    )
    assert recon_claim is not None
    assert await kernel.reconcile(recon_claim.lease_expires_at) == 1
    await _assert_original_claim_lifecycle(
        factory,
        recon_claim,
        status="expired",
        released_at=recon_claim.lease_expires_at,
    )
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
    before_attempt, before_step, before_run, before_current = await _records(
        factory, claim.task_attempt_id
    )
    assert before_current is not None
    before = _lifecycle_snapshot(before_attempt, before_step, before_run, before_current)
    before_counts = await _scoped_counts(factory, before_step.id)
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
    assert _lifecycle_snapshot(attempt, step, run, current) == before
    assert await _scoped_counts(factory, step.id) == before_counts


async def test_deferred_outcome_unknown_reconciliation_claim_blocks_alternate_owner_until_due(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deferred reconciliation owner retains OUTCOME_UNKNOWN until durable reclaim is due."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, execution = await start_and_claim(kernel, now=now)
    assert await kernel.mark_outcome_unknown(
        execution, now, capability_id="synthetic.check", capability_version=1,
        idempotency_class="check_before_retry", reconciliation_reference="synthetic.ref",
    )
    recon = await kernel.claim_outcome_unknown(execution.task_attempt_id, "reconciler-a", now)
    assert recon is not None
    expiry = recon.lease_expires_at
    poison = kernel._repository._reconcile_one_expired_claim

    poisoned = False

    async def fail_recovery(claim_id: str, operation_now: datetime) -> bool:
        nonlocal poisoned
        if claim_id == recon.id and not poisoned:
            poisoned = True
            raise RuntimeError("synthetic reconciliation poison")
        return await poison(claim_id, operation_now)

    monkeypatch.setattr(kernel._repository, "_reconcile_one_expired_claim", fail_recovery)
    assert await kernel.reconcile(expiry, recovery_backoff_seconds=10) == 0
    deferred = await _claim_by_id(factory, recon.id)
    assert deferred.recovery_not_before == expiry + timedelta(seconds=10)
    attempt, step, run, current = await _records(factory, execution.task_attempt_id)
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert attempt.current_claim_id == recon.id
    assert current is not None and current.id == recon.id and current.fencing_token == recon.fencing_token
    assert await kernel.claim_outcome_unknown(execution.task_attempt_id, "reconciler-b", expiry + timedelta(seconds=1)) is None
    assert await kernel._repository.finalize(recon, {"result_ref": "stale"}, expiry + timedelta(seconds=1)) is False
    assert await kernel.fail_terminal(recon, "stale_failure", expiry + timedelta(seconds=1)) is False

    due = expiry + timedelta(seconds=10)
    assert await kernel.reconcile(due) == 1
    recovered = await _claim_by_id(factory, recon.id)
    assert recovered.status == "expired" and recovered.released_at == due
    attempt, step, run, current = await _records(factory, execution.task_attempt_id)
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN and attempt.current_claim_id is None
    assert current is None and step.status == WorkflowStepStatus.WAITING and run.status == WorkflowRunStatus.WAITING
    replacement = await kernel.claim_outcome_unknown(execution.task_attempt_id, "reconciler-c", due)
    assert replacement is not None and replacement.fencing_token > recon.fencing_token


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


async def test_stale_reclaim_selection_cannot_bypass_a_committed_recovery_deferral(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Would fail if reclaim trusted selection instead of its final durable CAS."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, original = await start_and_claim(kernel, now=now)
    recovery_not_before = original.lease_expires_at + timedelta(seconds=10)
    original_scalar = AsyncSession.scalar
    deferred = False

    async def select_then_commit_deferral(
        session: AsyncSession, statement: object, *args: object, **kwargs: object
    ) -> object:
        nonlocal deferred
        selected = await original_scalar(session, statement, *args, **kwargs)
        if not deferred and selected is not None:
            deferred = True
            await session.execute(
                update(ExecutionClaimRecord)
                .where(ExecutionClaimRecord.id == original.id)
                .values(recovery_not_before=recovery_not_before)
            )
            # Model another transaction committing after selection and before CAS.
            await session.commit()
        return selected

    monkeypatch.setattr(AsyncSession, "scalar", select_then_commit_deferral)
    reclaimed = await kernel.reclaim(
        original.task_attempt_id, "stale-reclaimer", original.lease_expires_at
    )

    assert reclaimed is None
    attempt, step, run, current = await _records(factory, original.task_attempt_id)
    assert (attempt.status, attempt.current_claim_id, step.status, run.status) == (
        TaskAttemptStatus.RUNNING,
        original.id,
        WorkflowStepStatus.RUNNING,
        WorkflowRunStatus.RUNNING,
    )
    assert current is not None and current.id == original.id
    persisted = await _claim_by_id(factory, original.id)
    assert persisted.recovery_not_before == recovery_not_before
    assert persisted.lease_expires_at == original.lease_expires_at
    assert persisted.fencing_token == original.fencing_token


async def test_stale_recovery_selection_cannot_mutate_after_a_committed_deferral(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Would fail if recovery's CAS did not recheck recovery_not_before."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, original = await start_and_claim(kernel, now=now)
    expiry = original.lease_expires_at
    recovery_not_before = expiry + timedelta(seconds=10)
    original_get = AsyncSession.get
    deferred = False

    async def select_then_commit_deferral(
        session: AsyncSession, entity: object, ident: object, *args: object, **kwargs: object
    ) -> object:
        nonlocal deferred
        selected = await original_get(session, entity, ident, *args, **kwargs)
        if entity is ExecutionClaimRecord and ident == original.id and not deferred:
            deferred = True
            await session.execute(
                update(ExecutionClaimRecord)
                .where(ExecutionClaimRecord.id == original.id)
                .values(recovery_not_before=recovery_not_before)
            )
            # Model another transaction committing after page selection and before CAS.
            await session.commit()
        return selected

    monkeypatch.setattr(AsyncSession, "get", select_then_commit_deferral)
    assert await kernel._repository._reconcile_one_expired_claim(original.id, expiry) is False

    attempt, step, run, current = await _records(factory, original.task_attempt_id)
    assert (attempt.status, attempt.current_claim_id, step.status, run.status) == (
        TaskAttemptStatus.RUNNING,
        original.id,
        WorkflowStepStatus.RUNNING,
        WorkflowRunStatus.RUNNING,
    )
    assert current is not None and current.id == original.id
    persisted = await _claim_by_id(factory, original.id)
    assert persisted.recovery_not_before == recovery_not_before
    assert persisted.lease_expires_at == original.lease_expires_at
    assert persisted.fencing_token == original.fencing_token


async def test_deferred_first_page_claim_does_not_starve_later_recovery_or_reopen_before_due(
    workflow_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Would fail if a poisoned recovery could monopolize batch one or reopen early."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    _, poison = await start_and_claim(kernel, now=now)
    _, later = await start_and_claim(kernel, now=now + timedelta(seconds=1))
    recovery_now = later.lease_expires_at
    due_at = recovery_now + timedelta(seconds=10)
    original_reconcile = kernel._repository._reconcile_one_expired_claim
    poison_failures = 0

    async def fail_poison_once(claim_id: str, operation_now: datetime) -> bool:
        nonlocal poison_failures
        if claim_id == poison.id and poison_failures == 0:
            poison_failures += 1
            raise RuntimeError("synthetic poison")
        return await original_reconcile(claim_id, operation_now)

    monkeypatch.setattr(
        kernel._repository, "_reconcile_one_expired_claim", fail_poison_once
    )
    assert await kernel.reconcile(
        recovery_now, batch_size=1, recovery_backoff_seconds=10
    ) == 0
    deferred = await _claim_by_id(factory, poison.id)
    assert (deferred.status, deferred.recovery_not_before) == ("active", due_at)
    assert deferred.lease_expires_at == poison.lease_expires_at
    assert deferred.fencing_token == poison.fencing_token

    before_due = recovery_now + timedelta(microseconds=1)
    assert await kernel.reclaim(poison.task_attempt_id, "public-reclaimer", before_due) is None
    assert await kernel.claim_outcome_unknown(
        poison.task_attempt_id, "reconciler", before_due
    ) is None
    assert await kernel._repository.finalize(poison, {"result_ref": "stale"}, before_due) is False

    assert await kernel.reconcile(
        before_due, batch_size=1, recovery_backoff_seconds=10
    ) == 1
    later_claim = await _claim_by_id(factory, later.id)
    assert (later_claim.status, later_claim.released_at) == ("expired", before_due)
    later_attempt, later_step, later_run, later_current = await _records(
        factory, later.task_attempt_id
    )
    assert (later_attempt.status, later_attempt.current_claim_id, later_step.status, later_run.status) == (
        TaskAttemptStatus.PENDING,
        None,
        WorkflowStepStatus.PENDING,
        WorkflowRunStatus.PENDING,
    )
    assert later_current is None

    assert await kernel.reconcile(
        before_due, batch_size=1, recovery_backoff_seconds=10
    ) == 0
    assert await kernel.reconcile(due_at, batch_size=1, recovery_backoff_seconds=10) == 1
    recovered = await _claim_by_id(factory, poison.id)
    assert (recovered.status, recovered.released_at) == ("expired", due_at)
    assert recovered.lease_expires_at == poison.lease_expires_at
    assert recovered.fencing_token == poison.fencing_token
