"""Immutable retry and durable backoff tests with a deterministic clock value."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest_asyncio
from pydantic import BaseModel
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
from app.runtime.workflow.models import TaskAttemptStatus, WaitingReason
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
