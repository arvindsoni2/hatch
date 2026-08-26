"""Conformance tests for the SQLite runtime unit of work."""

from __future__ import annotations

from datetime import datetime, timedelta
import inspect
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import Base, create_sqlite_engine
from app.runtime.events.models import RuntimeEventRecord, RuntimeOutboxRecord
from app.runtime.storage.contracts import WorkflowStore
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from app.runtime.workflow.kernel import WorkflowKernel
from app.runtime.workflow.repository import SQLiteWorkflowRepository
from app.runtime.workflow.models import (
    ExecutionClaimRecord,
    TaskAttemptRecord,
    TaskAttemptStatus,
    WaitingReason,
    WorkflowRunRecord,
)


@pytest_asyncio.fixture
async def runtime_uow_factory(tmp_path):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
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


def _signature_shape(callable_: Any) -> tuple[tuple[str, inspect._ParameterKind, object], ...]:
    return tuple(
        (parameter.name, parameter.kind, parameter.default)
        for parameter in inspect.signature(callable_).parameters.values()
    )


def test_sqlite_repository_matches_the_kernel_workflow_store_contract(
    runtime_uow_factory,
) -> None:
    """Would fail if a kernel-facing repository changed its durable semantic API."""
    repository = SQLiteWorkflowRepository(runtime_uow_factory)
    method_names = (
        "create_run",
        "get_attempt",
        "claim_next",
        "reclaim",
        "renew_claim",
        "finalize",
        "fail_or_retry",
        "reconcile_expired_claims",
        "transition_waiting",
        "resume_waiting",
        "mark_outcome_unknown",
        "claim_outcome_unknown",
        "return_outcome_unknown",
        "fail_terminal",
    )

    for name in method_names:
        assert _signature_shape(getattr(type(repository), name)) == _signature_shape(
            getattr(WorkflowStore, name)
        )

    # Runtime protocol membership is supplementary; signatures above are the
    # architecture seam that backend implementations must preserve.
    assert isinstance(repository, WorkflowStore)


class _RepositoryInjectedIntoKernel:
    """Small in-memory implementation of the public workflow repository seam."""

    def __init__(self, attempt: TaskAttemptRecord) -> None:
        self._attempt = attempt

    async def create_run(
        self,
        *,
        workflow_definition_id: str,
        workflow_definition_version: int,
        input_ref: dict[str, object],
        domain_ref: dict[str, object],
        mode: str,
        max_attempts: int,
    ) -> WorkflowRunRecord:
        raise AssertionError("not used by this contract test")

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        return self._attempt if attempt_id == self._attempt.id else None

    async def claim_next(self, worker_id: str, now: datetime, lease_duration: timedelta) -> ExecutionClaimRecord | None:
        raise AssertionError("not used by this contract test")

    async def reclaim(self, attempt_id: str, worker_id: str, now: datetime, lease_duration: timedelta) -> ExecutionClaimRecord | None:
        raise AssertionError("not used by this contract test")

    async def renew_claim(self, claim: ExecutionClaimRecord, now: datetime, lease_duration: timedelta) -> bool:
        raise AssertionError("not used by this contract test")

    async def finalize(self, claim: ExecutionClaimRecord, result_ref: dict[str, object], now: datetime) -> bool:
        raise AssertionError("not used by this contract test")

    async def fail_or_retry(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: str,
        policy_id: str,
        policy_version: int,
        not_before: datetime | None,
        now: datetime,
    ) -> TaskAttemptRecord | None:
        raise AssertionError("not used by this contract test")

    async def reconcile_expired_claims(self, now: datetime) -> int:
        raise AssertionError("not used by this contract test")

    async def transition_waiting(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: WaitingReason,
        now: datetime,
    ) -> bool:
        raise AssertionError("not used by this contract test")

    async def resume_waiting(
        self, attempt_id: str, *, now: datetime
    ) -> TaskAttemptRecord | None:
        raise AssertionError("not used by this contract test")

    async def mark_outcome_unknown(
        self,
        claim: ExecutionClaimRecord,
        *,
        now: datetime,
        capability_id: str,
        capability_version: int,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool:
        raise AssertionError("not used by this contract test")

    async def claim_outcome_unknown(self, attempt_id: str, worker_id: str, now: datetime, lease_duration: timedelta) -> ExecutionClaimRecord | None:
        raise AssertionError("not used by this contract test")

    async def return_outcome_unknown(self, claim: ExecutionClaimRecord, *, now: datetime) -> bool:
        raise AssertionError("not used by this contract test")

    async def fail_terminal(self, claim: ExecutionClaimRecord, *, reason: str, now: datetime) -> bool:
        raise AssertionError("not used by this contract test")


async def test_kernel_get_attempt_uses_the_injected_workflow_store() -> None:
    """Would fail if a kernel bypassed a non-SQLite durable repository."""
    attempt = TaskAttemptRecord(workflow_step_id="synthetic-step", attempt_number=1)
    repository = _RepositoryInjectedIntoKernel(attempt)
    kernel = WorkflowKernel(object(), repository=repository)  # type: ignore[arg-type]

    assert await kernel.get_attempt(attempt.id) is attempt
