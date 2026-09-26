"""Atomic state/event/outbox invariants for the runtime UoW."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.events.models import RuntimeEventRecord, RuntimeOutboxRecord
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.models import WorkflowRunRecord


@pytest_asyncio.fixture
async def runtime_uow_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SQLiteRuntimeUnitOfWorkFactory(session_factory)
    finally:
        await engine.dispose()


async def _counts(factory) -> tuple[int, int, int]:
    async with factory.session_factory() as session:
        return (
            await session.scalar(select(func.count()).select_from(WorkflowRunRecord)),
            await session.scalar(select(func.count()).select_from(RuntimeEventRecord)),
            await session.scalar(select(func.count()).select_from(RuntimeOutboxRecord)),
        )


async def test_state_event_and_outbox_commit_together(runtime_uow_factory) -> None:
    async with runtime_uow_factory.transaction() as uow:
        run = await uow.workflows.create_run(
            workflow_definition_id="synthetic.workflow",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="new",
        )
        event = await uow.events.append(
            event_type="runtime.run_created",
            event_version=1,
            aggregate_type="workflow_run",
            aggregate_id=run.id,
            workflow_run_id=run.id,
            actor_type="system",
            payload_json={"reason_code": "created"},
            sensitivity="metadata",
        )
        await uow.outbox.enqueue(event.id, "runtime.telemetry")
        await uow.commit()

    assert await _counts(runtime_uow_factory) == (1, 1, 1)


@pytest.mark.parametrize("failure_point", ["state", "event", "outbox"])
async def test_state_event_outbox_roll_back_together(
    runtime_uow_factory, failure_point: str
) -> None:
    class InjectedFailure(RuntimeError):
        pass

    with pytest.raises(InjectedFailure):
        async with runtime_uow_factory.transaction() as uow:
            run = await uow.workflows.create_run(
                workflow_definition_id="synthetic.workflow",
                workflow_definition_version=1,
                domain_type="synthetic",
                runtime_mode="new",
            )
            if failure_point == "state":
                raise InjectedFailure
            event = await uow.events.append(
                event_type="runtime.run_created",
                event_version=1,
                aggregate_type="workflow_run",
                aggregate_id=run.id,
                workflow_run_id=run.id,
                actor_type="system",
                payload_json={"reason_code": "created"},
                sensitivity="metadata",
            )
            if failure_point == "event":
                raise InjectedFailure
            await uow.outbox.enqueue(event.id, "runtime.telemetry")
            raise InjectedFailure

    assert await _counts(runtime_uow_factory) == (0, 0, 0)
