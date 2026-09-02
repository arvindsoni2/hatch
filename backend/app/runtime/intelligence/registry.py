"""Trusted configured-model registry; no provider client is created here."""

from __future__ import annotations

from .models import ModelDescriptor


class ModelRegistry:
    """An immutable, stable-ID lookup over known configured model descriptors."""

    def __init__(
        self, descriptors: tuple[ModelDescriptor, ...] | list[ModelDescriptor]
    ) -> None:
        indexed = {descriptor.model_id: descriptor for descriptor in descriptors}
        if len(indexed) != len(descriptors):
            raise ValueError("model descriptors must have unique model_id values")
        self._descriptors = indexed

    @classmethod
    def from_configured_models(cls) -> "ModelRegistry":
        """Wrap current profile configuration without constructing a provider client."""
        from app.agents.tools.llm_factory import configured_model_catalog

        return cls(
            tuple(ModelDescriptor(**item) for item in configured_model_catalog())
        )

    def get(self, model_id: str) -> ModelDescriptor | None:
        return self._descriptors.get(model_id)

    def descriptors(self) -> tuple[ModelDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))
