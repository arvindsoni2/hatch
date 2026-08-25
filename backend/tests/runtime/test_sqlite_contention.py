"""Bounded SQLite claim contention with one AsyncSession per worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
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
from app.runtime.workflow.repository import SQLiteWorkflowRepository


class _Input(BaseModel):
    ref: str


class _Output(BaseModel):
    ref: str


class _LockFailingRepository:
    def __init__(self, delegate: SQLiteWorkflowRepository, failures: int) -> None:
        self._delegate = delegate
        self._failures = failures
        self.claim_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def claim_next(self, *args: Any, **kwargs: Any) -> Any:
        self.claim_calls += 1
        if self.claim_calls <= self._failures:
            raise OperationalError("UPDATE", {}, RuntimeError("database is locked"))
        return await self._delegate.claim_next(*args, **kwargs)


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

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=50")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def _build(
        *,
        repository: SQLiteWorkflowRepository | None = None,
        lock_retry_attempts: int = 3,
        lock_wait=None,
    ) -> WorkflowKernel:
        return WorkflowKernel(
            SQLiteRuntimeUnitOfWorkFactory(session_factory),
            lease_duration=timedelta(seconds=30),
            lock_retry_attempts=lock_retry_attempts,
            repository=repository,
            lock_wait=lock_wait,
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


async def test_claim_retries_deterministic_sqlite_lock_failures(kernel_factory) -> None:
    waits: list[float] = []

    async def wait(delay: float) -> None:
        waits.append(delay)

    faulting = _LockFailingRepository(
        SQLiteWorkflowRepository(kernel_factory()._uow_factory), failures=2
    )
    kernel = kernel_factory(repository=faulting, lock_wait=wait)
    now = datetime(2030, 1, 1)
    await kernel.start_run(
        _spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "retry-lock"},
        mode="new",
    )

    assert await kernel.claim_next("worker-a", now) is not None
    assert faulting.claim_calls == 3
    assert waits == [0.005, 0.01]


async def test_claim_reraises_at_the_configured_lock_retry_limit(kernel_factory) -> None:
    waits: list[float] = []

    async def wait(delay: float) -> None:
        waits.append(delay)

    faulting = _LockFailingRepository(
        SQLiteWorkflowRepository(kernel_factory()._uow_factory), failures=3
    )
    kernel = kernel_factory(
        repository=faulting, lock_wait=wait, lock_retry_attempts=3
    )

    with pytest.raises(OperationalError, match="database is locked"):
        await kernel.claim_next("worker-a", datetime(2030, 1, 1))
    assert faulting.claim_calls == 3
    assert waits == [0.005, 0.01]
