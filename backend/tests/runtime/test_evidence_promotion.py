"""Evidence must be explicitly promoted before it affects routing."""

from __future__ import annotations

from app.runtime.intelligence import (
    EvidenceObservation,
    EvidenceStore,
    ModelDescriptor,
    ModelRegistry,
    ModelRouter,
    RoutingPreference,
    RoutingRequirements,
    promote_model_evidence,
)


def _router_and_store() -> tuple[ModelRouter, EvidenceStore]:
    store = EvidenceStore()
    router = ModelRouter(
        ModelRegistry(
            (
                ModelDescriptor(
                    model_id="first-model",
                    version="1",
                    provider="llamacpp",
                    model_name="first/native",
                    capabilities=frozenset({"structured_output"}),
                    quality_score=0.8,
                    base_rank=10,
                    local_or_cloud="local",
                ),
                ModelDescriptor(
                    model_id="other-model",
                    version="1",
                    provider="llamacpp",
                    model_name="other/native",
                    capabilities=frozenset({"structured_output"}),
                    quality_score=0.8,
                    base_rank=5,
                    local_or_cloud="local",
                ),
            )
        ),
        evidence_store=store,
    )
    return router, store


def test_observation_does_not_change_routing_until_promoted() -> None:
    """Making recorded observations routing-active must make this test fail."""
    router, observation_store = _router_and_store()
    requirements = RoutingRequirements(
        task_id="evidence.task",
        task_version=1,
        required_capabilities=frozenset({"structured_output"}),
    )
    before = router.route(
        requirements, None, RoutingPreference.auto()
    ).selected_model_id
    observation_store.record(
        EvidenceObservation(
            observation_id="observation-1",
            task_id="evidence.task",
            task_version=1,
            model_id="other-model",
            model_version="1",
            provider="llamacpp",
            quality_score=0.99,
            sample_size=20,
        )
    )

    assert (
        router.route(requirements, None, RoutingPreference.auto()).selected_model_id
        == before
    )


def test_explicit_qualification_promotes_bounded_evidence() -> None:
    """Ranking an unqualified observation must make this test fail."""
    router, store = _router_and_store()
    requirements = RoutingRequirements(
        task_id="evidence.task",
        task_version=1,
        required_capabilities=frozenset({"structured_output"}),
    )
    store.record(
        EvidenceObservation(
            observation_id="observation-2",
            task_id="evidence.task",
            task_version=1,
            model_id="other-model",
            model_version="1",
            provider="llamacpp",
            quality_score=0.99,
            sample_size=20,
        )
    )

    promoted = promote_model_evidence(
        store,
        ("observation-2",),
        qualification={"minimum_sample_size": 10, "qualification_id": "benchmark-v1"},
    )

    assert promoted.model_id == "other-model"
    assert (
        router.route(requirements, None, RoutingPreference.auto()).selected_model_id
        == "other-model"
    )
