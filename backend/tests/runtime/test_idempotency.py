"""Idempotency and replay-safety contracts for capability invocation."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import CapabilityResult, IdempotencyClass

from execution_test_support import (
    RecordingAdapter,
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
