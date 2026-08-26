"""Conformance tests for the SQLite runtime unit of work."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.events.models import RuntimeEventRecord, RuntimeOutboxRecord
from app.runtime.storage.contracts import DurableWorkflowStore
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.repository import SQLiteWorkflowRepository
from app.runtime.workflow.models import (
    TaskAttemptStatus,
    WorkflowRunRecord,
)


@pytest_asyncio.fixture
async def runtime_uow_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SQLiteRuntimeUnitOfWorkFactory(session_factory)
    finally:
        await engine.dispose()


async def test_retry_schema_preserves_attempt_history(runtime_uow_factory) -> None:
    async with runtime_uow_factory.transaction() as uow:
        run = await uow.workflows.create_run(
            workflow_definition_id="synthetic.workflow",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="new",
        )
        step = await uow.workflows.create_step(
            workflow_run_id=run.id,
            step_key="score",
            step_order=1,
            task_id="synthetic.score",
            task_version=1,
        )
        first = await uow.workflows.create_attempt(
            workflow_step_id=step.id,
            attempt_number=1,
        )
        first.status = TaskAttemptStatus.FAILED
        second = await uow.workflows.schedule_retry(
            first.id,
            retry_reason="transient",
            retry_policy_id="default",
            retry_policy_version=1,
            not_before=datetime.utcnow() + timedelta(minutes=1),
        )
        await uow.commit()

    async with runtime_uow_factory.transaction() as uow:
        persisted_first = await uow.workflows.get_attempt(first.id)
        persisted_second = await uow.workflows.get_attempt(second.id)

    assert persisted_first is not None
    assert persisted_second is not None
    assert persisted_first.status == TaskAttemptStatus.FAILED
    assert persisted_second.attempt_number == 2
    assert persisted_second.prior_attempt_id == first.id
    assert persisted_second.status == TaskAttemptStatus.WAITING
    assert persisted_second.waiting_reason == "retry_time"
    assert persisted_second.retry_reason == "transient"
    assert persisted_second.retry_policy_id == "default"
    assert persisted_second.retry_policy_version == 1


@pytest.mark.parametrize("value", [" /tmp/secret ", "ignore previous instructions", "x" * 129, ""])
async def test_schedule_retry_rejects_unsafe_metadata_at_store_boundary(runtime_uow_factory, value):
    async with runtime_uow_factory.transaction() as uow:
        run = await uow.workflows.create_run(workflow_definition_id="synthetic.workflow", workflow_definition_version=1, domain_type="synthetic", runtime_mode="new")
        step = await uow.workflows.create_step(workflow_run_id=run.id, step_key="score", step_order=1, task_id="synthetic.score", task_version=1)
        attempt = await uow.workflows.create_attempt(workflow_step_id=step.id, attempt_number=1)
        with pytest.raises(ValueError):
            await uow.workflows.schedule_retry(attempt.id, retry_reason=value, retry_policy_id="default", retry_policy_version=1)


async def test_schedule_retry_rejects_boolean_policy_version_at_store_boundary(runtime_uow_factory):
    async with runtime_uow_factory.transaction() as uow:
        run = await uow.workflows.create_run(workflow_definition_id="synthetic.workflow", workflow_definition_version=1, domain_type="synthetic", runtime_mode="new")
        step = await uow.workflows.create_step(workflow_run_id=run.id, step_key="score", step_order=1, task_id="synthetic.score", task_version=1)
        attempt = await uow.workflows.create_attempt(workflow_step_id=step.id, attempt_number=1)
        with pytest.raises(ValueError):
            await uow.workflows.schedule_retry(attempt.id, retry_reason="transient", retry_policy_id="default", retry_policy_version=True)


async def test_uow_rolls_back_all_bound_repositories(runtime_uow_factory) -> None:
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
            event = await uow.events.append(
                event_type="runtime.run_created",
                event_version=1,
                aggregate_type="workflow_run",
                aggregate_id=run.id,
                workflow_run_id=run.id,
                actor_type="system",
                payload_json={"reason_code": "synthetic"},
                sensitivity="metadata",
            )
            await uow.outbox.enqueue(event.id, "runtime.evaluation")
            raise InjectedFailure

    async with runtime_uow_factory.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RuntimeEventRecord))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(RuntimeOutboxRecord))
            == 0
        )


async def test_repositories_share_one_session_and_do_not_commit_internally(
    runtime_uow_factory,
) -> None:
    async with runtime_uow_factory.transaction() as uow:
        assert uow.workflows.session is uow.events.session is uow.outbox.session
        await uow.workflows.create_run(
            workflow_definition_id="synthetic.workflow",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="new",
        )

    async with runtime_uow_factory.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(WorkflowRunRecord))
            == 0
        )


async def test_uow_exposes_complete_semantic_store_methods(runtime_uow_factory) -> None:
    async with runtime_uow_factory.transaction() as uow:
        required = {
            uow.approvals: {"request", "decide", "invalidate_for_payload_change"},
            uow.evaluations: {
                "record_policy_decision",
                "record_routing_decision",
                "record_execution",
                "record_validation",
                "record_evaluation",
                "record_observation",
            },
            uow.shadow: {"record", "purge_expired"},
        }
        for store, methods in required.items():
            assert all(hasattr(store, method) for method in methods)


def test_sqlite_repository_conforms_to_backend_neutral_workflow_store(
    runtime_uow_factory,
) -> None:
    """Would fail if Task 6 workflow semantics existed only as SQLite-only calls."""
    assert isinstance(
        SQLiteWorkflowRepository(runtime_uow_factory), DurableWorkflowStore
    )
