"""Semantic repository and unit-of-work protocols for the runtime."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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

if TYPE_CHECKING:
    from ..workflow.models import (
        ApprovalRecord,
        ExecutionClaimRecord,
        TaskAttemptRecord,
        WaitingReason,
        WorkflowRunRecord,
        WorkflowStepRecord,
    )


@runtime_checkable
class WorkflowStore(Protocol):
    """Backend-neutral durable workflow semantics used by the kernel.

    Implementations may use SQLite conditional updates or PostgreSQL row locks, but
    must preserve the same fencing, waiting, and ambiguous-outcome behavior.
    """

    async def create_run(
        self,
        *,
        workflow_definition_id: str,
        workflow_definition_version: int,
        input_ref: dict[str, object],
        domain_ref: dict[str, object],
        mode: str,
        max_attempts: int,
    ) -> WorkflowRunRecord: ...

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None: ...

    async def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ExecutionClaimRecord | None: ...

    async def reclaim(
        self,
        attempt_id: str,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ExecutionClaimRecord | None: ...

    async def renew_claim(
        self,
        claim: ExecutionClaimRecord,
        now: datetime,
        lease_duration: timedelta,
    ) -> bool: ...

    async def finalize(
        self,
        claim: ExecutionClaimRecord,
        result_ref: dict[str, object],
        now: datetime,
    ) -> bool: ...

    async def begin_execution_intent(
        self,
        claim: ExecutionClaimRecord,
        *,
        now: datetime,
        capability_id: str,
        capability_version: int,
        side_effect_class: str,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool: ...

    async def persist_execution_result(
        self,
        claim: ExecutionClaimRecord,
        *,
        execution_role: str,
        capability_id: str,
        capability_version: int,
        side_effect_class: str,
        idempotency_class: str,
        reconciliation_reference: str,
        result_class: str,
        started_at: datetime,
        finished_at: datetime,
        latency_ms: int,
        metadata: dict[str, object],
        outcome_unknown: dict[str, object] | None,
    ) -> bool: ...

    async def fail_or_retry(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: str,
        policy_id: str,
        policy_version: int,
        not_before: datetime | None,
        now: datetime,
    ) -> TaskAttemptRecord | None: ...

    async def reconcile_expired_claims(
        self,
        now: datetime,
        *,
        batch_size: int = 25,
        recovery_backoff_seconds: int = 1,
    ) -> int: ...

    async def transition_waiting(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: WaitingReason,
        now: datetime,
    ) -> bool: ...

    async def resume_waiting(
        self, attempt_id: str, *, now: datetime
    ) -> TaskAttemptRecord | None: ...

    async def mark_outcome_unknown(
        self,
        claim: ExecutionClaimRecord,
        *,
        now: datetime,
        capability_id: str,
        capability_version: int,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool: ...

    async def claim_outcome_unknown(
        self,
        attempt_id: str,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ExecutionClaimRecord | None: ...

    async def return_outcome_unknown(
        self, claim: ExecutionClaimRecord, *, now: datetime
    ) -> bool: ...

    async def fail_terminal(
        self, claim: ExecutionClaimRecord, *, reason: str, now: datetime
    ) -> bool: ...


class WorkflowRecordStore(Protocol):
    """Transaction-bound record operations used inside a runtime unit of work.

    This intentionally does not expose claim or reconciliation operations. Those
    are kernel-facing durable semantics on :class:`WorkflowStore` above.
    """

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

    async def decide(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str,
        decision_reason: str | None = None,
        decided_at: datetime | None = None,
    ) -> bool: ...

    async def expire_if_due(self, approval_id: str, *, now: datetime) -> bool: ...

    async def invalidate_for_payload_change(
        self,
        task_attempt_id: str,
        *,
        current_payload_hash: str,
        now: datetime,
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
    workflows: WorkflowRecordStore
    approvals: ApprovalStore
    events: EventStore
    outbox: OutboxStore
    evaluations: EvaluationStore
    shadow: ShadowComparisonStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class RuntimeUnitOfWorkFactory(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RuntimeUnitOfWork]: ...
