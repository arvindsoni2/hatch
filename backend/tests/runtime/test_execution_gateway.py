"""Behavioral contracts for the typed, policy-gated execution gateway."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import CapabilityResult
from app.runtime.execution.adapters.llm import register_llm_generate_structured
from app.runtime_bindings.capabilities import register_product_capabilities

from execution_test_support import (
    RecordingAdapter,
    SyntheticOutput,
    WrongOutput,
    denied_policy_for,
    gateway_case,
    policy_for,
)


async def test_visible_capability_is_not_automatically_authorized(
    workflow_runtime,
) -> None:
    """Would fail if registry visibility bypassed the Control Plane allowlist."""
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(workflow_runtime, adapter)

    result = await gateway.invoke(
        claim=claim,
        capability_id="synthetic.execute",
        policy=denied_policy_for(),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "capability_not_authorized"
    assert adapter.calls == []
    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ExecutionRecord))).all()) == []


async def test_gateway_strictly_validates_payload_and_typed_output(
    workflow_runtime,
) -> None:
    """Would fail if strings were coerced into integers at an untrusted boundary."""
    adapter = RecordingAdapter()
    gateway, _, factory, claim, _ = await gateway_case(workflow_runtime, adapter)

    result = await gateway.invoke(
        claim=claim,
        capability_id="synthetic.execute",
        policy=policy_for("synthetic.execute"),
        payload={"count": "7"},
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "invalid_capability_payload"
    assert adapter.calls == []
    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ExecutionRecord))).all()) == []


async def test_gateway_rejects_adapter_output_that_violates_descriptor(
    workflow_runtime,
) -> None:
    """Would fail if adapter output escaped descriptor-owned strict validation."""
    adapter = RecordingAdapter(
        CapabilityResult.success(WrongOutput(result_ref="bad", count="7"))
    )
    gateway, _, factory, claim, _ = await gateway_case(workflow_runtime, adapter)

    result = await gateway.invoke(
        claim=claim,
        capability_id="synthetic.execute",
        policy=policy_for("synthetic.execute"),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "invalid_capability_result"
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        assert record.result_class == "validation_failure"


async def test_success_is_typed_persisted_then_reported_with_nonfatal_telemetry(
    workflow_runtime,
) -> None:
    """Would fail if telemetry errors changed a correct durable execution result."""
    seen = []
    adapter = RecordingAdapter()
    gateway, kernel, factory, claim, registry = await gateway_case(
        workflow_runtime, adapter
    )

    async def broken_telemetry(event) -> None:
        async with factory.session_factory() as session:
            record = await session.scalar(select(ExecutionRecord))
            assert record is not None
            assert record.result_class == "success"
        seen.append(event)
        raise RuntimeError("synthetic telemetry outage")

    gateway = type(gateway)(
        registry=registry,
        kernel=kernel,
        approvals=gateway.approvals,
        telemetry=broken_telemetry,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id="synthetic.execute",
        policy=policy_for("synthetic.execute"),
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert result.output == SyntheticOutput(result_ref="synthetic-result", count=7)
    assert len(seen) == 1
    async with factory.session_factory() as session:
        record = await session.scalar(select(ExecutionRecord))
        assert record is not None
        assert record.capability_id == "synthetic.execute"
        assert record.result_class == "success"


async def test_only_four_initial_capabilities_are_registered() -> None:
    """Would fail if Task 8 silently exposed extra product or MCP capabilities."""
    from app.runtime.execution import CapabilityRegistry

    async def handler(payload, context):
        return CapabilityResult.success(payload)

    registry = CapabilityRegistry()
    register_llm_generate_structured(registry, handler=handler)
    register_product_capabilities(
        registry,
        local_score_handler=handler,
        render_cv_handler=handler,
        render_cover_letter_handler=handler,
    )

    assert registry.capability_ids() == (
        "artifact.render_cover_letter",
        "artifact.render_cv",
        "job.local_score",
        "llm.generate_structured",
    )


async def test_canaries_never_enter_records_errors_logs_or_telemetry(
    workflow_runtime,
    caplog,
) -> None:
    """Would fail if raw payload, path, or token-like data leaked into metadata."""
    canaries = (
        "RAW-CONTENT-CANARY",
        "/tmp/private-candidate-path",
        "TOKEN-sk-test-canary",
    )
    telemetry = []
    adapter = RecordingAdapter()
    gateway, kernel, factory, claim, registry = await gateway_case(
        workflow_runtime, adapter
    )
    gateway = type(gateway)(
        registry=registry,
        kernel=kernel,
        approvals=gateway.approvals,
        telemetry=telemetry.append,
    )
    caplog.set_level(logging.DEBUG)

    result = await gateway.invoke(
        claim=claim,
        capability_id="synthetic.execute",
        policy=policy_for("synthetic.execute"),
        payload={"count": "not-an-integer", "sensitive_value": " ".join(canaries)},
    )

    assert result.reason_code == "invalid_capability_payload"
    async with factory.session_factory() as session:
        records = list((await session.scalars(select(ExecutionRecord))).all())
    touched = json.dumps(
        {
            "records": [record.metadata_json for record in records],
            "result": {"code": result.code.value, "reason_code": result.reason_code},
            "logs": caplog.text,
            "telemetry": [event.as_dict() for event in telemetry],
        },
        sort_keys=True,
    )
    for canary in canaries:
        assert canary not in touched
