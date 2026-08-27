"""Durable, product-independent checks for ambiguous external outcomes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any

from .kernel import Clock, WorkflowKernel
from .models import TaskAttemptStatus
from .retry import RetryFailure


class ReconciliationDecision(str, Enum):
    """A handler's durable-safe observation of a possibly committed action."""

    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"


ReconciliationHandler = Callable[..., Awaitable[ReconciliationDecision]]


class ReconciliationRegistry:
    """In-process handler lookup; workflow state remains in the repository."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, int], ReconciliationHandler] = {}

    def register(
        self,
        capability_id: str,
        capability_version: int,
        handler: ReconciliationHandler,
    ) -> None:
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise ValueError("capability_id is required")
        if isinstance(capability_version, bool) or not isinstance(capability_version, int) or capability_version < 1:
            raise ValueError("capability_version must be positive")
        if not callable(handler):
            raise ValueError("reconciliation handler must be callable")
        self._handlers[(capability_id.strip(), capability_version)] = handler

    def require(self, capability_id: str, capability_version: int) -> ReconciliationHandler:
        handler = self._handlers.get((capability_id, capability_version))
        if handler is None:
            raise LookupError("no reconciliation handler registered for capability")
        return handler


class WorkflowReconciler:
    """Turns OUTCOME_UNKNOWN into a fenced capability check before any retry."""

    def __init__(
        self,
        kernel: WorkflowKernel,
        registry: ReconciliationRegistry,
        *,
        worker_id: str,
        clock: Clock | None = None,
    ) -> None:
        self._kernel = kernel
        self._registry = registry
        self._worker_id = worker_id
        self._clock = clock or kernel.clock

    async def reconcile_outcome_unknown(
        self,
        attempt_id: str,
        now: datetime,
        *,
        retry_failure: RetryFailure | None = None,
    ) -> ReconciliationDecision | None:
        """Check first, then finalize or explicitly schedule an allowed retry."""
        attempt = await self._kernel.get_attempt(attempt_id)
        if (
            attempt is None
            or attempt.status != TaskAttemptStatus.OUTCOME_UNKNOWN
            or attempt.capability_id is None
            or attempt.capability_version is None
            or attempt.idempotency_class != "check_before_retry"
            or attempt.reconciliation_reference is None
        ):
            return None
        handler = self._registry.require(attempt.capability_id, attempt.capability_version)
        claim = await self._kernel.claim_outcome_unknown(attempt_id, self._worker_id, now)
        if claim is None:
            return None
        try:
            decision = await handler(
                task_attempt_id=attempt_id,
                capability_id=attempt.capability_id,
                capability_version=attempt.capability_version,
                reconciliation_reference=attempt.reconciliation_reference,
                fencing_token=claim.fencing_token,
            )
            if not isinstance(decision, ReconciliationDecision):
                raise ValueError("reconciliation handler returned an invalid decision")
            completed_at = self._clock.now()
            if decision is ReconciliationDecision.CONFIRMED:
                finalized = await self._kernel.finalize(
                    claim, {"result_ref": "reconciled-confirmed"}, now=completed_at
                )
                if not finalized:
                    return None
                return decision
            if retry_failure is None:
                if not await self._kernel.fail_terminal(
                    claim, "outcome_not_found", completed_at
                ):
                    return None
            else:
                if (
                    await self._kernel.fail_or_retry(
                        claim, retry_failure, completed_at
                    )
                    is None
                ):
                    return None
            return decision
        except BaseException:
            await self._kernel.return_outcome_unknown(claim, self._clock.now())
            raise

    async def fail_non_retryable_side_effect(
        self, claim: Any, now: datetime
    ) -> bool:
        """Never replay a non-idempotent effect without a domain-specific check."""
        return await self._kernel.fail_terminal(
            claim, "non_retryable_side_effect", now
        )
