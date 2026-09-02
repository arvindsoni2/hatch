"""Evidence must be explicitly promoted before it affects routing."""

from __future__ import annotations

from types import SimpleNamespace

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
import pytest


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


async def test_explicit_qualification_promotes_bounded_evidence() -> None:
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

    class DurableStore:
        async def record_promoted_model_evidence(self, evidence, _observations):
            self.evidence = evidence

    durable = DurableStore()
    promoted = await promote_model_evidence(
        store,
        durable,
        ("observation-2",),
        qualification={
            "minimum_sample_size": 10,
            "qualification_id": "benchmark-v1",
            "qualification_version": 1,
        },
    )

    assert promoted.model_id == "other-model"
    assert (
        router.route(requirements, None, RoutingPreference.auto()).selected_model_id
        == "other-model"
    )


async def test_promotion_rejects_duplicate_ids_negative_threshold_and_direct_activation() -> (
    None
):
    """Activating unqualified or duplicated observations must make this test fail."""
    _router, store = _router_and_store()
    observation = EvidenceObservation(
        observation_id="observation-3",
        task_id="evidence.task",
        task_version=1,
        model_id="other-model",
        model_version="1",
        provider="llamacpp",
        quality_score=0.9,
        sample_size=20,
    )
    store.record(observation)

    with pytest.raises(ValueError, match="duplicate"):
        await promote_model_evidence(
            store,
            object(),
            ("observation-3", "observation-3"),
            qualification={
                "minimum_sample_size": 1,
                "qualification_id": "benchmark",
                "qualification_version": 1,
            },
        )
    with pytest.raises(ValueError, match="minimum_sample_size"):
        await promote_model_evidence(
            store,
            object(),
            ("observation-3",),
            qualification={
                "minimum_sample_size": -1,
                "qualification_id": "benchmark",
                "qualification_version": 1,
            },
        )
    assert not hasattr(store, "promote")


async def test_persistence_failure_never_activates_evidence() -> None:
    _router, store = _router_and_store()
    store.record(
        EvidenceObservation(
            observation_id="observation-4",
            task_id="evidence.task",
            task_version=1,
            model_id="other-model",
            model_version="1",
            provider="llamacpp",
            quality_score=0.9,
            sample_size=20,
        )
    )

    class FailingStore:
        async def record_promoted_model_evidence(self, _evidence, _observations):
            raise RuntimeError("flush failed")

    with pytest.raises(RuntimeError, match="flush failed"):
        await promote_model_evidence(
            store,
            FailingStore(),
            ("observation-4",),
            {
                "minimum_sample_size": 1,
                "qualification_id": "benchmark",
                "qualification_version": 1,
            },
        )
    assert store.snapshot_id() == "evidence.none"


async def test_replay_requires_exact_id_aggregate_and_observation_lineage() -> None:
    _router, source = _router_and_store()
    observation = EvidenceObservation(
        observation_id="observation-5",
        task_id="evidence.task",
        task_version=1,
        model_id="other-model",
        model_version="1",
        provider="llamacpp",
        quality_score=0.9,
        sample_size=20,
    )
    source.record(observation)

    class DurableStore:
        async def record_promoted_model_evidence(self, evidence, _observations):
            self.evidence = evidence

    durable = DurableStore()
    evidence = await promote_model_evidence(
        source,
        durable,
        ("observation-5",),
        {
            "minimum_sample_size": 1,
            "qualification_id": "benchmark",
            "qualification_version": 1,
        },
    )
    row = SimpleNamespace(
        id=evidence.evidence_id,
        task_id=evidence.task_id,
        task_version=evidence.task_version,
        model_id=evidence.model_id,
        model_version=evidence.model_version,
        provider=evidence.provider,
        qualification_id=evidence.qualification_id,
        qualification_version=evidence.qualification_version,
        minimum_sample_size=evidence.minimum_sample_size,
        evidence_type="promoted",
        observation_ids_json=list(evidence.observation_ids),
        quality_score=evidence.quality_score,
        sample_size=evidence.sample_size,
    )

    class Loader:
        async def load_promoted_model_evidence(self):
            return [row]

        async def load_routing_observations(self, _ids):
            return [
                SimpleNamespace(
                    id=observation.observation_id,
                    routing_observation_type="routing_observation",
                    task_id=observation.task_id,
                    task_version=observation.task_version,
                    model_id=observation.model_id,
                    model_version=observation.model_version,
                    provider=observation.provider,
                    quality_score=observation.quality_score,
                    sample_size=observation.sample_size,
                )
            ]

    assert (
        await EvidenceStore.from_evaluation_store(Loader())
    ).snapshot_id() != "evidence.none"
    for field, value in (
        ("id", "evidence.forged"),
        ("sample_size", 1),
        ("observation_ids_json", ["missing"]),
    ):
        tampered = SimpleNamespace(**vars(row))
        setattr(tampered, field, value)

        class TamperedLoader(Loader):
            async def load_promoted_model_evidence(self):
                return [tampered]

        assert (
            await EvidenceStore.from_evaluation_store(TamperedLoader())
        ).snapshot_id() == "evidence.none"
