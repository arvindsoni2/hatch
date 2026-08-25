"""Bounded SQLite claim contention with one AsyncSession per worker."""

from __future__ import annotations

import asyncio
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


def _spec() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="synthetic.contention",
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


@pytest_asyncio.fixture
async def kernel_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'contention.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def _build() -> WorkflowKernel:
        return WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
            lock_retry_attempts=3,
        )

    try:
        yield _build
    finally:
        await engine.dispose()


async def test_concurrent_workers_claim_once_with_separate_sessions(kernel_factory) -> None:
    now = datetime(2030, 1, 1)
    initializer = kernel_factory()
    await initializer.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "contention"},
        mode="new",
    )
    barrier = asyncio.Barrier(3)

    async def claim(worker_id: str):
        await barrier.wait()
        return await kernel_factory().claim_next(worker_id, now)

    claims = await asyncio.gather(
        claim("worker-a"), claim("worker-b"), claim("worker-c")
    )
    acquired = [claim for claim in claims if claim is not None]
    assert len(acquired) == 1
    assert acquired[0].fencing_token == 1
