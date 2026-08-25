"""Semantic repository and unit-of-work protocols for the runtime."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from typing import Any, Protocol

from ..evaluation.models import (
    EvaluationRunRecord,
    EvidenceObservationRecord,
    ExecutionRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    ShadowComparisonRecord,
    ValidationResultRecord,
)
from ..events.models import RuntimeEventRecord, RuntimeOutboxRecord
from ..events.outbox import OutboxClaim
from ..workflow.models import (
    ApprovalRecord,
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
    async def request(self, **values: Any) -> ApprovalRecord: ...

    async def decide(self, approval_id: str, **values: Any) -> bool: ...

    async def invalidate_for_payload_change(
        self, task_attempt_id: str, *, current_payload_hash: str
    ) -> int: ...


class EventStore(Protocol):
    async def append(self, **values: Any) -> RuntimeEventRecord: ...


class OutboxStore(Protocol):
    async def enqueue(self, event_id: str, destination: str) -> RuntimeOutboxRecord: ...

    async def claim_next(
        self, *, now: datetime, lease_duration: timedelta
    ) -> OutboxClaim | None: ...

    async def finalize_delivery(
        self,
        claim: OutboxClaim,
        *,
        delivered: bool,
        lease_duration: timedelta,
        **values: Any,
    ) -> bool: ...


class EvaluationStore(Protocol):
    async def record_policy_decision(self, **values: Any) -> PolicyDecisionRecord: ...

    async def record_routing_decision(self, **values: Any) -> RoutingDecisionRecord: ...

    async def record_execution(self, **values: Any) -> ExecutionRecord: ...

    async def record_validation(self, **values: Any) -> ValidationResultRecord: ...

    async def record_evaluation(self, **values: Any) -> EvaluationRunRecord: ...

    async def record_observation(self, **values: Any) -> EvidenceObservationRecord: ...


class ShadowComparisonStore(Protocol):
    async def record(self, **values: Any) -> ShadowComparisonRecord: ...

    async def purge_expired(self, *, now: datetime | None = None) -> int: ...


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
