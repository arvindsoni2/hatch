"""Claim eligibility and durable ownership tests with synthetic SQLite data."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
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
from app.runtime.workflow.models import TaskAttemptStatus


class _Input(BaseModel):
    ref: str


class _Output(BaseModel):
    ref: str


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


@pytest_asyncio.fixture
async def kernel(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'claims.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
            clock=_Clock(datetime(2030, 1, 2)),
        )
    finally:
        await engine.dispose()


@pytest.fixture
def spec() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="synthetic.claim",
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


async def test_claim_requires_a_due_pending_attempt(kernel, spec) -> None:
    now = datetime(2030, 1, 1)
    assert await kernel.claim_next("worker-a", now) is None

    await kernel.start_run(
        spec,
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_id": "synthetic-domain", "domain_type": "synthetic"},
        mode="new",
    )

    claim = await kernel.claim_next("worker-a", now)
    assert claim is not None
    assert claim.claimed_by == "worker-a"
    assert claim.fencing_token == 1
    assert claim.lease_expires_at == now + timedelta(seconds=30)
    assert await kernel.claim_next("worker-b", now) is None


async def test_claim_rejects_an_empty_worker_id(kernel) -> None:
    with pytest.raises(ValueError, match="worker_id"):
        await kernel.claim_next("", datetime(2030, 1, 1))


async def test_start_run_rejects_unknown_runtime_mode(kernel, spec) -> None:
    with pytest.raises(ValueError, match="runtime mode"):
        await kernel.start_run(
            spec,
            input_ref={"input_ref": "synthetic-input"},
            domain_ref={"domain_id": "invalid-mode", "domain_type": "synthetic"},
            mode="unsupported",
        )
    assert await kernel.claim_next("worker-a", datetime(2030, 1, 1)) is None


async def test_invalid_result_does_not_consume_the_claim(kernel, spec) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        spec,
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_id": "synthetic-failure", "domain_type": "synthetic"},
        mode="new",
    )
    claim = await kernel.claim_next("worker-a", now)
    assert claim is not None

    with pytest.raises(ValueError, match="result"):
        await kernel.finalize(claim, {})

    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.RUNNING
    assert await kernel.finalize(claim, {"result_ref": "safe-reference"}) is True


async def test_finalize_uses_the_injected_monotonic_clock(kernel, spec) -> None:
    started_at = datetime(2030, 1, 1, 12, 0, 0)
    finished_at = started_at + timedelta(seconds=7)
    clock = _Clock(finished_at)
    clock_kernel = WorkflowKernel(
        kernel._uow_factory,
        lease_duration=timedelta(seconds=30),
        clock=clock,
    )
    await clock_kernel.start_run(
        spec,
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_id": "clock", "domain_type": "synthetic"},
        mode="new",
    )
    claim = await clock_kernel.claim_next("worker-a", started_at)
    assert claim is not None

    assert await clock_kernel.finalize(claim, {"result_ref": "safe-reference"})
    attempt = await clock_kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.started_at == started_at
    assert attempt.finished_at == finished_at
    assert attempt.finished_at >= attempt.started_at
