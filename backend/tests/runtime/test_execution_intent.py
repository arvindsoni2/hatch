"""Durable pre-invocation intent and crash-recovery contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import (
    CapabilityResult,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.workflow import TaskAttemptStatus, WorkflowKernel

from execution_test_support import (
    NOW,
    RecordingAdapter,
    SyntheticOutput,
    descriptor,
    gateway_case,
    policy_for,
)


async def test_fenced_intent_is_committed_before_adapter_invocation(
    workflow_runtime,
) -> None:
    """Would fail if adapter work began before its durable intent transaction closed."""
    capability_id = "synthetic.intent_order"
    raw_key = "TOKEN-intent-order-canary"
    observed = {}

    async def inspect_durable_intent(_payload, _context):
        async with factory.session_factory() as session:
            from app.runtime.workflow import TaskAttemptRecord

            attempt = await session.get(TaskAttemptRecord, claim.task_attempt_id)
            assert attempt is not None
            observed.update(
                active=getattr(attempt, "execution_intent_active", False),
                capability_id=attempt.capability_id,
                capability_version=attempt.capability_version,
                side_effect_class=getattr(attempt, "side_effect_class", None),
                idempotency_class=attempt.idempotency_class,
                reconciliation_reference=attempt.reconciliation_reference,
                execution_count=await session.scalar(
                    select(func.count()).select_from(ExecutionRecord)
                ),
            )
        return CapabilityResult.success(
            SyntheticOutput(result_ref="intent-result", count=7)
        )

    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(handler=inspect_durable_intent),
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7, "idempotency_key": raw_key},
    )

    assert result.code.value == "success"
    reference = observed.pop("reconciliation_reference")
    assert observed == {
        "active": True,
        "capability_id": capability_id,
        "capability_version": 1,
        "side_effect_class": "commit_side_effect",
        "idempotency_class": "check_before_retry",
        "execution_count": 0,
    }
    assert reference.startswith("sha256.")
    assert raw_key not in reference
    assert raw_key not in json.dumps(
        {**observed, "reference": reference}, sort_keys=True
    )


@pytest.mark.parametrize(
    ("raised", "side_effect", "idempotency"),
    (
        (
            SystemExit("synthetic_crash"),
            SideEffectClass.COMMIT_SIDE_EFFECT,
            IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
        (
            RuntimeError("synthetic_persistence_failure"),
            SideEffectClass.PURE,
            IdempotencyClass.NON_RETRYABLE_SIDE_EFFECT,
        ),
    ),
    ids=("crash-after-effect", "persistence-failure-after-effect"),
)
async def test_effect_without_result_persistence_recovers_as_outcome_unknown(
    workflow_runtime,
    monkeypatch,
    raised,
    side_effect,
    idempotency,
) -> None:
    """Would fail if an active ambiguous intent recovered to replayable PENDING."""
    capability_id = "synthetic.effect_before_persist"
    raw_key = "TOKEN-effect-before-persist"
    effects = []

    async def commit_effect(_payload, _context):
        effects.append("committed")
        return CapabilityResult.success(
            SyntheticOutput(result_ref="committed-result", count=7)
        )

    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(handler=commit_effect),
        descriptor(
            capability_id,
            side_effect=side_effect,
            idempotency=idempotency,
        ),
    )

    async def fail_result_persistence(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(kernel, "persist_execution_result", fail_result_persistence)

    with pytest.raises(type(raised), match=str(raised)):
        await gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload={"count": 7, "idempotency_key": raw_key},
        )

    assert effects == ["committed"]
    restarted = WorkflowKernel(factory, lease_duration=timedelta(seconds=30))
    assert await restarted.reconcile(NOW + timedelta(seconds=31)) == 1
    attempt = await restarted.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert attempt.capability_id == capability_id
    assert attempt.capability_version == 1
    assert attempt.idempotency_class == idempotency.value
    assert attempt.reconciliation_reference.startswith("sha256.")
    assert raw_key not in attempt.reconciliation_reference
    assert (
        await restarted.claim_next("blind-replay-worker", NOW + timedelta(seconds=31))
        is None
    )
    async with factory.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ExecutionRecord)) == 0
        )


async def test_cancelled_ambiguous_invocation_recovers_without_blind_replay(
    workflow_runtime,
) -> None:
    """Would fail if cancellation discarded the durable ambiguous-effect intent."""
    capability_id = "synthetic.cancelled_commit"
    started = asyncio.Event()

    async def possibly_committing(_payload, _context):
        started.set()
        await asyncio.Event().wait()

    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(handler=possibly_committing),
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
            timeout=60.0,
        ),
    )
    task = asyncio.create_task(
        gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload={"count": 7, "idempotency_key": "cancelled-commit-key"},
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    restarted = WorkflowKernel(factory, lease_duration=timedelta(seconds=30))
    assert await restarted.reconcile(NOW + timedelta(seconds=31)) == 1
    attempt = await restarted.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert (
        await restarted.claim_next("blind-replay-worker", NOW + timedelta(seconds=31))
        is None
    )
