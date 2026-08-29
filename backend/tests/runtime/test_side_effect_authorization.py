"""Approval and authorization contracts for committing capabilities."""

from __future__ import annotations

from dataclasses import replace

from app.runtime.contracts import ExecutionResultCode
from app.runtime.execution import IdempotencyClass, SideEffectClass

from execution_test_support import (
    NOW,
    RecordingAdapter,
    descriptor,
    gateway_case,
    policy_for,
)


async def test_commit_capability_requires_valid_approval(workflow_runtime) -> None:
    """Would fail if REQUIRE_APPROVAL reached a committing adapter without a grant."""
    capability_id = "synthetic.commit"
    adapter = RecordingAdapter()
    gateway, _, _, claim, _ = await gateway_case(
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
        policy=policy_for(capability_id, approval_required=True),
        payload={"count": 7, "idempotency_key": "approval-test-key"},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "approval_required"
    assert adapter.calls == []


async def test_approval_for_payload_a_does_not_authorize_b(workflow_runtime) -> None:
    """Would fail if an approval ID authorized a mutated committing payload."""
    capability_id = "synthetic.commit"
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )
    # The real approval manager derives and checks the durable run/step scope.
    from app.runtime.workflow import (
        TaskAttemptRecord,
        WorkflowRunRecord,
        WorkflowStepRecord,
    )

    async with factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
        assert attempt is not None
        step = await uow.session.get(WorkflowStepRecord, attempt.workflow_step_id)
        assert step is not None
        run = await uow.session.get(WorkflowRunRecord, step.workflow_run_id)
        assert run is not None
    payload_a = {"count": 7, "idempotency_key": "approval-test-key"}
    approval = await gateway.approvals.request(
        workflow_run_id=run.id,
        workflow_step_id=step.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id=capability_id,
        payload=payload_a,
    )
    assert await gateway.approvals.decide(
        approval.id,
        decided_by="synthetic-user",
        approved=True,
        reason="user_confirmed",
        now=NOW,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id, approval_required=True),
        approval=approval,
        payload={"count": 8, "idempotency_key": "approval-test-key"},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "approval_invalid"
    assert adapter.calls == []


async def test_valid_payload_bound_approval_reaches_committing_adapter(
    workflow_runtime,
) -> None:
    """Would fail if exact durable approval scope were not accepted at the gateway."""
    capability_id = "synthetic.commit"
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )
    from app.runtime.workflow import (
        TaskAttemptRecord,
        WorkflowRunRecord,
        WorkflowStepRecord,
    )

    async with factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
        assert attempt is not None
        step = await uow.session.get(WorkflowStepRecord, attempt.workflow_step_id)
        assert step is not None
        run = await uow.session.get(WorkflowRunRecord, step.workflow_run_id)
        assert run is not None
    payload = {"count": 7, "idempotency_key": "approved-commit-key"}
    assert gateway.approvals is not None
    approval = await gateway.approvals.request(
        workflow_run_id=run.id,
        workflow_step_id=step.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id=capability_id,
        payload=payload,
    )
    assert await gateway.approvals.decide(
        approval.id,
        decided_by="synthetic-user",
        approved=True,
        reason="user_confirmed",
        now=NOW,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id, approval_required=True),
        approval=approval,
        payload=payload,
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert len(adapter.calls) == 1


async def test_inconsistent_allow_decision_cannot_bypass_effective_approval(
    workflow_runtime,
) -> None:
    """Would fail if an ALLOW label overrode stricter effective constraints."""
    capability_id = "synthetic.commit"
    adapter = RecordingAdapter()
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )
    inconsistent = replace(
        policy_for(capability_id, approval_required=True),
        decision="ALLOW",
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=inconsistent,
        payload={"count": 7, "idempotency_key": "must-not-run"},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "approval_required"
    assert adapter.calls == []


async def test_noncanonical_approval_payload_returns_typed_failure(
    workflow_runtime,
) -> None:
    """Would fail if canonical approval hashing exceptions escaped the gateway."""
    capability_id = "synthetic.commit"
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency=IdempotencyClass.CHECK_BEFORE_RETRY,
        ),
    )
    from app.runtime.workflow import (
        TaskAttemptRecord,
        WorkflowRunRecord,
        WorkflowStepRecord,
    )

    async with factory.transaction() as uow:
        attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
        assert attempt is not None
        step = await uow.session.get(WorkflowStepRecord, attempt.workflow_step_id)
        assert step is not None
        run = await uow.session.get(WorkflowRunRecord, step.workflow_run_id)
        assert run is not None
    approved_payload = {"count": 7, "idempotency_key": "approval-key"}
    assert gateway.approvals is not None
    approval = await gateway.approvals.request(
        workflow_run_id=run.id,
        workflow_step_id=step.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id=capability_id,
        payload=approved_payload,
    )
    assert await gateway.approvals.decide(
        approval.id,
        decided_by="synthetic-user",
        approved=True,
        reason="user_confirmed",
        now=NOW,
    )
    oversized_canary = "TOKEN-approval-canary-" + ("x" * (65 * 1024))

    leaked_exception = None
    result = None
    try:
        result = await gateway.invoke(
            claim=claim,
            capability_id=capability_id,
            policy=policy_for(capability_id, approval_required=True),
            approval=approval,
            payload={
                "count": 7,
                "idempotency_key": "approval-key",
                "sensitive_value": oversized_canary,
            },
        )
    except Exception as error:  # The assertion below proves this must not happen.
        leaked_exception = error

    assert leaked_exception is None, "gateway leaked approval validation exception"
    assert result is not None
    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "invalid_approval_payload"
    assert oversized_canary not in result.model_dump_json()
    assert adapter.calls == []
