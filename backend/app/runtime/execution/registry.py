"""In-process capability discovery without granting execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from .models import (
    CapabilityDescriptor,
    CapabilityInvocationContext,
    CapabilityResult,
)


@runtime_checkable
class CapabilityAdapter(Protocol):
    async def invoke(
        self,
        payload: BaseModel,
        context: CapabilityInvocationContext,
    ) -> CapabilityResult: ...


@dataclass(frozen=True)
class CapabilityRegistration:
    descriptor: CapabilityDescriptor
    adapter: CapabilityAdapter


class CapabilityRegistry:
    """Resolves registered capability metadata and adapters by stable ID."""

    def __init__(self) -> None:
        self._registrations: dict[str, CapabilityRegistration] = {}

    def register(
        self,
        descriptor: CapabilityDescriptor,
        adapter: CapabilityAdapter,
    ) -> None:
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError("descriptor must be a CapabilityDescriptor")
        if not isinstance(adapter, CapabilityAdapter):
            raise TypeError("adapter must implement CapabilityAdapter")
        if descriptor.capability_id in self._registrations:
            raise ValueError("capability is already registered")
        self._registrations[descriptor.capability_id] = CapabilityRegistration(
            descriptor=descriptor,
            adapter=adapter,
        )

    def resolve(self, capability_id: str) -> CapabilityRegistration:
        try:
            return self._registrations[capability_id]
        except (KeyError, TypeError) as error:
            raise LookupError("capability is not registered") from error

    def capability_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._registrations))
