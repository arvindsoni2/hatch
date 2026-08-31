"""Behavioral contracts for the typed, policy-gated execution gateway."""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy import select

from app.runtime.control import (
    ConstraintSet,
    ControlPlane,
    PolicyLayer,
    RoutingPreferences,
)
from app.runtime.contracts import ExecutionResultCode
from app.runtime.contracts import (
    EvaluationPolicy,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    RiskClass,
    TaskSpec,
    WorkflowPolicy,
)
from app.runtime.evaluation import ExecutionRecord
from app.runtime.execution import (
    CapabilityRegistry,
    CapabilityResult,
    ExecutionGateway,
    SideEffectClass,
)
from app.runtime.execution.adapters.llm import (
    StructuredGenerationInput,
    StructuredGenerationOutput,
    register_llm_generate_structured,
)
from app.runtime.workflow import ApprovalManager
from app.runtime_bindings.capabilities import register_product_capabilities

from execution_test_support import (
    NOW,
    RecordingAdapter,
    SyntheticOutput,
    WrongOutput,
    denied_policy_for,
    descriptor,
    gateway_case,
    policy_for,
)
from workflow_test_support import start_and_claim


async def _llm_gateway_case(workflow_runtime, handler):
    kernel, factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=NOW)
    registry = CapabilityRegistry()
    register_llm_generate_structured(registry, handler=handler)
    return (
        ExecutionGateway(
            registry=registry,
            kernel=kernel,
            approvals=ApprovalManager(factory, clock=lambda: NOW),
        ),
        factory,
        claim,
    )


def _llm_policy(
    *,
    data_egress: bool = True,
    allowed_models: frozenset[str] | None = None,
    allowed_providers: frozenset[str] | None = None,
    forced_model: str | None = None,
    approval_required: bool = False,
):
    return ControlPlane().evaluate(
        system=PolicyLayer(
            ConstraintSet(
                data_egress=data_egress,
                allowed_capabilities=frozenset({"llm.generate_structured"}),
                allowed_models=allowed_models,
                allowed_providers=allowed_providers,
                approval_required=approval_required,
            )
        ),
        routing=RoutingPreferences(force_model=forced_model),
    )


async def _structured_success(_payload, _context):
    return StructuredGenerationOutput(result_ref="synthetic-result")


async def _approve_llm_payload(factory, gateway, claim, payload):
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
    assert gateway.approvals is not None
    approval = await gateway.approvals.request(
        workflow_run_id=run.id,
        workflow_step_id=step.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="llm.generate_structured",
        payload=payload,
    )
    assert await gateway.approvals.decide(
        approval.id,
        decided_by="synthetic-user",
        approved=True,
        reason="user_confirmed",
        now=NOW,
    )
    return approval


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


async def test_llm_egress_denial_prevents_adapter_invocation(workflow_runtime) -> None:
    """Would fail if an allowed capability ignored effective data-egress denial."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, factory, claim = await _llm_gateway_case(workflow_runtime, handler)

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(data_egress=False),
        payload={"request_ref": "request-1", "schema_ref": "schema-1"},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "data_egress_denied"
    assert calls == []
    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ExecutionRecord))).all()) == []


async def test_nonforced_required_model_capability_fails_closed_end_to_end(
    workflow_runtime,
) -> None:
    """Would fail if unproven TaskSpec model requirements only gated FORCE."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, _, claim = await _llm_gateway_case(workflow_runtime, handler)
    task = TaskSpec(
        task_id="synthetic.required-model-capability",
        version=1,
        input_model=StructuredGenerationInput,
        output_model=StructuredGenerationOutput,
        context_requirements=(),
        model_requirements=ModelCapabilityRequirements(
            required_capabilities=("structured_output",)
        ),
        risk_class=RiskClass.LOW,
        validators=("synthetic.validator",),
        evaluation_policy=EvaluationPolicy(),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=1),
    )
    policy = ControlPlane().evaluate(
        task=task,
        system=PolicyLayer(
            ConstraintSet(
                data_egress=True,
                allowed_capabilities=frozenset({"llm.generate_structured"}),
                allowed_models=frozenset({"model-a"}),
                allowed_providers=frozenset({"provider-a"}),
            )
        ),
        routing=RoutingPreferences(model_capabilities=frozenset({"structured_output"})),
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=policy,
        payload={
            "request_ref": "request-1",
            "schema_ref": "schema-1",
            "model_id": "model-a",
            "provider": "provider-a",
        },
    )

    assert policy.decision == "DENY"
    assert "model.structured_output_required" in policy.reason_codes
    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert calls == []


async def test_external_side_effect_class_fails_closed_on_egress_denial(
    workflow_runtime,
) -> None:
    """Would fail if external classification relied on a second opt-in egress flag."""
    capability_id = "synthetic.external_read"
    adapter = RecordingAdapter()
    gateway, _, _, claim, _ = await gateway_case(
        workflow_runtime,
        adapter,
        descriptor(
            capability_id,
            side_effect=SideEffectClass.READ_ONLY_EXTERNAL,
        ),
    )
    policy = ControlPlane().evaluate(
        system=PolicyLayer(
            ConstraintSet(
                data_egress=False,
                allowed_capabilities=frozenset({capability_id}),
            )
        )
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id=capability_id,
        policy=policy,
        payload={"count": 7},
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "data_egress_denied"
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    (
        (
            {
                "request_ref": "request-1",
                "schema_ref": "schema-1",
                "model_id": "model-b",
                "provider": "provider-a",
            },
            "model_not_authorized",
        ),
        (
            {
                "request_ref": "request-1",
                "schema_ref": "schema-1",
                "model_id": "model-a",
                "provider": "provider-b",
            },
            "provider_not_authorized",
        ),
    ),
)
async def test_llm_disallowed_model_or_provider_never_reaches_adapter(
    workflow_runtime,
    payload,
    reason_code,
) -> None:
    """Would fail if caller routing fields bypassed model/provider allowlists."""
    calls = []

    async def handler(typed_payload, context):
        calls.append((typed_payload, context))
        return await _structured_success(typed_payload, context)

    gateway, _, claim = await _llm_gateway_case(workflow_runtime, handler)

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
        ),
        payload=payload,
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == reason_code
    assert calls == []


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    (
        (
            {
                "request_ref": "request-1",
                "schema_ref": "schema-1",
                "provider": "provider-a",
            },
            "model_selection_required",
        ),
        (
            {
                "request_ref": "request-1",
                "schema_ref": "schema-1",
                "model_id": "model-a",
            },
            "provider_selection_required",
        ),
    ),
)
async def test_llm_omitted_restricted_routing_never_reaches_adapter(
    workflow_runtime,
    payload,
    reason_code,
) -> None:
    """Would fail if an adapter could resolve an allowlisted route after auth."""
    calls = []

    async def handler(typed_payload, context):
        calls.append((typed_payload, context))
        return await _structured_success(typed_payload, context)

    gateway, _, claim = await _llm_gateway_case(workflow_runtime, handler)

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
        ),
        payload=payload,
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == reason_code
    assert calls == []


async def test_llm_forced_model_mismatch_never_reaches_adapter(
    workflow_runtime,
) -> None:
    """Would fail if a caller-selected model overrode Control Plane force-model."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, _, claim = await _llm_gateway_case(workflow_runtime, handler)

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
            forced_model="model-a",
        ),
        payload={
            "request_ref": "request-1",
            "schema_ref": "schema-1",
            "model_id": "model-b",
            "provider": "provider-a",
        },
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "forced_model_mismatch"
    assert calls == []


async def test_llm_adapter_receives_only_policy_authorized_routing(
    workflow_runtime,
) -> None:
    """Would fail if effective routing were absent from the adapter handoff."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, _, claim = await _llm_gateway_case(workflow_runtime, handler)

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
            forced_model="model-a",
        ),
        payload={
            "request_ref": "request-1",
            "schema_ref": "schema-1",
            "provider": "provider-a",
        },
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert len(calls) == 1
    payload, context = calls[0]
    assert payload.model_id == "model-a"
    assert payload.provider == "provider-a"
    assert context.model_id == "model-a"
    assert context.provider == "provider-a"
    assert context.data_egress is True
    assert context.allowed_models == frozenset({"model-a"})
    assert context.allowed_providers == frozenset({"provider-a"})


async def test_approval_for_effective_forced_route_reaches_llm_adapter(
    workflow_runtime,
) -> None:
    """Would fail if approval were checked against pre-routing caller input."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, factory, claim = await _llm_gateway_case(workflow_runtime, handler)
    caller_payload = {
        "request_ref": "request-1",
        "schema_ref": "schema-1",
        "provider": "provider-a",
    }
    effective_payload = {
        "request_ref": "request-1",
        "schema_ref": "schema-1",
        "model_id": "model-a",
        "provider": "provider-a",
    }
    approval = await _approve_llm_payload(
        factory,
        gateway,
        claim,
        effective_payload,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
            forced_model="model-a",
            approval_required=True,
        ),
        approval=approval,
        payload=caller_payload,
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert len(calls) == 1
    invoked_payload, context = calls[0]
    assert invoked_payload.model_dump(mode="json") == effective_payload
    assert context.model_id == "model-a"


async def test_approval_for_pre_routing_payload_cannot_authorize_forced_route(
    workflow_runtime,
) -> None:
    """Would fail if approval omitted the model injected into executed payload."""
    calls = []

    async def handler(payload, context):
        calls.append((payload, context))
        return await _structured_success(payload, context)

    gateway, factory, claim = await _llm_gateway_case(workflow_runtime, handler)
    caller_payload = {
        "request_ref": "request-1",
        "schema_ref": "schema-1",
        "provider": "provider-a",
    }
    approval = await _approve_llm_payload(
        factory,
        gateway,
        claim,
        caller_payload,
    )

    result = await gateway.invoke(
        claim=claim,
        capability_id="llm.generate_structured",
        policy=_llm_policy(
            allowed_models=frozenset({"model-a"}),
            allowed_providers=frozenset({"provider-a"}),
            forced_model="model-a",
            approval_required=True,
        ),
        approval=approval,
        payload=caller_payload,
    )

    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert result.reason_code == "approval_invalid"
    assert calls == []


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
