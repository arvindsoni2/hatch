"""Ambiguous-outcome and late-worker fencing contracts for the gateway."""

from __future__ import annotations

from datetime import timedelta

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
