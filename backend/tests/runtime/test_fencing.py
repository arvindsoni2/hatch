"""Fencing and lease ownership tests using only synthetic references."""

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


class _Input(BaseModel):
    ref: str


class _Output(BaseModel):
    ref: str


class _Clock:
    def now(self) -> datetime:
        return datetime(2030, 1, 1, 0, 0, 30)


@pytest_asyncio.fixture
async def kernel(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fencing.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
            clock=_Clock(),
        )
    finally:
        await engine.dispose()


def _spec() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="synthetic.fencing",
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


async def test_stale_finalizer_cannot_overwrite_new_owner(kernel) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "fencing"},
        mode="new",
    )
    claim_a = await kernel.claim_next("worker-a", now)
    assert claim_a is not None

    claim_b = await kernel.reclaim(
        claim_a.task_attempt_id, "worker-b", claim_a.lease_expires_at
    )
    assert claim_b is not None
    assert claim_b.fencing_token > claim_a.fencing_token
    assert await kernel.finalize(claim_b, {"result_ref": "B"}) is True
    assert await kernel.finalize(claim_a, {"result_ref": "A"}) is False

    attempt = await kernel.get_attempt(claim_a.task_attempt_id)
    assert attempt is not None
    assert attempt.result_ref_json == {"result_ref": "B"}


async def test_lost_claim_cannot_be_renewed(kernel) -> None:
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "renew"},
        mode="new",
    )
    claim_a = await kernel.claim_next("worker-a", now)
    assert claim_a is not None
    claim_b = await kernel.reclaim(
        claim_a.task_attempt_id, "worker-b", claim_a.lease_expires_at
    )
    assert claim_b is not None

    assert await kernel.renew_claim(claim_a, claim_a.lease_expires_at) is False
    assert await kernel.renew_claim(claim_b, claim_b.claimed_at) is True
