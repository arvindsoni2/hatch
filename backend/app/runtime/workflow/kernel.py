"""Product-independent durable workflow kernel."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Mapping

from sqlalchemy.exc import OperationalError

from ..contracts.task_spec import TaskSpec
from ..events.repository import enforce_metadata_only
from ..migration.modes import RuntimeMode
from ..storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from .models import ExecutionClaimRecord, TaskAttemptRecord
from .repository import SQLiteWorkflowRepository
from .retry import RetryFailure


class InjectedFailure(RuntimeError):
    """Test-only deterministic failure used to verify durable crash boundaries."""


class WorkflowKernel:
    """Creates durable work and grants only database-backed execution claims."""

    def __init__(
        self,
        uow_factory: SQLiteRuntimeUnitOfWorkFactory,
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        worker_id: str = "workflow-kernel",
        fail_after: str | None = None,
        lock_retry_attempts: int = 3,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if lock_retry_attempts < 1:
            raise ValueError("lock_retry_attempts must be at least 1")
        self._uow_factory = uow_factory
        self._lease_duration = lease_duration
        self._repository = SQLiteWorkflowRepository(uow_factory)
        self._worker_id = worker_id
        self._lock_retry_attempts = lock_retry_attempts
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
        )

    async def claim_next(
        self, worker_id: str, now: datetime
    ) -> ExecutionClaimRecord | None:
        for attempt in range(self._lock_retry_attempts):
            try:
                return await self._repository.claim_next(
                    worker_id, now, self._lease_duration
                )
            except OperationalError as error:
                if "locked" not in str(error).lower() or attempt + 1 == self._lock_retry_attempts:
                    raise
                await asyncio.sleep(0.005 * (2**attempt))
        return None

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        async with self._uow_factory.transaction() as uow:
            return await uow.workflows.get_attempt(attempt_id)

    async def reclaim(
        self, attempt_id: str, worker_id: str, now: datetime
    ) -> ExecutionClaimRecord | None:
        return await self._repository.reclaim(
            attempt_id, worker_id, now, self._lease_duration
        )

    async def renew_claim(self, claim: ExecutionClaimRecord, now: datetime) -> bool:
        return await self._repository.renew_claim(claim, now, self._lease_duration)

    async def finalize(
        self, claim: ExecutionClaimRecord, result: Mapping[str, object]
    ) -> bool:
        result_ref = dict(result)
        if not isinstance(result_ref.get("result_ref"), str) or not result_ref["result_ref"]:
            raise ValueError("result must contain a non-empty result_ref")
        enforce_metadata_only(result_ref, path="result_ref")
        return await self._repository.finalize(claim, result_ref, datetime.utcnow())

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

    async def reconcile(self, now: datetime) -> int:
        return await self._repository.reconcile_expired_claims(now)
