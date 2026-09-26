"""Contract tests for deterministic, descriptor-backed model routing."""

from __future__ import annotations

from app.runtime.control import (
    ConstraintSet,
    ControlPlane,
    PolicyLayer,
    RoutingPreferences,
)
from app.runtime.contracts import ModelCapabilityRequirements
from app.runtime.intelligence import (
    ModelDescriptor,
    ModelRegistry,
    ModelRouter,
    RoutingPreference,
    RoutingRequirements,
)
import pytest


def _router() -> ModelRouter:
    return ModelRouter(
        ModelRegistry(
            (
                ModelDescriptor(
                    model_id="local-structured",
                    version="1",
                    provider="llamacpp",
                    model_name="qwen/local:4b",
                    capabilities=frozenset({"structured_output", "tool_calling"}),
                    quality_score=0.8,
                    base_rank=10,
                    local_or_cloud="local",
                ),
                ModelDescriptor(
                    model_id="cloud-plain",
                    version="1",
                    provider="openai",
                    model_name="gpt/provider-name",
                    capabilities=frozenset(),
                    structured_output=False,
                    quality_score=0.95,
                    base_rank=20,
                    local_or_cloud="cloud",
                ),
            )
        )
    )


def _requirements() -> RoutingRequirements:
    return RoutingRequirements(
        task_id="router.structured",
        task_version=1,
        required_capabilities=frozenset({"structured_output"}),
        quality_floor=0.5,
    )


def _policy():
    return ControlPlane().evaluate(
        security_policy=PolicyLayer(
            ConstraintSet(
                data_egress=False,
                allowed_models=frozenset({"local-structured", "cloud-plain"}),
                allowed_providers=frozenset({"llamacpp", "openai"}),
            )
        )
    )


def test_router_records_every_candidate_and_exclusion() -> None:
    """Skipping a candidate or its reason code must make this test fail."""
    decision = _router().route(_requirements(), _policy(), RoutingPreference.auto())

    assert [stage.name for stage in decision.stages] == [
        "capability",
        "quality",
        "policy",
        "evidence",
        "fallback",
    ]
    assert [candidate.model_id for candidate in decision.candidates] == [
        "cloud-plain",
        "local-structured",
    ]
    assert all(
        candidate.excluded_reason_codes is not None for candidate in decision.candidates
    )
    assert decision.selected_model_id == "local-structured"
    assert decision.candidates[0].excluded_reason_codes == (
        "capability.structured_output_missing",
        "privacy.data_egress_denied",
    )


def test_prefer_only_boosts_an_eligible_model() -> None:
    """Boosting a capability-ineligible preferred model must make this test fail."""
    decision = _router().route(
        _requirements(),
        _policy(),
        RoutingPreference.prefer("cloud-plain"),
    )

    assert decision.selected_model_id == "local-structured"
    assert decision.candidates[0].final_rank is None


def test_force_filters_only_after_mandatory_gates() -> None:
    """Selecting a forced model before capability gating must make this test fail."""
    decision = _router().route(
        _requirements(),
        _policy(),
        RoutingPreference.force("cloud-plain"),
    )

    assert decision.selected_model_id is None
    forced = next(
        item for item in decision.candidates if item.model_id == "cloud-plain"
    )
    assert "capability.structured_output_missing" in forced.excluded_reason_codes


def test_untrusted_routing_preferences_never_prove_capabilities() -> None:
    """Treating compatibility capability claims as trusted must make this test fail."""
    policy = ControlPlane().evaluate(
        task=None,
        routing=RoutingPreferences(model_capabilities=frozenset({"structured_output"})),
    )

    decision = _router().route(
        RoutingRequirements(
            task_id="router.untrusted",
            task_version=1,
            required_capabilities=ModelCapabilityRequirements(
                required_capabilities=("structured_output",)
            ).required_capabilities,
        ),
        policy,
        RoutingPreference.auto(),
    )

    assert decision.selected_model_id == "local-structured"


def test_registry_selection_proof_cannot_be_forged_or_replayed_to_another_registry() -> (
    None
):
    """Accepting a caller-built descriptor as authority must make this test fail."""
    registry = _router()._registry
    descriptor = registry.get("local-structured")
    assert descriptor is not None
    proof = registry.issue_selection(descriptor)

    assert registry.verify_selection(proof) == descriptor
    assert ModelRegistry((descriptor,)).verify_selection(proof) is None
    assert registry.verify_selection(object()) is None


def test_context_privacy_and_bounded_fallback_are_independent_gates() -> None:
    """Ignoring context/privacy or accepting an unbounded fallback list must fail."""
    router = _router()
    decision = router.route(
        RoutingRequirements(
            task_id="router.private-context",
            task_version=1,
            required_capabilities=frozenset({"structured_output"}),
            minimum_context_window=32_000,
            privacy_requirement="local",
        ),
        _policy(),
        RoutingPreference.auto(fallback_model_ids=("cloud-plain",)),
    )

    local = next(
        item for item in decision.candidates if item.model_id == "local-structured"
    )
    cloud = next(item for item in decision.candidates if item.model_id == "cloud-plain")
    assert "capability.context_window_too_small" in local.excluded_reason_codes
    assert "privacy.requirement_not_met" in cloud.excluded_reason_codes
    assert decision.fallback_model_ids == ()
    with pytest.raises(ValueError, match="fallback"):
        RoutingPreference.auto(
            fallback_model_ids=tuple(f"model-{item}" for item in range(9))
        )


def test_fallback_chain_is_ordered_and_force_never_falls_back() -> None:
    """Replacing requested fallback order with rank order must make this test fail."""
    router = ModelRouter(
        ModelRegistry(
            (
                ModelDescriptor(
                    "model-a", "1", "llamacpp", "a", local_or_cloud="local"
                ),
                ModelDescriptor(
                    "model-b", "1", "llamacpp", "b", local_or_cloud="local"
                ),
                ModelDescriptor(
                    "model-c", "1", "llamacpp", "c", local_or_cloud="local"
                ),
            )
        )
    )
    requirements = RoutingRequirements(task_id="router.fallback", task_version=1)
    auto = router.route(
        requirements,
        None,
        RoutingPreference.auto(fallback_model_ids=("model-c", "model-b")),
    )
    forced = router.route(
        requirements,
        None,
        RoutingPreference.force("model-a", fallback_model_ids=("model-c",)),
    )

    assert auto.fallback_model_ids == ("model-b",)
    assert forced.fallback_model_ids == ()
