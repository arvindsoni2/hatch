"""Idempotency and replay-safety contracts for capability invocation."""

from __future__ import annotations

import json
import hashlib

import pytest
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select

from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import (
    CapabilityDescriptor,
    CapabilityRegistry,
    CapabilityResult,
    IdempotencyClass,
    SideEffectClass,
)

from execution_test_support import (
    RecordingAdapter,
    SyntheticOutput,
    descriptor,
    gateway_case,
    policy_for,
)


async def test_keyed_capability_never_invokes_without_idempotency_key(
    workflow_runtime,
) -> None:
    """Would fail if a keyed adapter could execute without replay protection."""
    capability_id = "synthetic.keyed"
    adapter = RecordingAdapter()
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(capability_id, idempotency=IdempotencyClass.IDEMPOTENT_WITH_KEY),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "idempotency_key_required"
    assert adapter.calls == []


async def test_idempotency_key_reaches_adapter_but_only_hash_is_persisted(
    workflow_runtime,
) -> None:
    """Would fail if a raw replay token leaked into durable execution metadata."""
    capability_id = "synthetic.keyed"
    raw_key = "TOKEN-idempotency-canary"
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(capability_id, idempotency=IdempotencyClass.IDEMPOTENT_WITH_KEY),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7, "idempotency_key": raw_key},
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert adapter.calls[0][1].idempotency_key == raw_key
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
    serialized = json.dumps(record.metadata_json, sort_keys=True)
    assert raw_key not in serialized
    assert record.metadata_json["idempotency_key_hash"].startswith("sha256.")


async def test_non_retryable_side_effect_cannot_be_reclassified_retryable(
    workflow_runtime,
) -> None:
    """Would fail if adapter-controlled retry advice widened descriptor policy."""
    capability_id = "synthetic.nonretryable"
    adapter = RecordingAdapter(
        CapabilityResult(
            code=ExecutionResultCode.TRANSIENT_FAILURE,
            reason_code="provider_unavailable",
            retry_allowed=True,
        )
    )
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            idempotency=IdempotencyClass.NON_RETRYABLE_SIDE_EFFECT,
        ),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.TRANSIENT_FAILURE
    assert result.retry_allowed is False


class _IgnoringExtraInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    count: int


class _NoKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


class _NormalizedKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower()


async def test_gateway_rejects_extras_even_when_input_model_would_ignore_them(
    workflow_runtime,
) -> None:
    """Would fail if descriptor model configuration could silently drop input fields."""
    capability_id = "synthetic.ignore_extra"
    adapter = RecordingAdapter()
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        CapabilityDescriptor(
            capability_id=capability_id,
            version=1,
            input_model=_IgnoringExtraInput,
            output_model=SyntheticOutput,
            side_effect_class=SideEffectClass.PURE,
            idempotency_class=IdempotencyClass.IDEMPOTENT,
            default_timeout_seconds=1.0,
        ),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id),
        payload={"count": 7, "ignored_canary": "TOKEN-ignored-extra"},
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "invalid_capability_payload"
    assert adapter.calls == []


def test_keyed_descriptor_requires_typed_idempotency_key_field() -> None:
    """Would fail if keyed registration accepted a schema with no typed key."""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="idempotency_key"):
        registry.register(
            CapabilityDescriptor(
                capability_id="synthetic.missing_key_contract",
                version=1,
                input_model=_NoKeyInput,
                output_model=SyntheticOutput,
                side_effect_class=SideEffectClass.COMMIT_SIDE_EFFECT,
                idempotency_class=IdempotencyClass.CHECK_BEFORE_RETRY,
                default_timeout_seconds=1.0,
            ),
            RecordingAdapter(),
        )


async def test_normalized_typed_key_is_shared_by_approval_context_and_persistence(
    workflow_runtime,
) -> None:
    """Would fail if approval used typed input while adapter context used the raw key."""
    capability_id = "synthetic.normalized_key"
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        CapabilityDescriptor(
            capability_id=capability_id,
            version=1,
            input_model=_NormalizedKeyInput,
            output_model=SyntheticOutput,
            side_effect_class=SideEffectClass.COMMIT_SIDE_EFFECT,
            idempotency_class=IdempotencyClass.CHECK_BEFORE_RETRY,
            default_timeout_seconds=1.0,
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
    normalized_payload = {"count": 7, "idempotency_key": "normalized-key"}
    assert gateway.approvals is not None
    approval = await gateway.approvals.request(
        workflow_run_id=run.id,
        workflow_step_id=step.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id=capability_id,
        payload=normalized_payload,
    )
    assert await gateway.approvals.decide(
        approval.id,
        decided_by="synthetic-user",
        approved=True,
        reason="user_confirmed",
        now=claim.claimed_at,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy_for(capability_id, approval_required=True),
        approval=approval,
        payload={"count": 7, "idempotency_key": "  Normalized-Key  "},
    )

    assert result.code is ExecutionResultCode.SUCCESS
    typed_payload, context = adapter.calls[0]
    assert typed_payload.model_dump(mode="json") == normalized_payload
    assert context.idempotency_key == "normalized-key"
    expected_hash = "sha256." + hashlib.sha256(b"normalized-key").hexdigest()
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
    assert record.metadata_json["idempotency_key_hash"] == expected_hash
