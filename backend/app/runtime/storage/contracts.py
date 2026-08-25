"""Semantic repository and unit-of-work protocols for the runtime."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol

from ..events.models import RuntimeEventRecord, RuntimeOutboxRecord
from ..workflow.models import (
    TaskAttemptRecord,
    WorkflowRunRecord,
    WorkflowStepRecord,
)


class WorkflowStore(Protocol):
    async def create_run(self, **values: Any) -> WorkflowRunRecord: ...

    async def create_step(self, **values: Any) -> WorkflowStepRecord: ...

    async def create_attempt(self, **values: Any) -> TaskAttemptRecord: ...

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None: ...

    async def schedule_retry(
        self,
        attempt_id: str,
        *,
        retry_reason: str,
        retry_policy_id: str,
        retry_policy_version: int,
        not_before: datetime | None = None,
    ) -> TaskAttemptRecord: ...


class ApprovalStore(Protocol):
    """Storage boundary for durable human approval records."""


class EventStore(Protocol):
    async def append(self, **values: Any) -> RuntimeEventRecord: ...


class OutboxStore(Protocol):
    async def enqueue(self, event_id: str, destination: str) -> RuntimeOutboxRecord: ...


class EvaluationStore(Protocol):
    """Storage boundary for runtime decisions and evaluation evidence."""


class ShadowComparisonStore(Protocol):
    """Storage boundary for metadata-only shadow comparisons."""


class RuntimeUnitOfWork(Protocol):
    workflows: WorkflowStore
    approvals: ApprovalStore
    events: EventStore
    outbox: OutboxStore
    evaluations: EvaluationStore
    shadow: ShadowComparisonStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class RuntimeUnitOfWorkFactory(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RuntimeUnitOfWork]: ...
