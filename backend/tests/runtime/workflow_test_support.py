"""Synthetic, isolated fixtures shared by workflow-kernel contract tests."""

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


class SyntheticInput(BaseModel):
    ref: str


class SyntheticOutput(BaseModel):
    ref: str


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2031, 1, 1)


def synthetic_spec(*, max_attempts: int = 2) -> TaskSpec[SyntheticInput, SyntheticOutput]:
    return TaskSpec(
        task_id="synthetic.workflow",
        version=1,
        input_model=SyntheticInput,
        output_model=SyntheticOutput,
        context_requirements=(),
        model_requirements=ModelCapabilityRequirements(),
        risk_class=RiskClass.LOW,
        validators=("synthetic.validator",),
        evaluation_policy=EvaluationPolicy(),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=max_attempts),
    )


@pytest_asyncio.fixture
async def workflow_runtime(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-contracts.db'}",
        connect_args={"timeout": 5},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = SQLiteRuntimeUnitOfWorkFactory(session_factory)
    kernel = WorkflowKernel(
        factory, lease_duration=timedelta(seconds=30), clock=_FixedClock()
    )
    try:
        yield kernel, factory
    finally:
        await engine.dispose()


async def start_and_claim(kernel: WorkflowKernel, *, now: datetime, max_attempts: int = 2):
    run = await kernel.start_run(
        synthetic_spec(max_attempts=max_attempts),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "workflow-contract"},
        mode="new",
    )
    claim = await kernel.claim_next("worker-a", now)
    assert claim is not None
    return run, claim
