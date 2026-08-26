"""Durable, product-independent checks for ambiguous external outcomes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any

from .kernel import WorkflowKernel
from .retry import RetryFailure


class ReconciliationDecision(str, Enum):
    """A handler's durable-safe observation of a possibly committed action."""

    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"


ReconciliationHandler = Callable[..., Awaitable[ReconciliationDecision]]


class ReconciliationRegistry:
    """In-process handler lookup; workflow state remains in the repository."""

    def __init__(self) -> None:
        self._handlers: dict[str, ReconciliationHandler] = {}

    def register(self, capability_id: str, handler: ReconciliationHandler) -> None:
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise ValueError("capability_id is required")
        if not callable(handler):
            raise ValueError("reconciliation handler must be callable")
        self._handlers[capability_id.strip()] = handler

    def require(self, capability_id: str) -> ReconciliationHandler:
        handler = self._handlers.get(capability_id)
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
    ) -> None:
        self._kernel = kernel
        self._registry = registry
        self._worker_id = worker_id

    async def reconcile_outcome_unknown(
        self,
        attempt_id: str,
        capability_id: str,
        now: datetime,
        *,
        retry_failure: RetryFailure | None = None,
    ) -> ReconciliationDecision | None:
        """Check first, then finalize or explicitly schedule an allowed retry."""
        handler = self._registry.require(capability_id)
        claim = await self._kernel.claim_outcome_unknown(attempt_id, self._worker_id, now)
        if claim is None:
            return None
        try:
            decision = await handler(
                task_attempt_id=attempt_id,
                capability_id=capability_id,
                fencing_token=claim.fencing_token,
            )
            if not isinstance(decision, ReconciliationDecision):
                raise ValueError("reconciliation handler returned an invalid decision")
            if decision is ReconciliationDecision.CONFIRMED:
                finalized = await self._kernel.finalize(
                    claim, {"result_ref": "reconciled-confirmed"}
                )
                if not finalized:
                    return None
                return decision
            if retry_failure is None:
                await self._kernel.fail_terminal(claim, "outcome_not_found", now)
            else:
                await self._kernel.fail_or_retry(claim, retry_failure, now)
            return decision
        except BaseException:
            await self._kernel.return_outcome_unknown(claim, now)
            raise

    async def fail_non_retryable_side_effect(
        self, claim: Any, now: datetime
    ) -> bool:
        """Never replay a non-idempotent effect without a domain-specific check."""
        return await self._kernel.fail_terminal(
            claim, "non_retryable_side_effect", now
        )
