"""Product-independent durable workflow kernel."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from collections.abc import Awaitable, Callable
from typing import Any, Mapping, Protocol

from sqlalchemy.exc import OperationalError

from ..contracts.task_spec import TaskSpec
from ..events.repository import enforce_metadata_only
from ..migration.modes import RuntimeMode
from ..storage.contracts import RuntimeUnitOfWorkFactory, WorkflowStore
from .models import ExecutionClaimRecord, TaskAttemptRecord, WaitingReason
from .repository import SQLiteWorkflowRepository
from .retry import RetryFailure


class InjectedFailure(RuntimeError):
    """Test-only deterministic failure used to verify durable crash boundaries."""


class Clock(Protocol):
    def now(self) -> datetime: ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.utcnow()


async def _sqlite_lock_wait(delay: float) -> None:
    await asyncio.sleep(delay)


class WorkflowKernel:
    """Creates durable work and grants only database-backed execution claims."""

    def __init__(
        self,
        uow_factory: RuntimeUnitOfWorkFactory,
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        worker_id: str = "workflow-kernel",
        fail_after: str | None = None,
        lock_retry_attempts: int = 3,
        clock: Clock | None = None,
        repository: WorkflowStore | None = None,
        lock_wait: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if lock_retry_attempts < 1:
            raise ValueError("lock_retry_attempts must be at least 1")
        self._uow_factory = uow_factory
        self._lease_duration = lease_duration
        self._repository = repository or SQLiteWorkflowRepository(uow_factory)
        self._worker_id = worker_id
        self._lock_retry_attempts = lock_retry_attempts
        self._clock = clock or _SystemClock()
        self._lock_wait = lock_wait or _sqlite_lock_wait
        if fail_after not in (None, "claim_commit"):
            raise ValueError("unsupported test failure point")
        self._fail_after = fail_after

    async def start_run(
        self,
        spec: TaskSpec[Any, Any],
        input_ref: Mapping[str, object],
        domain_ref: Mapping[str, object],
        mode: str,
    ):
        try:
            runtime_mode = RuntimeMode(mode).value
        except ValueError as error:
            raise ValueError("unsupported runtime mode") from error
        return await self._repository.create_run(
            workflow_definition_id=spec.task_id,
            workflow_definition_version=spec.version,
            input_ref=dict(input_ref),
            domain_ref=dict(domain_ref),
            mode=runtime_mode,
            max_attempts=spec.workflow_policy.max_attempts,
        )

    @property
    def clock(self) -> Clock:
        """The durable workflow time source shared with related orchestrators."""
        return self._clock

    async def claim_next(
        self, worker_id: str, now: datetime
    ) -> ExecutionClaimRecord | None:
        for attempt in range(self._lock_retry_attempts):
            try:
                return await self._repository.claim_next(
                    worker_id, now, self._lease_duration
                )
            except OperationalError as error:
                if (
                    "locked" not in str(error).lower()
                    or attempt + 1 == self._lock_retry_attempts
                ):
                    raise
                await self._lock_wait(0.005 * (2**attempt))
        return None

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        return await self._repository.get_attempt(attempt_id)

    async def reclaim(
        self, attempt_id: str, worker_id: str, now: datetime
    ) -> ExecutionClaimRecord | None:
        return await self._repository.reclaim(
            attempt_id, worker_id, now, self._lease_duration
        )

    async def renew_claim(self, claim: ExecutionClaimRecord, now: datetime) -> bool:
        return await self._repository.renew_claim(claim, now, self._lease_duration)

    async def finalize(
        self,
        claim: ExecutionClaimRecord,
        result: Mapping[str, object],
        *,
        now: datetime | None = None,
    ) -> bool:
        result_ref = dict(result)
        if (
            not isinstance(result_ref.get("result_ref"), str)
            or not result_ref["result_ref"]
        ):
            raise ValueError("result must contain a non-empty result_ref")
        enforce_metadata_only(result_ref, path="result_ref")
        finished_at = now or self._clock.now()
        if finished_at < claim.claimed_at:
            raise ValueError("clock must not finalize before the claim")
        return await self._repository.finalize(claim, result_ref, finished_at)

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
        outcome_unknown: dict[str, object] | None = None,
    ) -> bool:
        """Delegate Task 8 result persistence to the fenced durable repository."""
        return await self._repository.persist_execution_result(
            claim,
            execution_role=execution_role,
            capability_id=capability_id,
            capability_version=capability_version,
            side_effect_class=side_effect_class,
            idempotency_class=idempotency_class,
            reconciliation_reference=reconciliation_reference,
            result_class=result_class,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            metadata=metadata,
            outcome_unknown=outcome_unknown,
        )

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
    ) -> bool:
        """Commit a fenced capability binding before any adapter work begins."""
        return await self._repository.begin_execution_intent(
            claim,
            now=now,
            capability_id=capability_id,
            capability_version=capability_version,
            side_effect_class=side_effect_class,
            idempotency_class=idempotency_class,
            reconciliation_reference=reconciliation_reference,
        )

    async def fail_or_retry(
        self,
        claim: ExecutionClaimRecord,
        failure: RetryFailure,
        now: datetime,
    ) -> TaskAttemptRecord | None:
        return await self._repository.fail_or_retry(
            claim,
            reason=failure.reason,
            policy_id=failure.policy_id,
            policy_version=failure.policy_version,
            not_before=(now + failure.retry_after) if failure.retry_after else None,
            now=now,
        )

    async def run_once(self, now: datetime) -> ExecutionClaimRecord | None:
        """Claim one unit of work; callers execute only after this method returns."""
        claim = await self.claim_next(self._worker_id, now)
        if claim is not None and self._fail_after == "claim_commit":
            raise InjectedFailure("claim_commit")
        return claim

    async def reconcile(
        self,
        now: datetime,
        *,
        batch_size: int = 25,
        recovery_backoff_seconds: int = 1,
    ) -> int:
        return await self._repository.reconcile_expired_claims(
            now,
            batch_size=batch_size,
            recovery_backoff_seconds=recovery_backoff_seconds,
        )

    async def wait_for(
        self, claim: ExecutionClaimRecord, reason: WaitingReason, now: datetime
    ) -> bool:
        if not isinstance(reason, WaitingReason):
            raise ValueError("waiting reason must be a supported WaitingReason")
        if reason is WaitingReason.RETRY_TIME:
            raise ValueError(
                "RETRY_TIME is scheduler-only and cannot be requested by a worker"
            )
        return await self._repository.transition_waiting(claim, reason=reason, now=now)

    async def resume_waiting(
        self, attempt_id: str, now: datetime
    ) -> TaskAttemptRecord | None:
        return await self._repository.resume_waiting(attempt_id, now=now)

    async def mark_outcome_unknown(
        self,
        claim: ExecutionClaimRecord,
        now: datetime,
        *,
        capability_id: str,
        capability_version: int,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool:
        return await self._repository.mark_outcome_unknown(
            claim,
            now=now,
            capability_id=capability_id,
            capability_version=capability_version,
            idempotency_class=idempotency_class,
            reconciliation_reference=reconciliation_reference,
        )

    async def claim_outcome_unknown(
        self, attempt_id: str, worker_id: str, now: datetime
    ) -> ExecutionClaimRecord | None:
        return await self._repository.claim_outcome_unknown(
            attempt_id, worker_id, now, self._lease_duration
        )

    async def return_outcome_unknown(
        self, claim: ExecutionClaimRecord, now: datetime
    ) -> bool:
        return await self._repository.return_outcome_unknown(claim, now=now)

    async def fail_terminal(
        self, claim: ExecutionClaimRecord, reason: str, now: datetime
    ) -> bool:
        return await self._repository.fail_terminal(claim, reason=reason, now=now)
