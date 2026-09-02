"""Hard bounds and strict metadata-only controls for intelligence records."""

from __future__ import annotations

import pytest

from app.runtime.events.repository import MetadataOnlyViolation, enforce_metadata_only
from app.runtime.intelligence import (
    EvidenceObservation,
    ModelDescriptor,
    ModelEvidence,
    ModelRegistry,
    RoutingRequirements,
)


def test_registry_and_metadata_reject_unbounded_or_body_like_values() -> None:
    """Allowing a model swarm or innocent-key model body must make this test fail."""
    descriptors = tuple(
        ModelDescriptor(f"model-{index}", "1", "llamacpp", f"native-{index}")
        for index in range(33)
    )

    with pytest.raises(ValueError, match="registry"):
        ModelRegistry(descriptors)
    with pytest.raises(MetadataOnlyViolation, match="body-like"):
        enforce_metadata_only({"label": "x" * 513})


@pytest.mark.parametrize("task_version", [1.0, True, 1_000_001])
def test_observation_rejects_non_integer_or_unbounded_task_version(
    task_version,
) -> None:
    with pytest.raises(ValueError, match="task_version"):
        EvidenceObservation(
            observation_id="observation-1",
            task_id="evidence.task",
            task_version=task_version,
            model_id="model-1",
            model_version="1",
            provider="llamacpp",
            quality_score=0.5,
            sample_size=1,
        )


@pytest.mark.parametrize("sample_size", [1.0, True])
def test_observation_rejects_non_integer_sample_size(sample_size) -> None:
    with pytest.raises(ValueError, match="sample_size"):
        EvidenceObservation(
            observation_id="observation-1",
            task_id="evidence.task",
            task_version=1,
            model_id="model-1",
            model_version="1",
            provider="llamacpp",
            quality_score=0.5,
            sample_size=sample_size,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_version", 1.0),
        ("task_version", True),
        ("task_version", 1_000_001),
        ("sample_size", 1.0),
        ("sample_size", True),
        ("qualification_version", 1.0),
        ("qualification_version", True),
        ("minimum_sample_size", 1.0),
        ("minimum_sample_size", True),
    ],
)
def test_model_evidence_rejects_non_integer_or_unbounded_fields(field, value) -> None:
    values = {
        "evidence_id": "evidence." + "0" * 24,
        "task_id": "evidence.task",
        "task_version": 1,
        "model_id": "model-1",
        "model_version": "1",
        "provider": "llamacpp",
        "quality_score": 0.5,
        "sample_size": 1,
        "qualification_id": "benchmark",
        "qualification_version": 1,
        "minimum_sample_size": 1,
        "observation_ids": ("observation-1",),
    }
    values[field] = value

    with pytest.raises(ValueError):
        ModelEvidence(**values)


@pytest.mark.parametrize("quality_floor", [True, float("nan"), float("inf")])
def test_routing_requirements_reject_invalid_quality(quality_floor) -> None:
    with pytest.raises(ValueError, match="quality_floor"):
        RoutingRequirements("evidence.task", 1, quality_floor=quality_floor)


@pytest.mark.parametrize("minimum_context_window", [1.0, True, 2_000_001])
def test_routing_requirements_reject_invalid_context_window(
    minimum_context_window,
) -> None:
    with pytest.raises(ValueError, match="minimum_context_window"):
        RoutingRequirements(
            "evidence.task", 1, minimum_context_window=minimum_context_window
        )


@pytest.mark.parametrize("quality_score", [True, float("nan"), float("inf")])
def test_descriptor_rejects_invalid_quality(quality_score) -> None:
    with pytest.raises(ValueError, match="quality_score"):
        ModelDescriptor(
            "model-1", "1", "llamacpp", "native", quality_score=quality_score
        )


@pytest.mark.parametrize("base_rank", [True, float("nan"), float("inf"), 1_000_001])
def test_descriptor_rejects_invalid_base_rank(base_rank) -> None:
    with pytest.raises(ValueError, match="base_rank"):
        ModelDescriptor("model-1", "1", "llamacpp", "native", base_rank=base_rank)


@pytest.mark.parametrize("context_window", [1.0, True, 2_000_001])
def test_descriptor_rejects_invalid_context_window(context_window) -> None:
    with pytest.raises(ValueError, match="context_window"):
        ModelDescriptor(
            "model-1", "1", "llamacpp", "native", context_window=context_window
        )
