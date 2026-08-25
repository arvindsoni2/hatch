"""SQLite-backed runtime repositories sharing one transaction-scoped session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..events.models import RuntimeEventRecord, RuntimeOutboxRecord
from ..workflow.models import (
    TaskAttemptRecord,
    TaskAttemptStatus,
    WaitingReason,
    WorkflowRunRecord,
    WorkflowStepRecord,
)


class _SessionBoundStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _add(self, record: Any) -> Any:
        self.session.add(record)
        await self.session.flush()
        return record


class SQLiteWorkflowStore(_SessionBoundStore):
    async def create_run(self, **values: Any) -> WorkflowRunRecord:
        return await self._add(WorkflowRunRecord(**values))

    async def create_step(self, **values: Any) -> WorkflowStepRecord:
        return await self._add(WorkflowStepRecord(**values))

    async def create_attempt(self, **values: Any) -> TaskAttemptRecord:
        return await self._add(TaskAttemptRecord(**values))

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        return await self.session.get(TaskAttemptRecord, attempt_id)

    async def schedule_retry(
        self,
        attempt_id: str,
        *,
        retry_reason: str,
        retry_policy_id: str,
        retry_policy_version: int,
        not_before: datetime | None = None,
    ) -> TaskAttemptRecord:
        prior = await self.get_attempt(attempt_id)
        if prior is None:
            raise LookupError(f"task attempt not found: {attempt_id}")
        retry = TaskAttemptRecord(
            workflow_step_id=prior.workflow_step_id,
            attempt_number=prior.attempt_number + 1,
            prior_attempt_id=prior.id,
            status=(
                TaskAttemptStatus.WAITING if not_before else TaskAttemptStatus.PENDING
            ),
            waiting_reason=WaitingReason.RETRY_TIME if not_before else None,
            not_before=not_before,
            retry_reason=retry_reason,
            retry_policy_id=retry_policy_id,
            retry_policy_version=retry_policy_version,
        )
        return await self._add(retry)


class SQLiteEventStore(_SessionBoundStore):
    async def append(self, **values: Any) -> RuntimeEventRecord:
        return await self._add(RuntimeEventRecord(**values))


class SQLiteOutboxStore(_SessionBoundStore):
    async def enqueue(self, event_id: str, destination: str) -> RuntimeOutboxRecord:
        return await self._add(
            RuntimeOutboxRecord(event_id=event_id, destination=destination)
        )


class SQLiteApprovalStore(_SessionBoundStore):
    pass


class SQLiteEvaluationStore(_SessionBoundStore):
    pass


class SQLiteShadowComparisonStore(_SessionBoundStore):
    pass


class SQLiteRuntimeUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflows = SQLiteWorkflowStore(session)
        self.approvals = SQLiteApprovalStore(session)
        self.events = SQLiteEventStore(session)
        self.outbox = SQLiteOutboxStore(session)
        self.evaluations = SQLiteEvaluationStore(session)
        self.shadow = SQLiteShadowComparisonStore(session)
        self._committed = False

    async def commit(self) -> None:
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self.session.rollback()
        self._committed = False


class SQLiteRuntimeUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SQLiteRuntimeUnitOfWork]:
        async with self.session_factory() as session:
            uow = SQLiteRuntimeUnitOfWork(session)
            try:
                yield uow
            except BaseException:
                await uow.rollback()
                raise
