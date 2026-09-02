"""Hard bounds and strict metadata-only controls for intelligence records."""

from __future__ import annotations

import pytest

from app.runtime.events.repository import MetadataOnlyViolation, enforce_metadata_only
from app.runtime.intelligence import ModelDescriptor, ModelRegistry


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
