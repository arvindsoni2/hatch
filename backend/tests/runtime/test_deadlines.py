"""Deadline, timeout, budget propagation, and cancellation contracts."""

from __future__ import annotations

import asyncio
from datetime import timedelta, timezone

import pytest
from sqlalchemy import select

from app.runtime.control import BudgetLimits, ConstraintSet, ControlPlane, PolicyLayer
from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import CapabilityResult, IdempotencyClass, SideEffectClass

from execution_test_support import (
    NOW,
    RecordingAdapter,
    SyntheticOutput,
    descriptor,
    gateway_case,
)


async def test_earlier_policy_deadline_and_budgets_reach_adapter(
    workflow_runtime,
) -> None:
    """Would fail if a descriptor timeout widened an earlier Control Plane deadline."""
    capability_id = "synthetic.deadline"
    observed = {}

    async def handler(_payload, context):
        observed["context"] = context
        return CapabilityResult.success(
            SyntheticOutput(result_ref="deadline-result", count=7)
        )

    adapter = RecordingAdapter(handler=handler)
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime, adapter, descriptor(capability_id, timeout=10.0)
    )
    deadline = NOW.replace(tzinfo=timezone.utc) + timedelta(seconds=2)
    policy = ControlPlane().evaluate(
        system=PolicyLayer(
            ConstraintSet(
                allowed_capabilities=frozenset({capability_id}),
                deadline=deadline,
                budgets=BudgetLimits(max_input_tokens=11, max_output_tokens=13),
            )
        )
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy,
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert observed["context"].deadline == deadline
    assert observed["context"].budgets.max_input_tokens == 11
    assert observed["context"].budgets.max_output_tokens == 13


async def test_timeout_of_commit_is_outcome_unknown_not_retryable(
    workflow_runtime,
) -> None:
    """Would fail if cancellation at a commit boundary were called a safe timeout."""
    capability_id = "synthetic.commit_timeout"

    async def blocks(_payload, _context):
        await asyncio.Event().wait()

    adapter = RecordingAdapter(handler=blocks)
    gateway, kernel, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
            timeout=0.01,
        ),
    )

    from execution_test_support import policy_for

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7, "idempotency_key": "timeout-key"},
    )

    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.reason_code == "capability_timeout_ambiguous"
    assert result.retry_allowed is False
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == "outcome_unknown"


async def test_external_cancellation_remains_cancellation(workflow_runtime) -> None:
    """Would fail if caller cancellation were swallowed as a timeout or failure."""
    capability_id = "synthetic.cancel"
    started = asyncio.Event()

    async def blocks(_payload, _context):
        started.set()
        await asyncio.Event().wait()

    adapter = RecordingAdapter(handler=blocks)
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(capability_id, timeout=60.0),
    )
    from execution_test_support import policy_for

    task = asyncio.create_task(
        gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload={"count": 7},
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ExecutionRecord))).all()) == []
