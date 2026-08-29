"""Immutable retry and durable backoff tests with a deterministic clock value."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.contracts.enums import ExecutionStrategy, RiskClass
from app.runtime.contracts.task_spec import (
    EvaluationPolicy,
    ModelCapabilityRequirements,
    TaskSpec,
    WorkflowPolicy,
)
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.kernel import WorkflowKernel
from app.runtime.workflow.models import TaskAttemptRecord, TaskAttemptStatus, WaitingReason
from app.runtime.workflow.retry import RetryFailure


class _Input(BaseModel):
    ref: str


class _Output(BaseModel):
    ref: str


@pytest_asyncio.fixture
async def kernel(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retries.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
        )
    finally:
        await engine.dispose()


def _spec() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="synthetic.retry",
        version=1,
        input_model=_Input,
        output_model=_Output,
        context_requirements=(),
        model_requirements=ModelCapabilityRequirements(),
        risk_class=RiskClass.LOW,
        validators=("synthetic.validator",),
        evaluation_policy=EvaluationPolicy(),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=2),
    )


async def test_retry_creates_an_immutable_waiting_attempt(kernel) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "retry"},
        mode="new",
    )
    first_claim = await kernel.claim_next("worker-a", now)
    assert first_claim is not None

    retry_at = now + timedelta(minutes=5)
    second = await kernel.fail_or_retry(
        first_claim,
        RetryFailure(
            reason="transient_failure",
            policy_id="synthetic.backoff",
            policy_version=1,
            retry_after=timedelta(minutes=5),
        ),
        now,
    )
    assert second is not None
    first = await kernel.get_attempt(first_claim.task_attempt_id)
    assert first is not None
    assert first.status == TaskAttemptStatus.FAILED
    assert first.finished_at == now
    assert second.attempt_number == 2
    assert second.prior_attempt_id == first.id
    assert second.status == TaskAttemptStatus.WAITING
    assert second.waiting_reason == WaitingReason.RETRY_TIME
    assert second.not_before == retry_at
    assert second.retry_reason == "transient_failure"
    assert second.retry_policy_id == "synthetic.backoff"
    assert second.retry_policy_version == 1

    assert await kernel.claim_next("worker-b", retry_at - timedelta(microseconds=1)) is None
    promoted = await kernel.claim_next("worker-b", retry_at)
    assert promoted is not None
    assert promoted.task_attempt_id == second.id


async def test_stale_worker_cannot_create_a_retry(kernel) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "retry-stale"},
        mode="new",
    )
    claim_a = await kernel.claim_next("worker-a", now)
    assert claim_a is not None
    claim_b = await kernel.reclaim(
        claim_a.task_attempt_id, "worker-b", claim_a.lease_expires_at
    )
    assert claim_b is not None

    assert (
        await kernel.fail_or_retry(
            claim_a,
            RetryFailure("transient_failure", "synthetic.backoff", 1),
            claim_a.lease_expires_at,
        )
        is None
    )


async def test_retry_budget_makes_attempt_two_terminal_without_attempt_three(
    kernel,
) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "retry-budget"},
        mode="new",
    )
    first_claim = await kernel.claim_next("worker-a", now)
    assert first_claim is not None
    second = await kernel.fail_or_retry(
        first_claim,
        RetryFailure("transient_failure", "synthetic.backoff", 1),
        now,
    )
    assert second is not None
    restarted_kernel = WorkflowKernel(kernel._uow_factory)
    second_claim = await restarted_kernel.claim_next("worker-b", now)
    assert second_claim is not None
    assert second_claim.task_attempt_id == second.id

    assert (
        await restarted_kernel.fail_or_retry(
            second_claim,
            RetryFailure("transient_failure", "synthetic.backoff", 1),
            now,
        )
        is None
    )
    persisted_second = await restarted_kernel.get_attempt(second.id)
    assert persisted_second is not None
    assert persisted_second.status == TaskAttemptStatus.FAILED
    assert await restarted_kernel.claim_next("worker-c", now) is None

    async with kernel._uow_factory.session_factory() as session:
        attempt_count = await session.scalar(
            select(func.count())
            .select_from(TaskAttemptRecord)
            .where(TaskAttemptRecord.workflow_step_id == second.workflow_step_id)
        )
    assert attempt_count == 2


async def test_repository_rejects_retry_metadata_that_bypasses_the_kernel(kernel) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "retry-bypass"},
        mode="new",
    )
    claim = await kernel.claim_next("worker-a", now)
    assert claim is not None

    with pytest.raises(ValueError, match="stable code"):
        await kernel._repository.fail_or_retry(
            claim,
            reason="prompt: synthetic-canary",
            policy_id="synthetic.backoff",
            policy_version=1,
            not_before=None,
            now=now,
        )
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.RUNNING


@pytest.mark.parametrize(
    ("reason", "policy_id", "policy_version"),
    [
        (" ", "synthetic.backoff", 1),
        ("transient_failure", " ", 1),
        ("/tmp/synthetic-canary", "synthetic.backoff", 1),
        ("transient_failure", "prompt: synthetic-canary", 1),
        ("x" * 129, "synthetic.backoff", 1),
        ("transient_failure", "synthetic.backoff", True),
    ],
)
def test_retry_failure_rejects_unbounded_or_sensitive_metadata(
    reason: str, policy_id: str, policy_version: int
) -> None:
    with pytest.raises(ValueError):
        RetryFailure(reason, policy_id, policy_version)


def test_retry_failure_normalizes_stable_metadata_at_the_length_boundary() -> None:
    failure = RetryFailure(" synthetic.retry ", " synthetic.backoff ", 1)
    assert failure.reason == "synthetic.retry"
    assert failure.policy_id == "synthetic.backoff"
    assert RetryFailure("a" * 128, "b" * 128, 1).reason == "a" * 128
