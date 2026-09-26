"""Restart recovery proves the database, not process memory, owns recovery."""

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
from app.runtime.workflow.kernel import InjectedFailure, WorkflowKernel


class _Input(BaseModel):
    ref: str


class _Output(BaseModel):
    ref: str


def _spec() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="synthetic.restart",
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
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def _build(*, fail_after: str | None = None) -> WorkflowKernel:
        return WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
            worker_id="recovery-worker",
            fail_after=fail_after,
        )

    try:
        yield _build
    finally:
        await engine.dispose()


async def test_crash_after_claim_recovers_from_database(kernel_factory) -> None:
    now = datetime(2030, 1, 1)
    first = kernel_factory(fail_after="claim_commit")
    await first.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "restart"},
        mode="new",
    )

    with pytest.raises(InjectedFailure, match="claim_commit"):
        await first.run_once(now)

    second = kernel_factory()
    assert await second.reconcile(now + timedelta(seconds=30)) == 1
    recovered = await second.claim_next("new-process-worker", now + timedelta(seconds=30))
    assert recovered is not None
    assert recovered.fencing_token == 2
