"""Trusted configured-model registry; no provider client is created here."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .models import ModelDescriptor

_MAX_DESCRIPTORS = 32


@dataclass(frozen=True)
class RegistrySelectionProof:
    """Opaque registry-sealed selection; construction alone cannot authorize it."""

    model_id: str
    version: str
    provider: str
    digest: bytes


class ModelRegistry:
    """An immutable, stable-ID lookup over known configured model descriptors."""

    __slots__ = ("_descriptors", "_sealer")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ModelRegistry is final")

    def __init__(
        self, descriptors: tuple[ModelDescriptor, ...] | list[ModelDescriptor]
    ) -> None:
        indexed = {descriptor.model_id: descriptor for descriptor in descriptors}
        if len(descriptors) > _MAX_DESCRIPTORS:
            raise ValueError("model registry is bounded to 32 descriptors")
        if len(indexed) != len(descriptors):
            raise ValueError("model descriptors must have unique model_id values")
        self._descriptors = indexed
        self._sealer = secrets.token_bytes(32)

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

    def issue_selection(self, descriptor: ModelDescriptor) -> RegistrySelectionProof:
        if self.get(descriptor.model_id) is not descriptor:
            raise ValueError("descriptor is not owned by this registry")
        payload = (
            f"{descriptor.model_id}|{descriptor.version}|{descriptor.provider}".encode()
        )
        return RegistrySelectionProof(
            descriptor.model_id,
            descriptor.version,
            descriptor.provider,
            hmac.digest(self._sealer, payload, hashlib.sha256),
        )

    def verify_selection(self, proof: object) -> ModelDescriptor | None:
        if not isinstance(proof, RegistrySelectionProof):
            return None
        descriptor = self.get(proof.model_id)
        if descriptor is None or (descriptor.version, descriptor.provider) != (
            proof.version,
            proof.provider,
        ):
            return None
        expected = self.issue_selection(descriptor).digest
        return descriptor if hmac.compare_digest(expected, proof.digest) else None
