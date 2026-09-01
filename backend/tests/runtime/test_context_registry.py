"""Context capability registration contracts."""

from __future__ import annotations

import pytest

from app.runtime.context import ContextRegistry
from app.runtime.context.models import INITIAL_CONTEXT_CAPABILITIES
from app.runtime_bindings.context import register_initial_context_providers


class _JobDescriptionProvider:
    provider_id = "synthetic.job"
    capabilities = ("job.description",)


class _DuplicateJobDescriptionProvider:
    provider_id = "synthetic.duplicate-job"
    capabilities = ("job.description", "job.description")


def test_registry_rejects_duplicate_capability_registration() -> None:
    """A second owner would make declared resolution non-deterministic."""
    registry = ContextRegistry()
    registry.register(_JobDescriptionProvider())

    with pytest.raises(ValueError, match="context_capability_duplicate"):
        registry.register(_JobDescriptionProvider())


def test_registry_rejects_duplicate_capability_in_one_provider() -> None:
    """A malformed provider declaration cannot make ownership ambiguous."""
    with pytest.raises(ValueError, match="context_capability_duplicate"):
        ContextRegistry().register(_DuplicateJobDescriptionProvider())


def test_product_bindings_register_exact_initial_capability_vocabulary() -> None:
    """Generic resolution obtains all product capabilities only through bindings."""
    registry = ContextRegistry()

    register_initial_context_providers(registry)

    assert {
        capability
        for capability in INITIAL_CONTEXT_CAPABILITIES
        if registry.provider_for(capability) is not None
    } == INITIAL_CONTEXT_CAPABILITIES
