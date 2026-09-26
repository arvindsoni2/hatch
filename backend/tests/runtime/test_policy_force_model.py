"""Behavioral contracts for forced-model policy decisions."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.runtime.control import (
    ConstraintSet,
    ControlPlane,
    PolicyLayer,
    RoutingPreferences,
)
from app.runtime.contracts import (
    EvaluationPolicy,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    RiskClass,
    TaskSpec,
    WorkflowPolicy,
)
from app.runtime.intelligence import ModelDescriptor, ModelRegistry


class _Input(BaseModel):
    value: str


class _Output(BaseModel):
    value: str


def _requires_structured_output() -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="control.structured-output",
        version=1,
        input_model=_Input,
        output_model=_Output,
        context_requirements=(),
        model_requirements=ModelCapabilityRequirements(
            required_capabilities=("structured_output",)
        ),
        risk_class=RiskClass.LOW,
        validators=("control.validator",),
        evaluation_policy=EvaluationPolicy(max_evaluations=1),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=1),
    )


@pytest.fixture
def control_plane() -> ControlPlane:
    return ControlPlane()


def test_force_model_remains_subject_to_quality_and_policy(
    control_plane: ControlPlane,
) -> None:
    """Skipping forced-model capability validation must make this test fail."""
    decision = control_plane.evaluate(
        task=_requires_structured_output(),
        routing=RoutingPreferences(force_model="model-x"),
    )

    assert decision.decision == "DENY"
    assert "model.structured_output_required" in decision.reason_codes


def test_force_model_cannot_bypass_an_earlier_allowlist(
    control_plane: ControlPlane,
) -> None:
    """Ignoring an earlier model allowlist when forcing a model must make this fail."""
    decision = control_plane.evaluate(
        security_policy=PolicyLayer(
            constraints=ConstraintSet(allowed_models=frozenset({"model-a"}))
        ),
        routing=RoutingPreferences(
            force_model="model-x",
            model_capabilities=frozenset({"structured_output"}),
        ),
    )

    assert decision.decision == "DENY"
    assert "model.force_not_allowed" in decision.reason_codes


def test_untrusted_routing_capability_claim_cannot_authorize_forced_model(
    control_plane: ControlPlane,
) -> None:
    """Treating routing claims as proof of model quality must fail this test."""
    decision = control_plane.evaluate(
        task=_requires_structured_output(),
        routing=RoutingPreferences(
            force_model="model-x",
            model_capabilities=frozenset({"structured_output"}),
        ),
    )

    assert decision.decision == "DENY"
    assert "model.structured_output_required" in decision.reason_codes


def test_trusted_descriptor_capabilities_are_the_only_capability_handoff() -> None:
    """Ignoring the registry-owned capability handoff must make this test fail."""
    registry = ModelRegistry(
        (
            ModelDescriptor(
                model_id="model-x",
                version="1",
                provider="llamacpp",
                model_name="native",
                capabilities=frozenset({"structured_output"}),
                local_or_cloud="local",
            ),
        )
    )
    descriptor = registry.get("model-x")
    assert descriptor is not None
    decision = ControlPlane(model_registry=registry).evaluate(
        task=_requires_structured_output(),
        routing=RoutingPreferences(force_model="model-x"),
        selection_proof=registry.issue_selection(descriptor),
    )

    assert decision.decision == "ALLOW"


def test_control_rejects_a_duck_typed_selection_verifier() -> None:
    """A caller must not be able to provide its own proof verifier."""

    class ForgedVerifier:
        def verify_selection(self, _proof: object) -> object:
            raise AssertionError("must never be called")

    with pytest.raises(TypeError, match="ModelRegistry"):
        ControlPlane(model_registry=ForgedVerifier())


def test_model_registry_cannot_be_subclassed_or_monkeypatched() -> None:
    with pytest.raises(TypeError, match="final"):

        class ForgedRegistry(ModelRegistry):
            pass

    registry = ModelRegistry(())
    with pytest.raises(AttributeError):
        registry.verify_selection = lambda _proof: object()
    with pytest.raises(TypeError, match="immutable"):
        ModelRegistry.verify_selection = lambda _registry, _proof: object()
    with pytest.raises(TypeError, match="immutable"):
        del ModelRegistry.verify_selection


def test_control_composition_verifier_fields_are_immutable() -> None:
    control = ControlPlane(model_registry=ModelRegistry(()))
    for name in ("_verify_selection", "_model_registry"):
        with pytest.raises((AttributeError, TypeError)):
            setattr(control, name, None)
        with pytest.raises((AttributeError, TypeError)):
            delattr(control, name)


def test_cross_registry_proof_fails_closed() -> None:
    descriptor = ModelDescriptor(
        model_id="model-x",
        version="1",
        provider="llamacpp",
        model_name="native",
        capabilities=frozenset({"structured_output"}),
        local_or_cloud="local",
    )
    issuer = ModelRegistry((descriptor,))
    verifier = ModelRegistry((descriptor,))

    decision = ControlPlane(model_registry=verifier).evaluate(
        task=_requires_structured_output(),
        routing=RoutingPreferences(force_model="model-x"),
        selection_proof=issuer.issue_selection(descriptor),
    )

    assert decision.decision == "DENY"
    assert "model.structured_output_required" in decision.reason_codes


def test_approval_requirement_has_its_own_deterministic_decision(
    control_plane: ControlPlane,
) -> None:
    """Returning ALLOW for an approval-required policy must fail this test."""
    decision = control_plane.evaluate(
        system=PolicyLayer(constraints=ConstraintSet(approval_required=True)),
        user=PolicyLayer(constraints=ConstraintSet(approval_required=False)),
    )

    assert decision.decision == "REQUIRE_APPROVAL"
    assert "approval.required" in decision.reason_codes


@pytest.mark.parametrize(
    ("constraints", "reason_code"),
    [
        (
            ConstraintSet(allowed_providers=frozenset()),
            "provider.no_allowed_providers",
        ),
        (ConstraintSet(allowed_models=frozenset()), "model.no_allowed_models"),
        (
            ConstraintSet(allowed_capabilities=frozenset()),
            "capability.no_allowed_capabilities",
        ),
    ],
)
def test_empty_folded_allowlist_denies_deterministically(
    control_plane: ControlPlane,
    constraints: ConstraintSet,
    reason_code: str,
) -> None:
    """Allowing an empty final allowlist must fail this test."""
    decision = control_plane.evaluate(security_policy=PolicyLayer(constraints))

    assert decision.decision == "DENY"
    assert reason_code in decision.reason_codes
