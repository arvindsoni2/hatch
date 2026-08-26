"""Waiting-state contracts: releases are fenced and resumption is fresh."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.runtime.workflow.models import (
    ExecutionClaimRecord,
    ExecutionClaimStatus,
    TaskAttemptStatus,
    WaitingReason,
)
from app.runtime.workflow.retry import RetryFailure
from workflow_test_support import start_and_claim


async def test_waiting_owns_no_claim_and_resume_gets_a_new_fence(workflow_runtime) -> None:
    """Would fail if waiting kept or revived an active worker claim."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1, 12)
    _, first_claim = await start_and_claim(kernel, now=now)

    assert await kernel.wait_for(first_claim, WaitingReason.APPROVAL, now) is True
    waiting = await kernel.get_attempt(first_claim.task_attempt_id)
    assert waiting is not None
    assert waiting.status == TaskAttemptStatus.WAITING
    assert waiting.waiting_reason == WaitingReason.APPROVAL
    assert waiting.current_claim_id is None
    async with factory.session_factory() as session:
        claim = await session.get(ExecutionClaimRecord, first_claim.id)
    assert claim is not None
    assert claim.status == ExecutionClaimStatus.RELEASED

    assert await kernel.resume_waiting(waiting.id, now + timedelta(seconds=1)) is True
    resumed = await kernel.get_attempt(waiting.id)
    assert resumed is not None
    assert resumed.status == TaskAttemptStatus.PENDING
    assert resumed.current_claim_id is None
    second_claim = await kernel.claim_next("worker-b", now + timedelta(seconds=1))
    assert second_claim is not None
    assert second_claim.task_attempt_id == first_claim.task_attempt_id
    assert second_claim.id != first_claim.id
    assert second_claim.fencing_token == first_claim.fencing_token + 1


async def test_stale_worker_cannot_move_newer_claim_to_waiting(workflow_runtime) -> None:
    """Would fail if wait_for conditioned only on attempt identity."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, stale_claim = await start_and_claim(kernel, now=now)
    current_claim = await kernel.reclaim(
        stale_claim.task_attempt_id, "worker-b", stale_claim.lease_expires_at
    )
    assert current_claim is not None

    assert await kernel.wait_for(stale_claim, WaitingReason.USER_INPUT, now) is False
    attempt = await kernel.get_attempt(stale_claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.RUNNING
    assert attempt.current_claim_id == current_claim.id


@pytest.mark.parametrize("reason", ["approval", "", object()])
async def test_invalid_wait_reason_rolls_back_without_releasing_owner(
    workflow_runtime, reason: object
) -> None:
    """Would fail if arbitrary values could enter durable waiting metadata."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)

    with pytest.raises(ValueError, match="waiting reason"):
        await kernel.wait_for(claim, reason, now)  # type: ignore[arg-type]
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.RUNNING
    assert attempt.current_claim_id == claim.id


async def test_only_approval_and_user_input_waits_are_manually_resumable(
    workflow_runtime,
) -> None:
    """Would fail if a caller could bypass durable retry-time scheduling."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    retry = await kernel.fail_or_retry(
        claim,
        RetryFailure(
            "transient_failure",
            "synthetic.retry",
            1,
            retry_after=timedelta(minutes=1),
        ),
        now,
    )
    assert retry is not None
    assert retry.waiting_reason == WaitingReason.RETRY_TIME
    assert await kernel.resume_waiting(retry.id, now) is False
    persisted = await kernel.get_attempt(retry.id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.WAITING
    assert persisted.waiting_reason == WaitingReason.RETRY_TIME


async def test_completed_attempt_cannot_be_resumed_as_waiting(workflow_runtime) -> None:
    """Would fail if resume did not condition on the durable WAITING state."""
    kernel, _ = workflow_runtime
    now = datetime(2030, 1, 1)
    _, claim = await start_and_claim(kernel, now=now)
    assert await kernel.finalize(claim, {"result_ref": "synthetic-result"}) is True
    assert await kernel.resume_waiting(claim.task_attempt_id, now) is False
