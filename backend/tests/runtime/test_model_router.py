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
