"""Durable pre-invocation intent and crash-recovery contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import (
    CapabilityResult,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.workflow import (
    InjectedFailure,
    ReconciliationDecision,
    ReconciliationRegistry,
    TaskAttemptStatus,
    WorkflowKernel,
    WorkflowReconciler,
)

from execution_test_support import (
    NOW,
    RecordingAdapter,
    SyntheticOutput,
    descriptor,
    gateway_case,
    policy_for,
)


class _FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


def _inject_crash_after_successful_result_persistence(kernel, monkeypatch) -> None:
    """Raise only after the real fenced result transaction has committed."""
    persist = kernel.persist_execution_result

    async def persist_then_crash(*args, **kwargs):
        persisted = await persist(*args, **kwargs)
        if persisted:
            raise InjectedFailure("execution_result_persisted")
        return persisted

    monkeypatch.setattr(kernel, "persist_execution_result", persist_then_crash)


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


@pytest.mark.parametrize(
    ("side_effect", "idempotency", "payload"),
    (
        (
            SideEffectClass.COMMIT_SIDE_EFFECT,
            IdempotencyClass.CHECK_BEFORE_RETRY,
            {"count": 7, "idempotency_key": "post-persist-check-key"},
        ),
        (
            SideEffectClass.PURE,
            IdempotencyClass.NON_RETRYABLE_SIDE_EFFECT,
            {"count": 7},
        ),
        (
            SideEffectClass.ARTIFACT_GENERATION,
            IdempotencyClass.IDEMPOTENT_WITH_KEY,
            {"count": 7, "idempotency_key": "post-persist-artifact-key"},
        ),
    ),
    ids=("check-before-retry", "non-retryable", "artifact"),
)
async def test_successful_unsafe_result_remains_nonreplayable_until_finalization(
    workflow_runtime,
    monkeypatch,
    side_effect,
    idempotency,
    payload,
) -> None:
    """Would fail if successful unsafe persistence cleared its durable disposition."""
    capability_id = "synthetic.post_persist_crash"
    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(),
        descriptor(
            capability_id,
            side_effect=side_effect,
            idempotency=idempotency,
        ),
    )
    _inject_crash_after_successful_result_persistence(kernel, monkeypatch)

    with pytest.raises(InjectedFailure, match="execution_result_persisted"):
        await gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload=payload,
        )

    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.status == TaskAttemptStatus.RUNNING
    assert persisted.execution_intent_active is True
    async with factory.session_factory() as session:
        records = list((await session.scalars(select(ExecutionRecord))).all())
    assert len(records) == 1
    assert records[0].result_class == "success"

    recovery_time = claim.lease_expires_at
    restarted = WorkflowKernel(
        factory,
        lease_duration=timedelta(seconds=30),
        clock=_FixedClock(recovery_time),
    )
    assert (
        await restarted.reclaim(
            claim.task_attempt_id,
            "ordinary-replacement",
            recovery_time,
        )
        is None
    )
    assert await restarted.reconcile(recovery_time) == 1
    assert (
        await restarted.finalize(
            claim,
            {"result_ref": "stale-worker-result"},
            now=recovery_time,
        )
        is False
    )
    recovered = await restarted.get_attempt(claim.task_attempt_id)
    assert recovered is not None
    assert recovered.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert recovered.current_claim_id is None
    assert await restarted.claim_next("blind-replay-worker", recovery_time) is None


async def test_unsafe_disposition_clears_atomically_with_task_finalization(
    workflow_runtime,
) -> None:
    """Would fail if unsafe disposition closed before fenced task finalization."""
    capability_id = "synthetic.finalize_disposition"
    gateway, kernel, _, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(),
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
        payload={"count": 7, "idempotency_key": "finalize-disposition-key"},
    )

    assert result.code.value == "success"
    before_finalize = await kernel.get_attempt(claim.task_attempt_id)
    assert before_finalize is not None
    assert before_finalize.execution_intent_active is True
    assert await kernel.finalize(
        claim,
        {"result_ref": "finalized-workflow-result"},
        now=NOW,
    )
    finalized = await kernel.get_attempt(claim.task_attempt_id)
    assert finalized is not None
    assert finalized.status == TaskAttemptStatus.SUCCEEDED
    assert finalized.execution_intent_active is False


async def test_post_persist_crash_does_not_overblock_pure_idempotent_replay(
    workflow_runtime,
    monkeypatch,
) -> None:
    """Would fail if conservative recovery also blocked replay-safe pure work."""
    capability_id = "synthetic.safe_post_persist_crash"
    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(),
        descriptor(
            capability_id,
            side_effect=SideEffectClass.PURE,
            idempotency=IdempotencyClass.IDEMPOTENT,
        ),
    )
    _inject_crash_after_successful_result_persistence(kernel, monkeypatch)

    with pytest.raises(InjectedFailure, match="execution_result_persisted"):
        await gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload={"count": 7},
        )

    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.execution_intent_active is False
    recovery_time = claim.lease_expires_at
    restarted = WorkflowKernel(
        factory,
        lease_duration=timedelta(seconds=30),
        clock=_FixedClock(recovery_time),
    )
    assert await restarted.reconcile(recovery_time) == 1
    replacement = await restarted.claim_next("safe-replay-worker", recovery_time)
    assert replacement is not None
    assert replacement.task_attempt_id == claim.task_attempt_id
    assert replacement.fencing_token > claim.fencing_token
    assert (
        await restarted.finalize(
            claim,
            {"result_ref": "stale-safe-result"},
            now=recovery_time,
        )
        is False
    )


async def test_correlation_handle_survives_adapter_result_and_restart_reconciliation(
    workflow_runtime,
    monkeypatch,
) -> None:
    """Would fail if adapter, durable result, and reconciler used different handles."""
    capability_id = "synthetic.correlated_commit"
    raw_key = "TOKEN-raw-provider-key"
    sensitive_canary = "RAW-provider-operation|/tmp/private-candidate-content"
    effects_by_handle: dict[str | None, str] = {}
    adapter_handles: list[str | None] = []

    async def commit_effect(_payload, context):
        handle = getattr(context, "correlation_handle", None)
        adapter_handles.append(handle)
        effects_by_handle[handle] = "committed"
        return CapabilityResult.success(
            SyntheticOutput(result_ref="correlated-result", count=7)
        )

    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(handler=commit_effect),
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )
    _inject_crash_after_successful_result_persistence(kernel, monkeypatch)

    with pytest.raises(InjectedFailure, match="execution_result_persisted"):
        await gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id),
            payload={
                "count": 7,
                "idempotency_key": raw_key,
                "sensitive_value": sensitive_canary,
            },
        )

    assert len(adapter_handles) == 1
    handle = adapter_handles[0]
    assert isinstance(handle, str)
    assert handle.startswith("sha256.")
    persisted = await kernel.get_attempt(claim.task_attempt_id)
    assert persisted is not None
    assert persisted.reconciliation_reference == handle
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
    assert record is not None
    assert record.metadata_json["correlation_handle"] == handle
    durable_snapshot = json.dumps(
        {
            "intent": persisted.reconciliation_reference,
            "result": record.metadata_json,
        },
        sort_keys=True,
    )
    assert raw_key not in durable_snapshot
    assert sensitive_canary not in durable_snapshot

    recovery_time = claim.lease_expires_at
    restarted = WorkflowKernel(
        factory,
        lease_duration=timedelta(seconds=30),
        clock=_FixedClock(recovery_time),
    )
    assert await restarted.reconcile(recovery_time) == 1
    reconciliation_inputs: list[str] = []
    registry = ReconciliationRegistry()

    async def lookup_effect(*, reconciliation_reference: str, **_):
        reconciliation_inputs.append(reconciliation_reference)
        return (
            ReconciliationDecision.CONFIRMED
            if effects_by_handle.get(reconciliation_reference) == "committed"
            else ReconciliationDecision.NOT_FOUND
        )

    registry.register(capability_id, 1, lookup_effect)
    decision = await WorkflowReconciler(
        restarted,
        registry,
        worker_id="restart-reconciler",
        clock=_FixedClock(recovery_time),
    ).reconcile_outcome_unknown(claim.task_attempt_id, recovery_time)

    assert decision is ReconciliationDecision.CONFIRMED
    assert reconciliation_inputs == [handle]
    finalized = await restarted.get_attempt(claim.task_attempt_id)
    assert finalized is not None
    assert finalized.status == TaskAttemptStatus.SUCCEEDED
    assert await restarted.claim_next("blind-replay-worker", recovery_time) is None
