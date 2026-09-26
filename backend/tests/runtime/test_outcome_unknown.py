"""Ambiguous-outcome and late-worker fencing contracts for the gateway."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import (
    CapabilityResult,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.workflow import TaskAttemptStatus

from execution_test_support import (
    NOW,
    RecordingAdapter,
    SyntheticOutput,
    WrongOutput,
    descriptor,
    gateway_case,
    policy_for,
)


async def test_lost_external_commit_becomes_outcome_unknown(workflow_runtime) -> None:
    """Would fail if an ambiguous external commit fell through to blind retry."""
    capability_id = "synthetic.external_commit"
    adapter = RecordingAdapter(
        CapabilityResult(
            code=ExecutionResultCode.OUTCOME_UNKNOWN,
            reason_code="provider_response_lost",
            retry_allowed=True,
            reconciliation_reference="RAW-provider-operation-id",
        )
    )
    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
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
        payload={"count": 7, "idempotency_key": "external-commit-key"},
    )

    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.retry_allowed is False
    assert result.reconciliation_reference.startswith("sha256.")
    assert "RAW-provider-operation-id" not in result.reconciliation_reference
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    assert attempt.idempotency_class == "check_before_retry"
    assert attempt.reconciliation_reference == result.reconciliation_reference
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        assert record.result_class == "outcome_unknown"


async def test_gateway_rejects_result_after_claim_loss(workflow_runtime) -> None:
    """Would fail if a late worker persisted after a newer fencing token won."""
    capability_id = "synthetic.slow"
    state = {}

    async def lose_claim(_payload, _context):
        await state["kernel"].reconcile(NOW + timedelta(seconds=31))
        replacement = await state["kernel"].reclaim(
            state["claim"].task_attempt_id,
            "worker-b",
            NOW + timedelta(seconds=31),
        )
        assert replacement is not None
        return CapabilityResult.success(
            SyntheticOutput(result_ref="late-result", count=7)
        )

    adapter = RecordingAdapter(handler=lose_claim)
    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime, adapter, descriptor(capability_id)
    )
    state.update(kernel=kernel, claim=claim)

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.PERMANENT_FAILURE
    assert result.reason_code == "claim_lost"
    assert result.output is None
    async with factory.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ExecutionRecord)) == 0
        )


async def test_raised_post_commit_exception_becomes_durable_outcome_unknown(
    workflow_runtime,
) -> None:
    """Would fail if an exception after a possible commit became permanent failure."""
    capability_id = "synthetic.raise_after_commit"
    exception_canary = "TOKEN-provider-exception-canary"

    async def raises_after_commit(_payload, _context):
        raise RuntimeError(exception_canary)

    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(handler=raises_after_commit),
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
        payload={"count": 7, "idempotency_key": "commit-exception-key"},
    )

    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.reason_code == "capability_exception_ambiguous"
    assert result.retry_allowed is False
    assert result.reconciliation_reference is not None
    assert result.reconciliation_reference.startswith("sha256.")
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        touched = json.dumps(record.metadata_json, sort_keys=True)
    assert exception_canary not in touched
    assert exception_canary not in result.model_dump_json()


async def test_malformed_post_commit_success_becomes_durable_outcome_unknown(
    workflow_runtime,
) -> None:
    """Would fail if an unvalidated commit response were classified retry-safe."""
    capability_id = "synthetic.malformed_commit"
    gateway, kernel, factory, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(
            CapabilityResult.success(
                WrongOutput(result_ref="malformed", count="not-an-integer")
            )
        ),
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
        payload={"count": 7, "idempotency_key": "malformed-commit-key"},
    )

    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.reason_code == "capability_result_ambiguous"
    assert result.retry_allowed is False
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        assert record.result_class == "outcome_unknown"


@pytest.mark.parametrize(
    ("side_effect", "payload"),
    (
        (SideEffectClass.PREPARE_SIDE_EFFECT, {"count": 7}),
        (
            SideEffectClass.ARTIFACT_GENERATION,
            {"count": 7, "idempotency_key": "artifact-malformed-key"},
        ),
    ),
)
async def test_malformed_prepare_or_artifact_result_is_ambiguous_safe_failure(
    workflow_runtime,
    side_effect,
    payload,
) -> None:
    """Would fail if a post-effect validation error were treated as replay-safe."""
    capability_id = "synthetic.malformed_side_effect"
    gateway, kernel, _, claim, _ = await gateway_case(
        workflow_runtime,
        RecordingAdapter(
            CapabilityResult.success(
                WrongOutput(result_ref="malformed", count="not-an-integer")
            )
        ),
        descriptor(
            capability_id,
            side_effect=side_effect,
            idempotency=(
                IdempotencyClass.IDEMPOTENT_WITH_KEY
                if side_effect is SideEffectClass.ARTIFACT_GENERATION
                else IdempotencyClass.IDEMPOTENT
            ),
        ),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload=payload,
    )

    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.reason_code == "capability_result_ambiguous"
    attempt = await kernel.get_attempt(claim.task_attempt_id)
    assert attempt is not None
    assert attempt.status == TaskAttemptStatus.OUTCOME_UNKNOWN


@pytest.mark.parametrize("result_code", tuple(ExecutionResultCode))
async def test_adapter_reconciliation_reference_never_crosses_gateway_boundary(
    workflow_runtime,
    result_code,
    caplog,
) -> None:
    """Would fail if any adapter result class leaked a raw provider reference."""
    capability_id = "synthetic.reference_leak"
    raw_reference = "TOKEN-/tmp-provider-operation-canary"
    adapter_result = CapabilityResult(
        code=result_code,
        output=(
            SyntheticOutput(result_ref="synthetic-result", count=7)
            if result_code is ExecutionResultCode.SUCCESS
            else None
        ),
        reason_code="provider_result",
        reconciliation_reference=raw_reference,
    )
    gateway, kernel, factory, claim, registry = await gateway_case(
        workflow_runtime,
        RecordingAdapter(adapter_result),
        descriptor(
            capability_id,
            side_effect=(
                SideEffectClass.COMMIT_SIDE_EFFECT
                if result_code is ExecutionResultCode.OUTCOME_UNKNOWN
                else SideEffectClass.PURE
            ),
            idempotency=(
                IdempotencyClass.CHECK_BEFORE_RETRY
                if result_code is ExecutionResultCode.OUTCOME_UNKNOWN
                else IdempotencyClass.IDEMPOTENT
            ),
        ),
    )
    telemetry = []
    gateway = type(gateway)(
        registry=registry,
        kernel=kernel,
        approvals=gateway.approvals,
        telemetry=telemetry.append,
    )
    caplog.set_level(logging.DEBUG)

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload=(
            {"count": 7, "idempotency_key": "outcome-key"}
            if result_code is ExecutionResultCode.OUTCOME_UNKNOWN
            else {"count": 7}
        ),
    )

    attempt = await kernel.get_attempt(claim.task_attempt_id)
    touched = {
        "result": result.model_dump(mode="json"),
        "attempt_reconciliation_reference": (
            attempt.reconciliation_reference if attempt is not None else None
        ),
        "logs": caplog.text,
        "telemetry": [event.as_dict() for event in telemetry],
    }
    assert raw_reference not in json.dumps(touched, sort_keys=True)
    if result_code is ExecutionResultCode.OUTCOME_UNKNOWN:
        assert result.reconciliation_reference is not None
        assert result.reconciliation_reference.startswith("sha256.")
    else:
        assert result.reconciliation_reference is None
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        assert raw_reference not in json.dumps(record.metadata_json, sort_keys=True)
